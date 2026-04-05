# LLM interface — depends on core
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

from .core import *


def get_openclaw_llm_config() -> dict:
    """Read LLM config from openclaw models.json."""
    config = {
        "api_key": "",
        "base_url": "",
        "model": "MiniMax-M2",
    }
    # Check environment overrides
    import os
    for key in ("MINIMAX_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        if os.environ.get(key):
            config["api_key"] = os.environ[key]
    for key in ("MINIMAX_BASE_URL", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"):
        if os.environ.get(key):
            config["base_url"] = os.environ[key]
    for key in ("MINIMAX_MODEL", "OPENAI_MODEL", "ANTHROPIC_MODEL"):
        if os.environ.get(key):
            config["model"] = os.environ[key]
    # Read from models.json
    models_file = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "models.json"
    if models_file.exists():
        try:
            data = json.loads(models_file.read_text())
            providers = data.get("providers", {})
            for pkey in ("minimax", "openai", "anthropic"):
                prov = providers.get(pkey, {})
                if prov.get("apiKey"):
                    config["api_key"] = prov["apiKey"]
                if prov.get("baseUrl"):
                    config["base_url"] = prov["baseUrl"]
                    if not config["base_url"].endswith("/"):
                        config["base_url"] += "/"
                if prov.get("model"):
                    config["model"] = prov["model"]
        except Exception:
            pass
    return config


def call_llm(prompt: str, system: str = "", model: str = "",
              base_url: str = "", api_key: str = "",
              temperature: float = 0.3) -> str:
    """Call LLM API (Anthropic/OpenAI compatible)."""
    if not base_url or not api_key:
        config = get_openclaw_llm_config()
        base_url = base_url or config["base_url"]
        api_key = api_key or config["api_key"]
        model = model or config.get("model", "MiniMax-M2")
    if not base_url or not api_key:
        return ""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = json.dumps({
        "model": model or "MiniMax-M2",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 16000,
    }).encode("utf-8")
    endpoint = base_url.rstrip("/") + "/v1/messages"
    try:
        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "anthropic" in endpoint:
                text_blocks = [
                    b.get("text", "") for b in data.get("content", [])
                    if b.get("type") == "text" and b.get("text", "").strip()
                ]
                if text_blocks:
                    content = max(text_blocks, key=len)
                else:
                    thinking_blocks = [
                        b.get("thinking", "") for b in data.get("content", [])
                        if b.get("type") == "thinking" and b.get("thinking", "").strip()
                    ]
                    content = "\n".join(thinking_blocks)
            else:
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
            return _strip_code_fences(content)
    except Exception:
        return ""


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    if not text:
        return ""
    lines = text.splitlines()
    # Remove common fence patterns
    while lines and ("```" in lines[0] or lines[0].strip().startswith("here's") or
                    lines[0].strip().startswith("here is")):
        lines = lines[1:]
    while lines and ("```" in lines[-1] or lines[-1].strip().startswith("note:") or
                    lines[-1].strip().startswith("let me know")):
        lines = lines[:-1]
    content = "\n".join(lines).strip()
    if not content:
        return ""
    # If content starts with natural language (not code), try to find a code block
    non_code_starters = (
        "here", "this", "the", "i", "to", "after", "first", "you",
        "note", "let", "we", "of", "in", "for", "with", "that",
        "note:", "here's", "this ", "the function", "the code",
        "looking", "analysis", "based", "the following", "to fix",
        "the issue", "the problem", "i can", "i would",
    )
    first_word = content.split()[0].lower() if content.split() else ""
    first_two_words = " ".join(content.lower().split()[:2]) if content.split() else ""
    prose_patterns = (
        "looking at", "based on the", "i can see", "the following",
        "here is", "here's the", "to fix this", "the issue is",
    )
    is_prose = (
        first_word in non_code_starters
        or any(first_two_words.startswith(p) for p in prose_patterns)
        or not first_word
    )
    if is_prose:
        code_indicators = (
            "def ", "class ", "import ", "from ", "if ", "else:", "return ",
            "for ", "while ", "async ", "@", "async def", "const ", "let ",
            "function ", "fn ", "func "
        )
        for i, line in enumerate(lines):
            stripped = line.strip()
            if any(stripped.startswith(ind) for ind in code_indicators):
                return "\n".join(lines[i:]).strip()
        return ""
    return content


def analyze_with_llm(code_snippet: str, context: str, repo_path: str = "") -> dict:
    """Analyze code snippet and return suggestion via LLM."""
    config = get_openclaw_llm_config()
    if not config["api_key"] or not config["base_url"]:
        return {"suggestion": "", "risk_level": "medium",
                "implementation_hint": "", "available": False}
    # Detect language from file path
    lang = "python"
    if repo_path:
        ext = Path(repo_path).suffix.lower()
        lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                    ".go": "go", ".rs": "rust", ".java": "java",
                    ".cpp": "cpp", ".c": "c", ".cs": "csharp"}
        lang = lang_map.get(ext, "text")
    system = (
        "You are a senior code reviewer. Return valid JSON with keys: "
        "suggestion, risk_level, implementation_hint. Only JSON."
    )
    prompt = (
        "Context: " + context + "\n\nCode:\n```" + lang + "\n"
        + code_snippet[:2000] + "\n```"
    )
    result = call_llm(prompt=prompt, system=system, model=config["model"],
                     base_url=config["base_url"], api_key=config["api_key"])
    if not result:
        return {"suggestion": "", "risk_level": "medium",
                "implementation_hint": "", "available": False}
    try:
        parsed = json.loads(result)
        parsed["available"] = True
        return parsed
    except json.JSONDecodeError:
        m = re.search(r'\{[^{}]*\}', result, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group())
                parsed["available"] = True
                return parsed
            except Exception:
                pass
        return {"suggestion": result.strip()[:200], "risk_level": "medium",
                "implementation_hint": "", "available": True}

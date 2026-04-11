"""
LLM Evaluator — Core evaluation engine using LLM for perspective scanning.

This module provides the LLM-powered evaluation capability that scanners use to:
1. Analyze code and determine if a check passes/fails
2. Assess severity of findings
3. Generate natural language descriptions and evidence summaries
4. Classify findings into dimensions

Usage:
    from llm_evaluator import LLMEvaluator

    evaluator = LLMEvaluator(
        model="gpt-4",
        api_key=os.environ["OPENAI_API_KEY"]
    )

    result = evaluator.evaluate(
        perspective="security",
        dimension="injection",
        check_id="SQL_INJECTION_001",
        code_context={"file": "src/db.py", "snippet": "cursor.execute(f'SELECT * FROM users')"},
        perspective_doc=security_perspective_doc,
        previous_decisions=learnings
    )
"""

import json
import re
import os
from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path


# ─── Data Classes ────────────────────────────────────────────────────────────────

@dataclass
class LLMConfig:
    """Configuration for LLM calls."""
    model: str = "gpt-4"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int = 2048
    timeout_seconds: int = 60

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load config from environment variables."""
        return cls(
            model=os.environ.get("LLM_MODEL", "gpt-4"),
            base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.environ.get("OPENAI_API_KEY", ""),
        )


@dataclass
class EvaluationContext:
    """Context passed to the LLM for evaluation."""
    perspective: str
    dimension: str
    check_id: str
    file_path: str
    code_snippet: str
    perspective_doc: str          # Full perspective standard document text
    project_type: str = "generic"
    tech_stack: str = "python"
    language: Optional[str] = None
    previous_decisions: list = field(default_factory=list)  # Past decisions for this pattern


@dataclass
class EvaluationResult:
    """Structured result from LLM evaluation."""
    status: Literal["pass", "fail", "warning", "na"]
    severity: Literal["critical", "high", "medium", "low"]
    confidence: float                    # 0.0 - 1.0
    description: str                      # Human-readable finding description
    evidence: list[str]                  # Code snippets, file paths, metrics
    suggested_fix: str                   # What to do about it
    fix_action: str                      # Maps to fix-action-registry.md
    dimension: str                       # Which dimension this belongs to
    auto_actionable: bool
    reasoning: str                      # Why the LLM made this decision
    raw_response: str = ""              # Full LLM response for debugging


# ─── Prompt Templates ──────────────────────────────────────────────────────────

EVALUATION_SYSTEM_PROMPT = """You are an expert software quality inspector. You are evaluating code against the `{perspective}` perspective standard.

Your task: Analyze the provided code snippet and determine if it passes or fails the check `{check_id}`.

PERSPECTIVE STANDARD:
{perspective_doc}

Think step by step:
1. What is this check asking for?
2. Does the code snippet meet the requirement?
3. What evidence supports your conclusion?
4. How severe is any violation?
5. How can it be fixed?

Respond ONLY with a valid JSON object matching this exact schema:
{{
    "status": "pass" | "fail" | "warning" | "na",
    "severity": "critical" | "high" | "medium" | "low",
    "confidence": 0.0-1.0,
    "description": "What you found (max 200 chars)",
    "evidence": ["line 1 of evidence", "line 2 of evidence"],
    "suggested_fix": "How to fix it (max 150 chars)",
    "fix_action": "Maps to fix-action-registry (e.g. 'parameterize_query')",
    "dimension": "{dimension}",
    "auto_actionable": true | false,
    "reasoning": "Why you made this decision (max 300 chars)"
}}

If the code is not relevant to this check, return status="na".
If the code clearly violates the check, return status="fail".
If the code is close but not quite right (minor issues), return status="warning"."""

BATCH_EVALUATION_SYSTEM_PROMPT = """You are an expert software quality inspector. You are evaluating multiple code snippets against the `{perspective}` perspective standard.

For EACH snippet, determine if it passes or fails the check `{check_id}`.

Return a JSON object mapping file paths to their evaluation results:
{{
    "results": {{
        "file/path/snippet_id": {{
            "status": "pass" | "fail" | "warning" | "na",
            "severity": "critical" | "high" | "medium" | "low",
            "confidence": 0.0-1.0,
            "description": "What you found (max 200 chars)",
            "evidence": ["evidence line 1"],
            "suggested_fix": "How to fix it (max 150 chars)",
            "fix_action": "fix-action-registry action name",
            "auto_actionable": true | false,
            "reasoning": "Why (max 200 chars)"
        }}
    }}
}}"""


# ─── LLM API Client ────────────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    system: str,
    config: LLMConfig,
    json_mode: bool = True,
) -> str:
    """Make an LLM API call. Returns the response text."""
    import urllib.request
    import urllib.error

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        raise LLMError(f"HTTP {e.code}: {body}")
    except Exception as e:
        raise LLMError(f"LLM call failed: {e}")


# ─── Custom Exceptions ──────────────────────────────────────────────────────────

class LLMError(Exception):
    """Raised when LLM API call fails."""
    pass


# ─── Main Evaluator ────────────────────────────────────────────────────────────

class LLMEvaluator:
    """
    LLM-powered code evaluator.

    Uses an LLM to analyze code snippets against perspective standards
    and produce structured EvaluationResult objects.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()
        if not self.config.api_key:
            raise ValueError("API key required. Set OPENAI_API_KEY env var.")

    def evaluate(self, context: EvaluationContext) -> EvaluationResult:
        """
        Evaluate a single code snippet against a check.

        Args:
            context: EvaluationContext with code and perspective info

        Returns:
            EvaluationResult with status, severity, evidence, etc.
        """
        system_prompt = EVALUATION_SYSTEM_PROMPT.format(
            perspective=context.perspective,
            dimension=context.dimension,
            check_id=context.check_id,
            perspective_doc=context.perspective_doc[:8000],  # Truncate to fit token budget
        )

        user_prompt = self._build_evaluation_prompt(context)

        try:
            raw = call_llm(user_prompt, system_prompt, self.config)
            parsed = json.loads(raw)
            return self._parse_result(parsed, raw, context)
        except json.JSONDecodeError as e:
            # LLM didn't return valid JSON — fall back to warning
            return EvaluationResult(
                status="warning",
                severity="medium",
                confidence=0.3,
                description=f"LLM evaluation failed: could not parse response",
                evidence=[],
                suggested_fix="Review manually",
                fix_action="",
                dimension=context.dimension,
                auto_actionable=False,
                reasoning=f"JSON parse error: {e}. Raw: {raw[:500]}",
                raw_response=raw,
            )
        except LLMError as e:
            return EvaluationResult(
                status="warning",
                severity="medium",
                confidence=0.3,
                description=f"LLM evaluation failed: {e}",
                evidence=[],
                suggested_fix="Retry scan or evaluate manually",
                fix_action="",
                dimension=context.dimension,
                auto_actionable=False,
                reasoning=str(e),
                raw_response="",
            )

    def evaluate_batch(
        self,
        context: EvaluationContext,
        snippets: dict[str, str],  # snippet_id → code
    ) -> dict[str, EvaluationResult]:
        """
        Evaluate multiple code snippets in a single LLM call.

        Args:
            context: EvaluationContext (check_id/dimension/perspective only)
            snippets: dict of snippet_id → code text

        Returns:
            dict of snippet_id → EvaluationResult
        """
        system_prompt = BATCH_EVALUATION_SYSTEM_PROMPT.format(
            perspective=context.perspective,
            check_id=context.check_id,
        )

        user_prompt = f"Evaluate these {len(snippets)} code snippets:\n\n"
        for snippet_id, code in snippets.items():
            user_prompt += f"--- {snippet_id} ---\n{code[:500]}\n\n"

        try:
            raw = call_llm(user_prompt, system_prompt, self.config)
            parsed = json.loads(raw)
            results = {}
            for snippet_id, eval_data in parsed.get("results", {}).items():
                results[snippet_id] = self._parse_result(
                    eval_data, raw, context
                )
            return results
        except (json.JSONDecodeError, LLMError, KeyError) as e:
            # Fall back to individual evaluations
            results = {}
            for snippet_id, code in snippets.items():
                context_copy = EvaluationContext(
                    perspective=context.perspective,
                    dimension=context.dimension,
                    check_id=context.check_id,
                    file_path=snippet_id,
                    code_snippet=code,
                    perspective_doc=context.perspective_doc,
                    project_type=context.project_type,
                    tech_stack=context.tech_stack,
                    language=context.language,
                    previous_decisions=context.previous_decisions,
                )
                results[snippet_id] = self.evaluate(context_copy)
            return results

    def _build_evaluation_prompt(self, context: EvaluationContext) -> str:
        """Build the user prompt for a single evaluation."""
        # Detect language if not provided
        lang = context.language or self._detect_language(
            context.file_path, context.code_snippet
        )

        prompt_parts = [
            f"FILE: {context.file_path}",
            f"LANGUAGE: {lang}",
            f"PROJECT TYPE: {context.project_type}",
            "",
            "CODE SNIPPET:",
            "```" + (lang or ""),
            context.code_snippet[:2000],
            "```",
        ]

        # Add relevant previous decisions
        if context.previous_decisions:
            prompt_parts.append("\nRELEVANT PREVIOUS DECISIONS:")
            for decision in context.previous_decisions[-3:]:  # Last 3
                prompt_parts.append(
                    f"  - {decision.get('decision', 'N/A')}: "
                    f"{decision.get('description', '')[:200]}"
                )

        return "\n".join(prompt_parts)

    def _detect_language(self, file_path: str, snippet: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".go": "go",
            ".java": "java",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".cs": "csharp",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".sql": "sql",
            ".sh": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".md": "markdown",
        }
        return lang_map.get(ext, "text")

    def _parse_result(
        self, parsed: dict, raw: str, context: EvaluationContext
    ) -> EvaluationResult:
        """Parse LLM JSON response into EvaluationResult."""
        # Validate and normalize status
        raw_status = parsed.get("status", "warning")
        status = self._normalize_status(raw_status)

        # Validate and normalize severity
        raw_severity = parsed.get("severity", "medium")
        severity = self._normalize_severity(raw_severity)

        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        description = parsed.get("description", "No description")
        suggested_fix = parsed.get("suggested_fix", "")
        fix_action = parsed.get("fix_action", "")
        auto_actionable = bool(parsed.get("auto_actionable", False))
        reasoning = parsed.get("reasoning", "")

        # Extract evidence as list
        raw_evidence = parsed.get("evidence", [])
        if isinstance(raw_evidence, str):
            evidence = [raw_evidence]
        elif isinstance(raw_evidence, list):
            evidence = [str(e)[:200] for e in raw_evidence]
        else:
            evidence = []

        # Add file path to evidence
        evidence.insert(0, f"File: {context.file_path}")

        # Determine if auto-actionable based on fix_action
        if fix_action and auto_actionable is False:
            pass  # Respect explicit override
        elif fix_action:
            auto_actionable = True

        return EvaluationResult(
            status=status,
            severity=severity,
            confidence=confidence,
            description=description[:200],
            evidence=evidence,
            suggested_fix=suggested_fix[:150],
            fix_action=fix_action,
            dimension=parsed.get("dimension", context.dimension),
            auto_actionable=auto_actionable,
            reasoning=reasoning[:300],
            raw_response=raw,
        )

    def _normalize_status(self, status: str) -> Literal["pass", "fail", "warning", "na"]:
        """Normalize status string to valid enum."""
        mapping = {
            "pass": "pass", "passes": "pass", "passed": "pass",
            "fail": "fail", "fails": "fail", "failed": "fail",
            "warning": "warning", "warn": "warning",
            "na": "na", "n/a": "na", "not_applicable": "na",
        }
        return mapping.get(status.lower().strip(), "warning")

    def _normalize_severity(
        self, severity: str
    ) -> Literal["critical", "high", "medium", "low"]:
        """Normalize severity string to valid enum."""
        mapping = {
            "critical": "critical", "crit": "critical",
            "high": "high",
            "medium": "medium", "med": "medium",
            "low": "low",
        }
        return mapping.get(severity.lower().strip(), "medium")


# ─── Code Extractor ────────────────────────────────────────────────────────────

class CodeExtractor:
    """
    Extract relevant code snippets for scanning.

    Given a repo path and a check pattern, extracts relevant
    code snippets for LLM evaluation.
    """

    # Patterns that indicate which files to scan for which check
    CHECK_FILE_PATTERNS = {
        "sql_injection": ["*.py", "*.js", "*.ts", "*.java", "*.go"],
        "hardcoded_secret": ["*.py", "*.js", "*.ts", "*.java", "*.go", "*.env*"],
        "xss": ["*.html", "*.js", "*.ts", "*.jsx", "*.tsx"],
        "command_injection": ["*.py", "*.js", "*.sh"],
        "auth": ["*auth*.py", "*login*.py", "*session*.py"],
        "dependency": ["package.json", "requirements.txt", "go.mod", "Cargo.toml"],
    }

    def extract_for_check(
        self,
        repo_path: Path,
        check_id: str,
        dimension: str,
    ) -> list[dict]:
        """
        Extract relevant code snippets for a given check.

        Returns list of dicts: [{"file": "...", "snippet": "...", "line": N}]
        """
        patterns = self.CHECK_FILE_PATTERNS.get(
            dimension.lower(), ["*.py", "*.js", "*.ts"]
        )

        snippets = []
        for pattern in patterns:
            for file_path in repo_path.rglob(pattern):
                if self._should_skip(file_path):
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    # For now, return the full file as a snippet
                    # A smarter implementation would do semantic chunking
                    snippets.append({
                        "file": str(file_path.relative_to(repo_path)),
                        "snippet": content[:3000],  # First 3000 chars
                        "line": 1,
                    })
                except Exception:
                    continue

        return snippets

    def _should_skip(self, path: Path) -> bool:
        """Skip common non-source directories."""
        skip_dirs = {
            "node_modules", ".venv", "venv", "env",
            "dist", "build", ".git", "__pycache__",
            "coverage", ".tox", ".pytest_cache",
        }
        return any(part in path.parts for part in skip_dirs)


# ─── Smoke Test ────────────────────────────────────────────────────────────────

def smoke_test():
    """Test the evaluator with a known example."""
    evaluator = LLMEvaluator()

    context = EvaluationContext(
        perspective="security",
        dimension="injection",
        check_id="SQL_INJECTION_001",
        file_path="src/db.py",
        code_snippet="cursor.execute(f'SELECT * FROM users WHERE id={user_id}')",
        perspective_doc="Check: All database queries must use parameterized queries.",
        project_type="backend",
        tech_stack="python",
    )

    result = evaluator.evaluate(context)
    print(f"Status: {result.status}")
    print(f"Severity: {result.severity}")
    print(f"Confidence: {result.confidence}")
    print(f"Description: {result.description}")
    print(f"Fix Action: {result.fix_action}")
    print(f"Reasoning: {result.reasoning}")


if __name__ == "__main__":
    smoke_test()

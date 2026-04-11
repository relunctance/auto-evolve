"""
LLM Config Resolution — Zero Config for OpenClaw Skills

Resolution order:
  1. Explicit env vars (highest priority — user override)
  2. OpenClaw auto-discover (read OpenClaw's own config)
  3. Raise error (no config found)

Usage:
    from scripts.llm_config import resolve_llm_config
    config = resolve_llm_config()  # returns (base_url, api_key, model)
    # OR with explicit override:
    config = resolve_llm_config(base_url="...", api_key="...", model="...")
"""

import json
import os
from pathlib import Path
from typing import Optional

HOME = Path.home()
OPENCLAW_CONFIG = HOME / ".openclaw" / "openclaw.json"
OPENCLAW_AGENT_MODELS = HOME / ".openclaw" / "agents" / "main" / "agent" / "models.json"


def _load_openclaw_config() -> dict:
    """Load OpenClaw's main config."""
    if not OPENCLAW_CONFIG.exists():
        return {}
    return json.loads(OPENCLAW_CONFIG.read_text())


def _load_agent_models() -> dict:
    """Load agent's models config (contains API keys)."""
    if not OPENCLAW_AGENT_MODELS.exists():
        return {}
    return json.loads(OPENCLAW_AGENT_MODELS.read_text())


def resolve_openclaw_defaults() -> dict:
    """Read OpenClaw's default model from openclaw.json and agent models.json.

    Returns:
        dict with keys: base_url, api_key, model
        Returns empty dict if not found.
    """
    openclaw = _load_openclaw_config()
    agent_models = _load_agent_models()

    # Get default model name, e.g. "minimax/MiniMax-M2.7-highspeed"
    defaults = openclaw.get("agents", {}).get("defaults", {})
    primary = defaults.get("model", {}).get("primary", "")
    if not primary:
        return {}

    # Parse "provider/model"
    if "/" not in primary:
        return {}
    provider_name, model_id = primary.split("/", 1)

    # Look up provider in agent models.json
    providers = agent_models.get("providers", {})
    provider_config = providers.get(provider_name, {})
    api_key = provider_config.get("apiKey", "")

    base_url = provider_config.get("baseUrl", "")
    if not api_key or not base_url:
        return {}

    return {
        "model": primary,
        "base_url": base_url,
        "api_key": api_key,
        "provider": provider_name,
        "model_id": model_id,
        "source": "openclaw",
    }


def resolve_llm_config(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Resolve LLM config with the following priority:

    1. Explicit args (base_url, api_key, model) — user override
    2. Env vars (OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL etc.)
       - Supports: OPENAI_*, MINIMAX_*, ANTHROPIC_*
    3. OpenClaw auto-discover — read OpenClaw's own config
    4. Raise RuntimeError

    Returns:
        dict: {model, base_url, api_key, provider, source}
    """
    # Priority 1: explicit args
    if api_key and base_url and model:
        return {
            "model": model,
            "base_url": base_url,
            "api_key": api_key,
            "source": "explicit",
        }

    # Priority 2: environment variables
    # Try common LLM provider env vars
    if os.environ.get("OPENAI_API_KEY"):
        return {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o"),
            "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "api_key": os.environ["OPENAI_API_KEY"],
            "source": "env",
        }
    if os.environ.get("MINIMAX_API_KEY"):
        return {
            "model": os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
            "base_url": os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"),
            "api_key": os.environ["MINIMAX_API_KEY"],
            "source": "env",
        }
    if os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            "base_url": os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
            "api_key": os.environ["ANTHROPIC_API_KEY"],
            "source": "env",
        }

    # Try generic LLM API key env (some providers use this pattern)
    for env_key in ("LLM_API_KEY", "API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(env_key):
            return {
                "model": os.environ.get("LLM_MODEL", "gpt-4o"),
                "base_url": os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
                "api_key": os.environ[env_key],
                "source": "env",
            }

    # Priority 3: OpenClaw auto-discover
    openclaw_config = resolve_openclaw_defaults()
    if openclaw_config:
        return openclaw_config

    # No config found
    raise RuntimeError(
        "No LLM configuration found. "
        "Set one of: OPENAI_API_KEY, MINIMAX_API_KEY, ANTHROPIC_API_KEY, LLM_API_KEY, "
        "or ensure OpenClaw is configured at ~/.openclaw/openclaw.json"
    )


def get_llm_config_summary() -> str:
    """Return a human-readable summary of the resolved LLM config (no secrets)."""
    try:
        config = resolve_llm_config()
        return (
            f"[{config['source']}] "
            f"model={config['model']} "
            f"provider={config.get('provider', '?')} "
            f"(key: {'✓ set' if config['api_key'] else '✗ missing'})"
        )
    except RuntimeError as e:
        return f"[none] {e}"


if __name__ == "__main__":
    print("LLM Config Resolution (zero-config for OpenClaw skills)")
    print("=" * 50)
    try:
        config = resolve_llm_config()
        print(f"Source:   {config['source']}")
        print(f"Model:    {config['model']}")
        print(f"Provider: {config.get('provider', '?')}")
        print(f"Base URL: {config['base_url']}")
        print(f"API Key:  {'✓' if config['api_key'] else '✗'}")
    except RuntimeError as e:
        print(f"❌ {e}")

# Helper functions — depends on core
import json
from pathlib import Path
from typing import Optional

from .core import *


# ---- Learnings -----------------------------------------------------------

LEARNINGS_DIR = Path.home() / ".openclaw" / "workspace" / "skills" / "auto-evolve" / ".learnings"


def ensure_learnings_dir() -> Path:
    """Ensure .learnings directory exists."""
    LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    return LEARNINGS_DIR


def load_learnings() -> dict:
    """Load learnings from .learnings/approvals.json and .learnings/rejections.json."""
    ensure_learnings_dir()
    approvals = []
    rejections = []
    try:
        with open(ensure_learnings_dir() / "approvals.json", "r") as f:
            approvals = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    try:
        with open(ensure_learnings_dir() / "rejections.json", "r") as f:
            rejections = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"approvals": approvals, "rejections": rejections}


def save_learnings(data: dict) -> None:
    """Save learnings to .learnings/."""
    ensure_learnings_dir()
    for key in ("approvals", "rejections"):
        fp = ensure_learnings_dir() / f"{key}.json"
        with open(fp, "w") as f:
            json.dump(data.get(key, []), f, ensure_ascii=False, indent=2)


def is_rejected(change_desc: str, repo: str, learnings: dict) -> bool:
    """Check if a change was previously rejected."""
    for r in learnings.get("rejections", []):
        if r.get("repo") == repo and r.get("description", "") == change_desc:
            return True
    return False


def infer_value_score(item: ChangeItem) -> int:
    """Infer value score (1-10) for a change item."""
    keywords_high = [
        "test", "bug", "fix", "security", "vulnerability",
        "crash", "leak", "performance", "optimize", "critical",
    ]
    keywords_medium = [
        "refactor", "improve", "update", "enhance", "add feature",
        "compatibility", "deprecate",
    ]
    desc_lower = item.description.lower()
    if any(kw in desc_lower for kw in keywords_high):
        return 8
    if any(kw in desc_lower for kw in keywords_medium):
        return 5
    return 3


def infer_risk_score(risk: RiskLevel) -> int:
    """Convert risk level to numeric score (1-5)."""
    mapping = {
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 3,
        RiskLevel.HIGH: 4,
        RiskLevel.CRITICAL: 5,
    }
    return mapping.get(risk, 2)


def infer_cost_score(item: ChangeItem) -> int:
    """Infer implementation cost score (1-10)."""
    cost_keywords_low = ["comment", "docs", "typo", "format", "whitespace"]
    cost_keywords_high = [
        "database", "migration", "api change", "refactor",
        "redesign", "breaking", "schema",
    ]
    desc_lower = item.description.lower()
    if any(kw in desc_lower for kw in cost_keywords_low):
        return 2
    if any(kw in desc_lower for kw in cost_keywords_high):
        return 8
    return 4


def calculate_priority(item: ChangeItem) -> float:
    """
    Calculate priority score: higher = more important.
    Formula: value_score * 0.4 + (1 - risk/5) * 0.3 + (1 - cost/10) * 0.3
    """
    vs = infer_value_score(item)
    rs = infer_risk_score(item.risk)
    cs = infer_cost_score(item)
    return vs * 0.4 + (1 - rs / 5) * 0.3 + (1 - cs / 10) * 0.3


def enrich_change_with_priority(item: ChangeItem) -> ChangeItem:
    """Calculate and set priority for a change item."""
    item.value_score = float(infer_value_score(item))
    item.cost_score = float(infer_cost_score(item))
    item.priority = calculate_priority(item)
    return item


def sort_by_priority(items: list[ChangeItem]) -> list[ChangeItem]:
    """Sort change items by priority descending."""
    return sorted(items, key=lambda i: i.priority, reverse=True)

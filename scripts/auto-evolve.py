#!/usr/bin/env python3
"""
Auto-Evolve v3.3 — Automated skill iteration manager.

Features (v3.3):
- ProductThinkingScanner: asks "what is broken for users?" not "is code clean?"
- EffectTracker: true before/after effect tracking per iteration
- CostTracker: LLM call cost tracking with pricing table
- IssueLinker: auto-close GitHub issues related to committed changes
- SmartScheduler: activity-based dynamic scan frequency

Features (v3.0):
- LLM-driven code analysis
- Dependency awareness
- Test comparison
- Cherry-pick rollback
- Multi-language support
- Release management
- Contributor tracking
- Priority scoring

Usage:
    auto-evolve.py scan [--dry-run]
    auto-evolve.py approve [--all | ID...] [--reason TEXT]
    auto-evolve.py confirm                       # confirm pending changes (semi-auto)
    auto-evolve.py reject <id> [--reason TEXT]
    auto-evolve.py repo-add <path> --type TYPE [--monitor]
    auto-evolve.py repo-list
    auto-evolve.py rollback --to VERSION
    auto-evolve.py schedule --every HOURS
    auto-evolve.py schedule --suggest
    auto-evolve.py schedule --auto
    auto-evolve.py schedule --show
    auto-evolve.py schedule --remove
    auto-evolve.py set-mode semi-auto|full-auto
    auto-evolve.py set-rules [--low] [--medium] [--high]
    auto-evolve.py log [--limit N]
    auto-evolve.py learnings
    auto-evolve.py release --version VERSION [--changelog TEXT]
    auto-evolve.py effects [--iteration ID]
    auto-evolve.py costs [--iteration ID]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ===========================================================
# Constants
# ===========================================================

HOME = Path.home()
AUTO_EVOLVE_RC = HOME / ".auto-evolverc.json"
SKILL_DIR = HOME / ".openclaw" / "workspace" / "skills" / "auto-evolve"
ITERATIONS_DIR = SKILL_DIR / ".iterations"
LEARNINGS_DIR = SKILL_DIR / ".learnings"

REPO_TYPES = ("skill", "norms", "project", "closed")

# Multi-language TODO patterns
TODO_PATTERNS = {
    ".py": ["# TODO", "# FIXME", "# XXX", "# HACK", "# NOTE"],
    ".js": ["// TODO", "// FIXME", "// XXX", "// HACK", "/* TODO"],
    ".ts": ["// TODO", "// FIXME", "// XXX", "// HACK", "/* TODO"],
    ".go": ["// TODO", "// FIXME", "// XXX"],
    ".sh": ["# TODO", "# FIXME", "# XXX"],
    ".java": ["// TODO", "// FIXME", "// XXX", "/* TODO"],
    ".md": ["<!-- TODO", "[TODO]", "- [ ]"],
}
LANGUAGE_EXTENSIONS = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".go": "go",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".java": "java",
}
RISK_LEVELS = ("low", "medium", "high")
RISK_COLORS = {
    "low": "🟢",
    "medium": "🟡",
    "high": "🔴",
}

# Priority scoring weights
PRIORITY_WEIGHTS = {
    "value": 0.5,
    "risk": 0.3,
    "cost": 0.2,
}

DEFAULT_VALUE_SCORES = {
    "bug_fix": 10,
    "todo_fixme": 7,
    "add_test": 7,
    "optimization": 6,
    "refactor": 5,
    "docs": 4,
    "lint_fix": 4,
    "formatting": 3,
}

DEFAULT_COST_SCORES = {
    "5min": 1,
    "15min": 3,
    "30min": 5,
    "1h": 7,
    "2h": 10,
}


# ===========================================================
# LLM Pricing (v3.2 CostTracker)
# ===========================================================

LLM_PRICING: dict[str, dict[str, float]] = {
    "MiniMax-M2": {"input": 0.1, "output": 0.3},
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
    "claude-3-opus": {"input": 15.0, "output": 75.0},
}


# ===========================================================
# Enums
# ===========================================================

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ChangeCategory(Enum):
    AUTO_EXEC = "auto_exec"
    PENDING_APPROVAL = "pending_approval"
    OPTIMIZATION = "optimization"


class OperationMode(Enum):
    SEMI_AUTO = "semi-auto"
    FULL_AUTO = "full-auto"


# ===========================================================
# Data Models
# ===========================================================

@dataclass
class Repository:
    path: str
    type: str
    visibility: str = "public"
    auto_monitor: bool = True
    risk_override: Optional[str] = None
    scan_interval_hours: int = 168  # v3.2 SmartScheduler

    def resolve_path(self) -> Path:
        return Path(self.path).expanduser().resolve()

    def is_closed(self) -> bool:
        return self.visibility == "closed"

    def get_default_risk(self, change_type: str, file_path: str) -> RiskLevel:
        if self.risk_override:
            return RiskLevel(self.risk_override)

        file_lower = file_path.lower()

        if self.visibility == "closed":
            if change_type in ("modified", "added"):
                if any(ext in file_lower for ext in (".py", ".js", ".ts", ".go", ".rs")):
                    return RiskLevel.MEDIUM
            if change_type == "removed":
                return RiskLevel.MEDIUM

        if self.type == "norms":
            if any(ext in file_lower for ext in (".md", ".txt", ".yaml", ".yml", ".json")):
                return RiskLevel.LOW

        if self.type == "project":
            if "test" in file_lower or "_test." in file_lower:
                return RiskLevel.MEDIUM

        return RiskLevel.MEDIUM


@dataclass
class ChangeItem:
    id: int
    description: str
    file_path: str
    change_type: str
    risk: RiskLevel
    category: ChangeCategory
    repo_path: str = ""
    repo_type: str = ""
    optimization_type: Optional[str] = None
    commit_hash: Optional[str] = None
    pr_url: Optional[str] = None
    content_hash: Optional[str] = None
    value_score: int = 5
    risk_score: int = 5
    cost_score: int = 5
    priority: float = 0.0
    llm_suggestion: Optional[str] = None
    llm_risk: Optional[str] = None
    llm_implementation_hint: Optional[str] = None
    affected_files: Optional[list[str]] = None


@dataclass
class OptimizationFinding:
    type: str
    file_path: str
    line: int
    description: str
    suggestion: str
    risk: RiskLevel


@dataclass
class IterationManifest:
    version: str
    date: str
    status: str
    risk_level: str
    items_auto: int = 0
    items_approved: int = 0
    items_rejected: int = 0
    items_optimization: int = 0
    duration_seconds: float = 0.0
    items_pending_approval: list = field(default_factory=list)
    rollback_of: Optional[str] = None
    rollback_reason: Optional[str] = None
    has_alert: bool = False
    metrics_id: Optional[str] = None
    test_coverage_delta: Optional[float] = None
    contributors: Optional[dict] = None
    # v3.2
    total_cost_usd: Optional[float] = None
    llm_calls: int = 0


@dataclass
class LearningEntry:
    id: str
    type: str
    change_id: str
    description: str
    reason: Optional[str]
    date: str
    repo: str
    approved_by: Optional[str] = None


@dataclass
class AlertEntry:
    iteration_id: str
    date: str
    alert_type: str
    message: str
    details: dict


@dataclass
class IterationMetrics:
    iteration_id: str
    date: str
    todos_resolved: int = 0
    lint_errors_fixed: int = 0
    test_coverage_delta: float = 0.0
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    quality_gate_passed: bool = True


# ===========================================================
# v3.2: EffectTracker
# ===========================================================

class EffectTracker:
    """
    Tracks the actual effects of each iteration by comparing
    code quality metrics before and after changes are applied.
    """

    def __init__(self, iterations_dir: Path = ITERATIONS_DIR) -> None:
        self.iterations_dir = iterations_dir

    def count_todos(self, repo_path: Path) -> int:
        """Count unresolved TODO/FIXME annotations across the repo."""
        count = 0
        for ext, patterns in TODO_PATTERNS.items():
            if ext == ".md":
                continue  # Skip markdown separately
            for code_file in repo_path.rglob(f"*{ext}"):
                if any(s in str(code_file) for s in (".git", "__pycache__", "node_modules", ".iterations")):
                    continue
                try:
                    content = code_file.read_text(encoding="utf-8")
                    for line in content.split("\n"):
                        for pat in patterns:
                            if pat in line:
                                count += 1
                                break
                except (UnicodeDecodeError, OSError):
                    pass
        # Also scan markdown TODO markers
        for md_file in repo_path.rglob("*.md"):
            if ".git" in str(md_file) or ".iterations" in str(md_file):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    for pat in TODO_PATTERNS[".md"]:
                        if pat in line:
                            count += 1
                            break
            except (UnicodeDecodeError, OSError):
                pass
        return count

    def count_code_lines(self, repo_path: Path) -> int:
        """Count non-blank, non-comment lines of code."""
        total = 0
        for ext in LANGUAGE_EXTENSIONS:
            for code_file in repo_path.rglob(f"*{ext}"):
                if any(s in str(code_file) for s in (".git", "__pycache__", "node_modules", ".iterations")):
                    continue
                try:
                    content = code_file.read_text(encoding="utf-8")
                    for line in content.split("\n"):
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                            total += 1
                except (UnicodeDecodeError, OSError):
                    pass
        return total

    def count_functions(self, repo_path: Path) -> int:
        """Count function/ method definitions in Python files."""
        count = 0
        for py_file in repo_path.rglob("*.py"):
            if any(s in str(py_file) for s in (".git", "__pycache__", ".iterations")):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
                count += len(re.findall(r"^(?:async\s+)?def\s+\w+", content, re.MULTILINE))
            except (UnicodeDecodeError, OSError):
                pass
        return count

    def count_duplicate_lines(self, repo_path: Path) -> int:
        """Estimate duplicate code lines (identical lines appearing 3+ times)."""
        line_counts: dict[str, int] = {}
        for ext in LANGUAGE_EXTENSIONS:
            for code_file in repo_path.rglob(f"*{ext}"):
                if any(s in str(code_file) for s in (".git", "__pycache__", ".iterations")):
                    continue
                try:
                    content = code_file.read_text(encoding="utf-8")
                    for line in content.split("\n"):
                        stripped = line.strip()
                        if len(stripped) > 20 and not stripped.startswith("#") and not stripped.startswith("//"):
                            line_counts[stripped] = line_counts.get(stripped, 0) + 1
                except (UnicodeDecodeError, OSError):
                    pass
        return sum(1 for c in line_counts.values() if c >= 3)

    def run_lint(self, repo_path: Path) -> int:
        """Run pylint on Python files and return error count."""
        result = subprocess.run(
            ["python3", "-m", "py_compile"],
            cwd=str(repo_path),
            capture_output=True,
        )
        # Simple syntax check only - pylint may not be installed
        return 0  # Placeholder; real lint count requires pylint

    def snapshot(self, repo_path: Path) -> dict:
        """
        Take a snapshot of current code quality metrics.
        Returns a dict with todos, code_lines, functions, duplicates.
        """
        return {
            "todos": self.count_todos(repo_path),
            "code_lines": self.count_code_lines(repo_path),
            "functions": self.count_functions(repo_path),
            "duplicate_lines": self.count_duplicate_lines(repo_path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def track_iteration_effect(
        self,
        iteration_id: str,
        before_snapshots: dict[str, dict],
        after_snapshots: dict[str, dict],
        todos_resolved: int = 0,
        lint_errors_fixed: int = 0,
        coverage_delta: float = 0.0,
    ) -> dict:
        """
        Compare before/after snapshots and produce an effect report.
        Stores the result as effect.json in the iteration directory.
        """
        effects: dict[str, dict] = {}

        all_repos = set(before_snapshots.keys()) | set(after_snapshots.keys())

        for repo_key in all_repos:
            before = before_snapshots.get(repo_key, {})
            after = after_snapshots.get(repo_key, {})

            effects[repo_key] = {
                "todos_delta": (after.get("todos", 0) - before.get("todos", 0)),
                "code_lines_delta": (after.get("code_lines", 0) - before.get("code_lines", 0)),
                "functions_delta": (after.get("functions", 0) - before.get("functions", 0)),
                "duplicate_lines_delta": (after.get("duplicate_lines", 0) - before.get("duplicate_lines", 0)),
            }

        # Aggregate deltas across all repos
        total_todos_delta = sum(e["todos_delta"] for e in effects.values())
        total_code_lines_delta = sum(e["code_lines_delta"] for e in effects.values())
        total_functions_delta = sum(e["functions_delta"] for e in effects.values())
        total_duplicate_delta = sum(e["duplicate_lines_delta"] for e in effects.values())

        # Determine verdict
        positive_signals = sum(1 for d in [
            -total_todos_delta,  # Fewer TODOs = good
            coverage_delta,
            -total_duplicate_delta,  # Fewer duplicates = good
            -abs(total_functions_delta),  # Fewer long functions = good
        ] if d > 0)
        negative_signals = sum(1 for d in [
            -total_todos_delta,
            coverage_delta,
            -total_duplicate_delta,
            -abs(total_functions_delta),
        ] if d < 0)

        if positive_signals >= 3:
            verdict = "positive"
        elif negative_signals >= 3:
            verdict = "negative"
        else:
            verdict = "neutral"

        summary_parts = []
        if total_todos_delta != 0:
            summary_parts.append(f"{abs(total_todos_delta)} TODOs {'resolved' if total_todos_delta < 0 else 'added'}")
        if coverage_delta != 0:
            summary_parts.append(f"coverage {coverage_delta:+.1f}%")
        if total_duplicate_delta != 0:
            summary_parts.append(f"{abs(total_duplicate_delta)} duplicate lines {'removed' if total_duplicate_delta < 0 else 'added'}")
        if total_code_lines_delta != 0:
            summary_parts.append(f"{total_code_lines_delta:+,} lines of code")

        summary = ", ".join(summary_parts) if summary_parts else "No significant changes detected"

        effect_report = {
            "iteration_id": iteration_id,
            "date": datetime.now(timezone.utc).isoformat(),
            "effects": effects,
            "summary": summary,
            "verdict": verdict,
            "totals": {
                "todos_resolved": todos_resolved,
                "todos_delta": total_todos_delta,
                "coverage_delta": coverage_delta,
                "lint_errors_delta": -lint_errors_fixed if lint_errors_fixed else 0,
                "duplicate_lines_delta": total_duplicate_delta,
                "function_count_delta": total_functions_delta,
                "code_lines_delta": total_code_lines_delta,
            },
        }

        # Save to iteration directory
        iter_dir = self.iterations_dir / iteration_id
        iter_dir.mkdir(parents=True, exist_ok=True)
        (iter_dir / "effect.json").write_text(json.dumps(effect_report, indent=2))

        return effect_report


# ===========================================================
# v3.2: CostTracker
# ===========================================================

class CostTracker:
    """
    Tracks LLM call costs per iteration using a pricing table.
    Records each call and aggregates costs in catalog.json.
    """

    def __init__(self, iterations_dir: Path = ITERATIONS_DIR) -> None:
        self.iterations_dir = iterations_dir
        self.pricing = LLM_PRICING

    def track_llm_call(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
    ) -> dict:
        """
        Record a single LLM call and estimate its cost in USD.
        Saves the call record to the current iteration's llm_calls.jsonl.
        """
        pricing = self.pricing.get(model, {"input": 0.0, "output": 0.0})
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        total_cost = round(input_cost + output_cost, 6)

        record = {
            "date": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "estimated_cost_usd": total_cost,
        }

        # Append to current iteration's calls file (session-scoped)
        if not hasattr(self, "_pending_calls"):
            self._pending_calls: list[dict] = []
        self._pending_calls.append(record)

        return record

    def flush_calls(self, iteration_id: str) -> None:
        """Write accumulated calls to the iteration directory."""
        if not hasattr(self, "_pending_calls") or not self._pending_calls:
            return
        iter_dir = self.iterations_dir / iteration_id
        iter_dir.mkdir(parents=True, exist_ok=True)
        calls_file = iter_dir / "llm_calls.jsonl"
        with calls_file.open("a") as f:
            for call in self._pending_calls:
                f.write(json.dumps(call) + "\n")
        self._pending_calls = []

    def get_iteration_cost(self, iteration_id: str) -> dict:
        """Aggregate all LLM costs for a given iteration."""
        calls = self.load_calls(iteration_id)
        total = sum(c["estimated_cost_usd"] for c in calls)
        total_tokens = sum(c["total_tokens"] for c in calls)
        return {
            "iteration_id": iteration_id,
            "total_calls": len(calls),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total, 6),
        }

    def load_calls(self, iteration_id: str) -> list[dict]:
        """Load all LLM call records for an iteration."""
        calls_file = self.iterations_dir / iteration_id / "llm_calls.jsonl"
        if not calls_file.exists():
            return []
        calls = []
        with calls_file.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        calls.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return calls


# ===========================================================
# v3.2: IssueLinker
# ===========================================================

class IssueLinker:
    """
    Finds and auto-closes GitHub Issues related to committed changes.
    Uses `gh issue list` to find open issues referencing changed files.
    """

    def __init__(self) -> None:
        self._gh_available: Optional[bool] = None

    def _check_gh(self) -> bool:
        """Check if gh CLI is available."""
        if self._gh_available is None:
            self._gh_available = subprocess.run(
                ["which", "gh"], capture_output=True
            ).returncode == 0
        return self._gh_available

    def find_related_issues(self, repo_path: Path, changed_files: list[str]) -> list[dict]:
        """
        Find open issues whose title or body references any of the changed files.
        """
        if not self._check_gh():
            return []

        result = subprocess.run(
            ["gh", "issue", "list", "--state", "open", "--limit", "50", "--json", "number,title,body"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

        try:
            issues = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        related = []
        for issue in issues:
            body = issue.get("body", "") or ""
            title = issue.get("title", "") or ""
            combined = title.lower() + " " + body.lower()
            for file_path in changed_files:
                file_lower = file_path.lower()
                # Match file name or path component
                if file_lower in combined or Path(file_lower).name in combined:
                    related.append({
                        "number": issue["number"],
                        "title": issue["title"],
                        "body": body[:200],
                    })
                    break

        return related

    def close_issue(self, repo_path: Path, issue_number: int, comment: str) -> bool:
        """
        Add a comment to an issue explaining it was resolved by auto-evolve,
        then close it with reason 'completed'.
        """
        if not self._check_gh():
            return False

        # Add comment
        subprocess.run(
            [
                "gh", "issue", "comment", str(issue_number),
                "--body", comment,
            ],
            cwd=str(repo_path),
            capture_output=True,
        )

        # Close issue
        result = subprocess.run(
            [
                "gh", "issue", "close", str(issue_number),
                "--reason", "completed",
            ],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def close_related_issues(self, repo_path: Path, changed_files: list[str], iteration_id: str) -> dict:
        """
        Find and close all issues related to changed files.
        Returns a summary dict.
        """
        related = self.find_related_issues(repo_path, changed_files)
        if not related:
            return {"found": 0, "closed": 0, "issues": []}

        closed = []
        for issue in related:
            comment = (
                f"**Resolved by auto-evolve** (iteration `{iteration_id}`)\n\n"
                f"This issue was automatically resolved after the related "
                f"code changes were applied and validated."
            )
            success = self.close_issue(repo_path, issue["number"], comment)
            closed.append({
                "number": issue["number"],
                "title": issue["title"],
                "closed": success,
            })

        return {
            "found": len(related),
            "closed": sum(1 for c in closed if c["closed"]),
            "issues": closed,
        }


# ===========================================================
# v3.2: SmartScheduler
# ===========================================================

class SmartScheduler:
    """
    Dynamically adjusts scan frequency based on project activity.
    Uses git commit frequency over the last 7 days to assess activity level.
    """

    ACTIVITY_THRESHOLDS: dict[str, dict[str, int]] = {
        "very_active": {"commits_per_week": 20, "scan_interval_hours": 24},
        "active": {"commits_per_week": 10, "scan_interval_hours": 72},
        "normal": {"commits_per_week": 3, "scan_interval_hours": 168},
        "idle": {"commits_per_week": 0, "scan_interval_hours": 336},
    }

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or {}

    def assess_activity(self, repo_path: Path) -> str:
        """
        Count commits in the last 7 days and return activity level.
        Returns one of: very_active, active, normal, idle
        """
        result = subprocess.run(
            ["git", "log", "--oneline", "--since", "7 days ago"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        commit_count = len([l for l in lines if l])

        if commit_count >= self.ACTIVITY_THRESHOLDS["very_active"]["commits_per_week"]:
            return "very_active"
        elif commit_count >= self.ACTIVITY_THRESHOLDS["active"]["commits_per_week"]:
            return "active"
        elif commit_count >= self.ACTIVITY_THRESHOLDS["normal"]["commits_per_week"]:
            return "normal"
        else:
            return "idle"

    def get_recommended_interval(self, repo_path: Path) -> int:
        """Get the recommended scan interval for a repo based on its activity."""
        activity = self.assess_activity(repo_path)
        return self.ACTIVITY_THRESHOLDS[activity]["scan_interval_hours"]

    def get_activity_stats(self, repo_path: Path) -> dict:
        """Get detailed activity statistics for a repo."""
        result = subprocess.run(
            ["git", "log", "--oneline", "--since", "7 days ago"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        commit_count = len([l for l in lines if l])

        activity = self.assess_activity(repo_path)
        recommended = self.ACTIVITY_THRESHOLDS[activity]["scan_interval_hours"]

        return {
            "commits_last_7_days": commit_count,
            "activity": activity,
            "recommended_interval_hours": recommended,
            "threshold": self.ACTIVITY_THRESHOLDS[activity]["commits_per_week"],
        }

    def suggest_schedule(self) -> dict:
        """
        Generate scheduling suggestions for all configured repositories.
        Returns a dict mapping repo name to suggestion details.
        """
        suggestions = {}
        repositories = self.config.get("repositories", [])

        for repo in repositories:
            repo_path = Path(repo["path"]).expanduser().resolve()
            if not repo_path.exists():
                continue

            stats = self.get_activity_stats(repo_path)
            current_interval = repo.get("scan_interval_hours", 168)

            delta = stats["recommended_interval_hours"] - current_interval
            if delta > 0:
                action = "increase"
            elif delta < 0:
                action = "decrease"
            else:
                action = "maintain"

            suggestions[repo["path"]] = {
                "name": repo_path.name,
                "current_interval_hours": current_interval,
                "recommended_interval_hours": stats["recommended_interval_hours"],
                "activity": stats["activity"],
                "commits_last_7_days": stats["commits_last_7_days"],
                "action": action,
                "change_hours": delta,
            }

        return suggestions

    def apply_schedule(self, updates: dict[str, int]) -> dict:
        """
        Apply interval changes to config and save.
        updates: dict mapping repo path -> new interval hours
        Returns a summary dict.
        """
        from auto_evolve import load_config, save_config
        config = load_config()
        applied = []

        for repo in config.get("repositories", []):
            path = repo["path"]
            if path in updates:
                old = repo.get("scan_interval_hours", 168)
                repo["scan_interval_hours"] = updates[path]
                applied.append({
                    "path": path,
                    "old_interval": old,
                    "new_interval": updates[path],
                })

        save_config(config)
        return {"applied": applied}


# ===========================================================
# LLM Integration
# ===========================================================

def get_openclaw_llm_config() -> dict:
    """
    Read OpenClaw LLM configuration from environment, openclaw CLI, or models.json.
    Priority: env vars > models.json > openclaw config get llm
    """
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("MINIMAX_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("MINIMAX_BASE_URL", "")
    model = os.environ.get("OPENAI_MODEL") or os.environ.get("MINIMAX_MODEL", "MiniMax-M2")

    # Try openclaw config get llm (may not exist in all versions)
    try:
        result = subprocess.run(
            ["openclaw", "config", "get", "llm"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            cfg = json.loads(result.stdout)
            api_key = api_key or cfg.get("api_key", "")
            base_url = base_url or cfg.get("base_url", "")
            model = model or cfg.get("model", "MiniMax-M2")
    except Exception:
        pass

    # Fallback: read from agents/main/agent/models.json
    if not api_key or not base_url:
        models_file = HOME / ".openclaw" / "agents" / "main" / "agent" / "models.json"
        if models_file.exists():
            try:
                data = json.loads(models_file.read_text())
                providers = data.get("providers", {})
                # Try minimax provider first
                minimax = providers.get("minimax", {})
                if not api_key:
                    api_key = minimax.get("apiKey", "")
                if not base_url:
                    base_url = minimax.get("baseUrl", "")
                    if base_url:
                        # The baseUrl is like https://api.minimaxi.com/anthropic
                        # The /v1/messages suffix is added by _call_llm_for_refactor
                        base_url = base_url.rstrip("/")
                # Also try openai provider
                if not api_key:
                    openai = providers.get("openai", {})
                    api_key = openai.get("apiKey", "")
                if not base_url:
                    openai = providers.get("openai", {})
                    obu = openai.get("baseUrl", "")
                    if obu:
                        base_url = obu.rstrip("/") + "/chat/completions"
            except (json.JSONDecodeError, OSError):
                pass

    return {"api_key": api_key, "base_url": base_url, "model": model}


def call_llm(prompt: str, system: str = "", model: str = "", base_url: str = "", api_key: str = "") -> str:
    if not api_key or not base_url:
        return ""
    import urllib.request
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = json.dumps({"model": model or "MiniMax-M2", "messages": messages, "temperature": 0.3, "max_tokens": 16000}).encode("utf-8")
    try:
        req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception:
        return ""


def analyze_with_llm(code_snippet: str, context: str, repo_path: str = "") -> dict:
    config = get_openclaw_llm_config()
    if not config["api_key"] or not config["base_url"]:
        return {"suggestion": "", "risk_level": "medium", "implementation_hint": "", "available": False}
    lang = detect_language_from_path(repo_path)
    system = (
        "You are a senior product evolution advisor. "
        "Your job is NOT to review code quality — it is to ask the RIGHT questions about the product. "
        "When you see code, ask: "
        "  1. What is broken from a USER perspective (not developer)? "
        "  2. What would make a user say 'this is confusing' or 'why does this exist'? "
        "  3. What should we STOP doing? "
        "  4. What is missing that users secretly want but never ask for? "
        "  5. What is technically clever but practically useless? "
        "Return valid JSON with keys: "
        "  suggestion (a sharp, opinionated product question or stop-doing THIS, max 200 chars), "
        "  risk_level (low/medium/high), "
        "  implementation_hint (one concrete next step, max 100 chars), "
        "  category (one of: user_complaint | friction_point | unused_feature | competitive_gap | stop_doing | add_feature). "
        "Only JSON. Be brutally honest. Prefer 'stop doing X' over 'add more features'."
    )
    prompt = (
        "IMPORTANT: Answer with ONLY a JSON object. No explanation, no markdown fences.\n\n"
        "Code:\n```" + lang + "\n" + code_snippet[:2000] + "\n```\n\n"
        "Context: " + context + "\n\n"
        "Ask: what is really broken here? What should we stop, start, or question?"
    )
    result = call_llm(prompt=prompt, system=system, model=config["model"], base_url=config["base_url"], api_key=config["api_key"])
    if not result:
        return {"suggestion": "", "risk_level": "medium", "implementation_hint": "", "available": False, "category": "unknown"}
    try:
        parsed = json.loads(result)
        parsed["available"] = True
        if "category" not in parsed:
            parsed["category"] = "user_complaint"
        return parsed
    except json.JSONDecodeError:
        m = re.search(r'\{[^{}]*\}', result, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group())
                parsed["available"] = True
                if "category" not in parsed:
                    parsed["category"] = "user_complaint"
                return parsed
            except Exception:
                pass
        return {"suggestion": result.strip()[:200], "risk_level": "medium", "implementation_hint": "", "available": True, "category": "user_complaint"}


# ===========================================================
# LLM-Driven Code Optimization (v3.2)
# Implements true auto-execution of optimization findings.
# ===========================================================

import tempfile
import urllib.request


def _quality_check(file_path: str, code: str) -> tuple[bool, str]:
    """
    Validate that modified code passes syntax check.
    Writes code to a temp file and runs py_compile.
    Returns (passed, error_message).
    """
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=Path(file_path).suffix, delete=False
        ) as f:
            f.write(code)
            tmp_path = f.name
        result = subprocess.run(
            ["python3", "-m", "py_compile", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        os.unlink(tmp_path)
        if result.returncode == 0:
            return True, ""
        # Extract meaningful error
        stderr = result.stderr.strip()
        if not stderr and result.stdout:
            stderr = result.stdout.strip()
        return False, stderr[:300]
    except Exception as e:
        return False, str(e)[:200]


def _rollback_optimization(repo: Repository, file_path: str, before_hash: str) -> bool:
    """
    Rollback a file to its pre-modification state using git.
    Returns True if rollback succeeded.
    """
    try:
        subprocess.run(
            ["git", "checkout", before_hash, "--", file_path],
            cwd=str(repo.resolve_path()),
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _get_file_snapshot(repo: Repository, file_path: str) -> tuple[str, str]:
    """
    Get current file content and git hash before modification.
    Returns (content, git_hash). Empty string hash means file is not in git.
    """
    full_path = repo.resolve_path() / file_path
    try:
        content = full_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return "", ""
    try:
        result = subprocess.run(
            ["git", "hash-object", file_path],
            cwd=str(repo.resolve_path()),
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_hash = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        git_hash = ""
    return content, git_hash


def _call_llm_for_refactor(
    prompt: str,
    system: str,
    file_ext: str,
) -> str:
    """
    Call LLM to generate code refactor. Returns the refactored code string.
    Falls back to empty string on failure.
    """
    config = get_openclaw_llm_config()
    if not config.get("api_key") or not config.get("base_url"):
        return ""

    lang_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".go": "go", ".sh": "shell", ".java": "java",
    }
    lang = lang_map.get(file_ext.lower(), "text")

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + config["api_key"],
    }
    messages = (
        ([{"role": "system", "content": system}] if system else [])
        + [{"role": "user", "content": prompt}]
    )

    # Detect API type from base_url
    base_url = config["base_url"].rstrip("/")
    if "anthropic" in base_url or config.get("model", "").lower().startswith("minimax"):
        # Anthropic messages API
        body = {
            "model": config.get("model", "MiniMax-M2"),
            "messages": messages,
            "max_tokens": 16000,
            "temperature": 0.2,
        }
        endpoint = base_url + "/v1/messages"
    else:
        # OpenAI chat completions API
        body = {
            "model": config.get("model", "MiniMax-M2"),
            "messages": messages,
            "max_tokens": 16000,
            "temperature": 0.2,
        }
        endpoint = base_url + "/chat/completions"

    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # Parse response based on API type
            if "anthropic" in endpoint:
                # Anthropic/MiniMax response format: may contain 'thinking' and 'text' blocks
                # Prefer text blocks, but fall back to thinking blocks if no text
                text_blocks = [
                    b.get("text", "") for b in data.get("content", [])
                    if b.get("type") == "text" and b.get("text", "").strip()
                ]
                if text_blocks:
                    content = max(text_blocks, key=len)
                else:
                    # Fall back to thinking blocks — extract the thinking content
                    thinking_blocks = [
                        b.get("thinking", "") for b in data.get("content", [])
                        if b.get("type") == "thinking" and b.get("thinking", "").strip()
                    ]
                    content = "\n".join(thinking_blocks)
            else:
                # OpenAI response format
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
            # Strip markdown code fences if present
            return _strip_code_fences(content)
    except urllib.error.HTTPError as e:
        return ""
    except Exception:
        return ""


def _strip_code_fences(text: str) -> str:
    """Strip leading/trailing markdown code fences from LLM output."""
    lines = text.strip().split("\n")
    # Remove triple-backtick fences
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    content = "\n".join(lines).strip()

    # If content starts with natural language (not code), try to find a code block
    # This handles cases where LLM returns "Here's the refactored code:" followed by code
    non_code_starters = (
        "here", "this", "the", "i", "to", "after", "first", "you",
        "note", "let", "we", "of", "in", "for", "with", "that",
        "note:", "here's", "this ", "the function", "the code",
    )
    first_word = content.split()[0].lower() if content.split() else ""
    if first_word in non_code_starters or not first_word:
        # Try to find a code block pattern: lines that start with valid Python keywords
        code_indicators = ("def ", "class ", "import ", "from ", "if ", "else:", "return ", "for ", "while ", "async ", "@", "async def")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if any(stripped.startswith(ind) for ind in code_indicators):
                return "\n".join(lines[i:]).strip()

    return content


def _execute_todo_fixme(
    code: str,
    item: dict,
    repo_path: Path,
) -> tuple[str, str]:
    """
    Handle todo_fixme optimization: use LLM to analyze the TODO/FIXME
    and either remove it (if trivial), replace with explanation, or flag for manual review.
    Returns (new_code, result_description).
    """
    file_ext = Path(item["file_path"]).suffix
    lang = {"py": "python", "js": "javascript", "ts": "typescript", "go": "go"}.get(
        file_ext.lstrip("."), "text"
    )
    line_info = f"Line {item['line']}: {item['description']}"

    system = (
        f"You are a code refactoring assistant. You work with {lang} code only.\n"
        "Rules:\n"
        "1. If the TODO/FIXME is trivial (e.g. spelling, formatting, outdated note), remove it.\n"
        "2. If it references an issue that is already resolved, remove it.\n"
        "3. If it is a genuine future task, replace the TODO with a brief inline comment explaining status.\n"
        "4. NEVER fabricate functionality — only clean up existing annotations.\n"
        "5. Return ONLY the complete modified file content. No markdown fences, no explanations.\n"
        "6. Preserve all code exactly; only modify the TODO/FIXME lines.\n"
    )
    prompt = (
        f"File: {item['file_path']}\n"
        f"Issue: {line_info}\n\n"
        f"Original code:\n```{lang}\n{code}\n```\n\n"
        "Apply the cleanup rule and return the complete modified file."
    )

    new_code = _call_llm_for_refactor(prompt, system, file_ext)
    if not new_code:
        return "", "LLM call failed or no API key"
    return new_code, "todo_fixme resolved"


def _execute_duplicate_code(
    code: str,
    item: dict,
    repo_path: Path,
) -> tuple[str, str]:
    """
    Handle duplicate_code optimization: use LLM to detect the repeated pattern
    and refactor by extracting it into a constant or helper function.
    Returns (new_code, result_description).
    """
    file_ext = Path(item["file_path"]).suffix
    lang = {"py": "python", "js": "javascript", "ts": "typescript", "go": "go"}.get(
        file_ext.lstrip("."), "text"
    )
    desc = item.get("description", "")

    system = (
        f"You are a code refactoring assistant. You work with {lang} only.\n"
        "Task: eliminate duplicate code by extracting repeated patterns into constants or helpers.\n"
        "Rules:\n"
        "1. Find the duplicate pattern described.\n"
        "2. Replace repeated occurrences with a constant or small helper function.\n"
        "3. Preserve all functionality exactly.\n"
        "4. Return ONLY the complete modified file content. No markdown fences.\n"
        "5. If the duplication is incidental (not worth extracting), still clean it minimally.\n"
    )
    prompt = (
        f"File: {item['file_path']}\n"
        f"Finding: {desc}\n\n"
        f"Current code:\n```{lang}\n{code}\n```\n\n"
        "Refactor to eliminate duplication. Return complete file."
    )

    new_code = _call_llm_for_refactor(prompt, system, file_ext)
    if not new_code:
        return "", "LLM call failed or no API key"
    return new_code, "duplicate pattern refactored"


def _execute_long_function(
    code: str,
    item: dict,
    repo_path: Path,
) -> tuple[str, str]:
    """
    Handle long_function optimization: use LLM to split a function >100 lines
    into smaller, focused sub-functions.
    Returns (new_code, result_description).
    """
    file_ext = Path(item["file_path"]).suffix
    lang = {"py": "python", "js": "javascript", "ts": "typescript", "go": "go"}.get(
        file_ext.lstrip("."), "text"
    )
    desc = item.get("description", "")

    system = (
        f"You are a code refactoring assistant. You work with {lang} only.\n"
        "Task: Split an oversized function (>100 lines) into smaller, focused functions.\n"
        "Rules:\n"
        "1. Identify logical sections within the function that can be extracted.\n"
        "2. Create helper functions with clear, descriptive names.\n"
        "3. Preserve the original function signature and all side effects.\n"
        "4. Keep the code readable and maintainable.\n"
        "5. Return ONLY the complete modified file. No markdown fences.\n"
        "6. Do NOT change any logic — only restructure.\n"
    )
    prompt = (
        f"File: {item['file_path']}\n"
        f"Finding: {desc}\n\n"
        f"Current code:\n```{lang}\n{code}\n```\n\n"
        "Split the long function into smaller functions. Return complete file."
    )

    new_code = _call_llm_for_refactor(prompt, system, file_ext)
    if not new_code:
        return "", "LLM call failed or no API key"
    return new_code, "long function refactored"


def _execute_missing_test(
    code: str,
    item: dict,
    repo_path: Path,
) -> tuple[str, str]:
    """
    Handle missing_test optimization: generate a basic test file for an untested module.
    Since we can't write a new file from an optimization finding (no file path given),
    this generates test stubs in a string for manual use or writes to tests/ directory.
    Returns (generated_test_code, result_description).
    """
    desc = item.get("description", "")
    # missing_test often has file_path="." meaning root-level scan
    # Generate test stubs based on the module structure
    file_ext = Path(item.get("file_path", "test.py")).suffix or ".py"
    lang = {"py": "python"}.get(file_ext.lstrip("."), "python")

    system = (
        "You are a testing assistant. Generate pytest-compatible test stubs.\n"
        "Rules:\n"
        "1. Create a test file with imports matching the module structure.\n"
        "2. Add placeholder test functions with pass (one per public function).\n"
        "3. Include basic assert checks where logic is obvious.\n"
        "4. Return ONLY the complete test file content. No markdown fences.\n"
    )
    prompt = (
        f"Finding: {desc}\n\n"
        "Generate a test file for the untested modules. "
        "Use pytest conventions (test_ prefix). Return complete file content."
    )

    new_code = _call_llm_for_refactor(prompt, system, ".py")
    if not new_code:
        return "", "LLM call failed or no API key"
    return new_code, "test stubs generated"


def _execute_outdated_dep(
    code: str,
    item: dict,
    repo_path: Path,
) -> tuple[str, str]:
    """
    Handle outdated_dep optimization: replace pinned version with semver range.
    Returns (new_code, result_description).
    """
    import re as _re

    desc = item.get("description", "")
    # Extract package name from the line
    match = _re.search(r"^([a-zA-Z0-9_-]+)[=<>!]+", desc, _re.MULTILINE)
    if not match:
        return "", "Could not parse package name"

    new_code = _re.sub(
        r"([a-zA-Z0-9_-]+)==[\d.]+",
        r"\1>=1.0.0,<2.0.0",
        code,
    )
    if new_code == code:
        return "", "No change needed or pattern not matched"
    return new_code, "pinned dep converted to semver range"


def execute_optimization(
    item: dict,
    code: str,
    repo: Repository,
) -> tuple[str, str]:
    """
    Main dispatcher for LLM-driven optimization execution.

    Args:
        item: Optimization finding dict with keys: type, file_path, line, description, suggestion, risk
        code: Current file content
        repo: Repository object

    Returns:
        (new_code, result_msg). Empty new_code means execution failed or was skipped.
    """
    opt_type = item.get("type") or item.get("optimization_type", "")

    if opt_type == "todo_fixme":
        return _execute_todo_fixme(code, item, repo.resolve_path())

    elif opt_type == "duplicate_code":
        return _execute_duplicate_code(code, item, repo.resolve_path())

    elif opt_type == "long_function":
        return _execute_long_function(code, item, repo.resolve_path())

    elif opt_type == "missing_test":
        return _execute_missing_test(code, item, repo.resolve_path())

    elif opt_type == "outdated_dep":
        return _execute_outdated_dep(code, item, repo.resolve_path())

    else:
        return "", f"Unknown optimization type: {opt_type}"


@dataclass
class OptimizationResult:
    """Result of executing a single optimization."""
    item_id: int
    file_path: str
    opt_type: str
    success: bool
    new_code: str = ""
    result_msg: str = ""
    before_hash: str = ""
    quality_passed: bool = False
    quality_error: str = ""


def _auto_execute_optimizations(
    all_changes: list[ChangeItem],
    all_opts: list[OptimizationFinding],
    mode: OperationMode,
    rules: dict,
    dry_run: bool,
) -> tuple[list[ChangeItem], dict]:
    """
    Execute optimization findings in full-auto mode using LLM-driven code modification.

    In full-auto mode with rules permitting the risk level, each optimization is:
      1. Loaded from disk
      2. Sent to LLM for refactoring
      3. Validated with py_compile
      4. Written back to disk on success
      5. Git-committed

    Returns (executed_change_items, stats_dict).
    """
    executed: list[ChangeItem] = []
    stats: dict = {
        "total": 0,
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped_llm": 0,
        "quality_failed": 0,
        "by_type": {},
    }

    if mode != OperationMode.FULL_AUTO or dry_run:
        # In dry-run or non-full-auto, just report what would be executed
        executable_opts = [
            c for c in all_changes
            if c.category == ChangeCategory.OPTIMIZATION
            and should_auto_execute(rules, c.risk)
        ]
        stats["total"] = len(executable_opts)
        stats["attempted"] = 0
        if executable_opts:
            print(f"\n⚡ Full-auto would execute {len(executable_opts)} optimization(s):")
            for c in executable_opts[:10]:
                print(f"   [{c.id}] {c.optimization_type}: {c.description[:60]}")
            if len(executable_opts) > 10:
                print(f"   ... and {len(executable_opts) - 10} more")
        return [], stats

    # Full-auto mode: actually execute
    optimization_changes = [
        c for c in all_changes
        if c.category == ChangeCategory.OPTIMIZATION
        and should_auto_execute(rules, c.risk)
    ]
    stats["total"] = len(optimization_changes)

    if not optimization_changes:
        return [], stats

    print(f"\n⚡ Executing {len(optimization_changes)} optimization(s) in full-auto mode:")

    for change_item in optimization_changes:
        opt_type = change_item.optimization_type or "unknown"
        # Track by type
        stats["by_type"][opt_type] = stats["by_type"].get(opt_type, 0) + 1
        stats["attempted"] += 1

        repo = Repository(path=change_item.repo_path, type=change_item.repo_type)
        repo_path = repo.resolve_path()
        file_path = change_item.file_path

        # Skip directories and non-code files
        full_path = repo_path / file_path
        if full_path.is_dir():
            stats["skipped_llm"] += 1
            continue
        ext = Path(file_path).suffix.lower()
        if ext not in LANGUAGE_EXTENSIONS and ext != ".md":
            stats["skipped_llm"] += 1
            continue

        # Load current content
        try:
            code = full_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            print(f"  ❌ [{change_item.id}] {file_path}: cannot read file ({e})")
            stats["failed"] += 1
            continue

        # Snapshot before modification for rollback
        _, before_hash = _get_file_snapshot(repo, file_path)

        # Build finding-style dict for execute_optimization
        finding_dict: dict = {
            "type": opt_type,
            "file_path": file_path,
            "line": 0,
            "description": change_item.description,
            "suggestion": "",
            "risk": change_item.risk.value,
        }

        # Execute LLM-driven optimization
        try:
            new_code, result_msg = execute_optimization(finding_dict, code, repo)
        except Exception as e:
            print(f"  ❌ [{change_item.id}] {file_path}: LLM execution error ({e})")
            stats["failed"] += 1
            continue

        if not new_code:
            print(f"  ⏭️  [{change_item.id}] {file_path}: {result_msg or 'no LLM output'}")
            stats["skipped_llm"] += 1
            continue

        # Skip if no actual change was made
        if new_code.strip() == code.strip():
            print(f"  ⏭️  [{change_item.id}] {file_path}: no change produced")
            stats["skipped_llm"] += 1
            continue

        # Quality gate: py_compile check
        quality_ok, quality_err = _quality_check(file_path, new_code)
        if not quality_ok:
            print(f"  ❌ [{change_item.id}] {file_path}: quality gate failed — {quality_err[:80]}")
            stats["quality_failed"] += 1
            stats["failed"] += 1
            continue

        # Write the optimized code back
        try:
            full_path.write_text(new_code, encoding="utf-8")
        except OSError as e:
            print(f"  ❌ [{change_item.id}] {file_path}: write failed ({e})")
            # Rollback
            if before_hash:
                _rollback_optimization(repo, file_path, before_hash)
            stats["failed"] += 1
            continue

        # Git commit (truncate message safely to avoid UTF-8 cutting)
        commit_msg = f"auto: {opt_type} — {change_item.description}"
        commit_msg_bytes = commit_msg.encode("utf-8")[:72].decode("utf-8", errors="ignore")
        try:
            commit_hash = git_commit(repo, commit_msg_bytes)
        except Exception as e:
            print(f"  ❌ [{change_item.id}] {file_path}: git commit failed ({e})")
            # Rollback on commit failure
            if before_hash:
                _rollback_optimization(repo, file_path, before_hash)
            stats["failed"] += 1
            continue

        # Success
        change_item.commit_hash = commit_hash
        executed.append(change_item)
        stats["succeeded"] += 1
        print(f"  ✅ [{change_item.id}] {opt_type} {file_path} ({commit_hash[:7]})")

    # Summary
    print(
        f"\n  Optimization execution: {stats['succeeded']}/{stats['attempted']} succeeded "
        f"(skipped_llm={stats['skipped_llm']}, quality_failed={stats['quality_failed']})"
    )
    return executed, stats


# ===========================================================
# Multi-Language Support
# ===========================================================

def detect_language_from_path(path: str) -> str:
    return LANGUAGE_EXTENSIONS.get(Path(path).suffix.lower(), "text")


def detect_repo_languages(repo_path: Path) -> set[str]:
    langs: set[str] = set()
    for ext in LANGUAGE_EXTENSIONS:
        if any(repo_path.rglob("*" + ext)):
            langs.add(ext)
    return langs


def get_todo_patterns_for_file(file_path: str) -> list[str]:
    return TODO_PATTERNS.get(Path(file_path).suffix.lower(), ["# TODO"])


def scan_todos_multilang(repo: Repository) -> list[OptimizationFinding]:
    findings = []
    repo_path = repo.resolve_path()
    for ext in LANGUAGE_EXTENSIONS:
        for file_path in repo_path.rglob("*" + ext):
            if any(s in str(file_path) for s in (".git", "__pycache__", "node_modules", ".iterations")):
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            lang_pats = TODO_PATTERNS.get(ext, ["# TODO"])
            for i, line in enumerate(content.split("\n"), 1):
                for pat in lang_pats:
                    if pat in line:
                        idx = line.find(pat)
                        findings.append(OptimizationFinding(
                            type="todo_fixme",
                            file_path=str(file_path.relative_to(repo_path)),
                            line=i,
                            description="Unresolved: " + line[idx:].strip()[:80],
                            suggestion="Address or document this annotation",
                            risk=RiskLevel.LOW,
                        ))
                        break
    return findings


# ===========================================================
# Dependency Analysis
# ===========================================================

def extract_imports(content: str, file_path: str) -> list[str]:
    ext = Path(file_path).suffix.lower()
    imports: list[str] = []
    if ext == ".py":
        for m in re.finditer(r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", content, re.MULTILINE):
            imports.append((m.group(1) or m.group(2)).split(".")[0])
    elif ext in (".js", ".ts"):
        for m in re.finditer(r"(?:require\s*\(\s*[\"']([^\"']+)[\"']\s*\)|import\s+.*?\s+from\s+[\"']([^\"']+)[\"'])", content):
            imp = m.group(1) or m.group(2)
            if imp and not imp.startswith("."):
                imports.append(imp.split("/")[0])
    elif ext == ".go":
        for m in re.finditer(r'import\s+"([^"]+)"', content):
            imports.append(m.group(1).split("/")[-1])
    elif ext == ".java":
        for m in re.finditer(r"import\s+([\w.]+);", content):
            imports.append(m.group(1).split(".")[-1])
    return imports


def build_dependency_map(repo_path: Path) -> dict[str, list[str]]:
    dep_map: dict[str, list[str]] = {}
    for ext in LANGUAGE_EXTENSIONS:
        for fp in repo_path.rglob("*" + ext):
            if any(s in str(fp) for s in (".git", "__pycache__", "node_modules")):
                continue
            try:
                dep_map[str(fp.relative_to(repo_path))] = extract_imports(
                    fp.read_text(encoding="utf-8"), str(fp)
                )
            except (UnicodeDecodeError, OSError):
                pass
    return dep_map


def find_dependents(target_file: str, dep_map: dict[str, list[str]]) -> list[str]:
    target_base = Path(target_file).stem
    return [fp for fp, imps in dep_map.items() if target_base in imps]


def analyze_dependencies(repo: Repository, changed_files: list[str]) -> dict[str, list[str]]:
    repo_path = repo.resolve_path()
    dep_map = build_dependency_map(repo_path)
    affected: dict[str, list[str]] = {}
    for changed in changed_files:
        deps = find_dependents(changed, dep_map)
        if deps:
            affected[changed] = deps
    return affected


# ===========================================================
# Test Comparison
# ===========================================================

def run_tests_for_hash(repo: Repository, ref: str) -> dict:
    repo_path = str(repo.resolve_path())
    if subprocess.run(["which", "pytest"], capture_output=True).returncode != 0:
        return {"passed": None, "coverage": None, "duration": 0.0, "error": "pytest not found"}
    subprocess.run(["git", "stash", "-q"], cwd=repo_path)
    try:
        subprocess.run(["git", "checkout", "-q", ref], cwd=repo_path)
        start = time.time()
        r = subprocess.run(["pytest", "--tb=short", "-q"], cwd=repo_path, capture_output=True, text=True, timeout=120)
        dur = time.time() - start
        passed = r.returncode == 0
        cov = None
        cr = Path(repo_path) / "coverage.xml"
        if cr.exists():
            txt = cr.read_text()
            m = re.search(r'line-rate="([0-9.]+)"', txt)
            if m:
                cov = float(m.group(1)) * 100
        return {"passed": passed, "coverage": cov, "duration": dur, "error": None}
    except subprocess.TimeoutExpired:
        return {"passed": False, "coverage": None, "duration": 120.0, "error": "timeout"}
    except Exception as e:
        return {"passed": False, "coverage": None, "duration": 0.0, "error": str(e)}
    finally:
        subprocess.run(["git", "checkout", "-q", "-"], cwd=repo_path)
        subprocess.run(["git", "stash", "pop", "-q"], cwd=repo_path)


def run_test_comparison(repo: Repository, before_hash: str, after_hash: str) -> dict:
    before = run_tests_for_hash(repo, before_hash)
    after = run_tests_for_hash(repo, after_hash)
    delta = None
    if before.get("coverage") is not None and after.get("coverage") is not None:
        delta = round(after["coverage"] - before["coverage"], 2)
    return {
        "before_coverage": before.get("coverage"),
        "after_coverage": after.get("coverage"),
        "delta": delta,
        "before_passed": before.get("passed"),
        "after_passed": after.get("passed"),
        "before_duration": before.get("duration", 0.0),
        "after_duration": after.get("duration", 0.0),
        "tests_passed": after.get("passed", False),
    }


# ===========================================================
# Contributor Tracking
# ===========================================================

def track_contributors(repo: Repository) -> dict:
    r = subprocess.run(
        ["git", "log", "--pretty=format:%H|%s|%ad", "--date=iso"],
        cwd=str(repo.resolve_path()),
        capture_output=True,
        text=True,
        timeout=10,
    )
    total = auto_count = manual_count = 0
    last_manual = None
    for line in r.stdout.strip().split("\n"):
        if not line:
            continue
        total += 1
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        msg, date = parts[1], parts[2] if len(parts) > 2 else ""
        if msg.startswith("auto:") or msg.startswith("auto-evolve:"):
            auto_count += 1
        else:
            manual_count += 1
            if date and (last_manual is None or date > last_manual):
                last_manual = date.split()[0]
    return {
        "total_commits": total,
        "auto_commits": auto_count,
        "manual_commits": manual_count,
        "auto_percentage": round((auto_count / total) * 100, 1) if total else 0.0,
        "last_manual_commit": last_manual,
    }


# ===========================================================
# Release Management
# ===========================================================

def create_release(repo: Repository, version: str, changelog: str = "") -> None:
    repo_path = repo.resolve_path()
    tag = "v" + version.lstrip("v")
    subprocess.run(["git", "tag", tag, "-m", "Release " + version.lstrip("v")], cwd=str(repo_path), check=True)
    subprocess.run(["git", "push", "origin", tag], cwd=str(repo_path), check=True)
    r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(repo_path), capture_output=True, text=True)
    m = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", r.stdout.strip())
    if not m:
        print("Tag " + tag + " created and pushed.")
        return
    slug = m.group(1)
    notes = "# Release " + version.lstrip("v") + "\n\n" + changelog + "\n\n## auto-evolve\nManaged by auto-evolve.\n"
    gr = subprocess.run(
        ["gh", "release", "create", tag, "--title", tag, "--notes", notes, "--repo", slug],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if gr.returncode == 0:
        print("Release " + tag + " created: " + gr.stdout.strip())
    else:
        print("Tag " + tag + " created. gh failed: " + gr.stderr.strip())


# ===========================================================
# Priority Calculation
# ===========================================================

def infer_value_score(item: ChangeItem) -> int:
    """Infer value score (1-10) from change type and description."""
    desc_lower = item.description.lower()
    opt_type = (item.optimization_type or "").lower()

    if "bug" in desc_lower or "fix" in desc_lower:
        return DEFAULT_VALUE_SCORES["bug_fix"]
    if opt_type == "todo_fixme":
        return DEFAULT_VALUE_SCORES["todo_fixme"]
    if opt_type == "missing_test":
        return DEFAULT_VALUE_SCORES["add_test"]
    if opt_type == "long_function":
        return DEFAULT_VALUE_SCORES["refactor"]
    if opt_type == "duplicate_code":
        return DEFAULT_VALUE_SCORES["optimization"]
    if opt_type == "outdated_dep":
        return DEFAULT_VALUE_SCORES["optimization"]
    if "test" in desc_lower:
        return DEFAULT_VALUE_SCORES["add_test"]
    if any(kw in desc_lower for kw in ("readme", "changelog", "docs")):
        return DEFAULT_VALUE_SCORES["docs"]
    if "lint" in desc_lower or "format" in desc_lower:
        return DEFAULT_VALUE_SCORES["lint_fix"]
    return 5


def infer_risk_score(risk: RiskLevel) -> int:
    mapping = {RiskLevel.LOW: 2, RiskLevel.MEDIUM: 5, RiskLevel.HIGH: 9}
    return mapping.get(risk, 5)


def infer_cost_score(item: ChangeItem) -> int:
    desc_lower = item.description.lower()
    file_path = item.file_path.lower()
    if any(kw in desc_lower for kw in ("todo", "fixme", "lint", "format", "typo")):
        return 1
    if any(ext in file_path for ext in (".md", ".txt", ".rst")):
        if "readme" in file_path or "changelog" in file_path:
            return 2
        return 1
    if "test" in file_path or "_test." in file_path:
        return 3
    num_files = desc_lower.count(",") + 1
    if num_files <= 2:
        return 4
    elif num_files <= 5:
        return 6
    return 8


def calculate_priority(item: ChangeItem) -> float:
    value = item.value_score
    risk = item.risk_score
    cost = item.cost_score
    if risk * cost == 0:
        return 0.0
    return round((value * PRIORITY_WEIGHTS["value"]) / (risk * cost), 3)


def enrich_change_with_priority(item: ChangeItem) -> ChangeItem:
    item.value_score = infer_value_score(item)
    item.risk_score = infer_risk_score(item.risk)
    item.cost_score = infer_cost_score(item)
    item.priority = calculate_priority(item)
    return item


def sort_by_priority(items: list[ChangeItem]) -> list[ChangeItem]:
    return sorted(items, key=lambda x: x.priority, reverse=True)


def priority_color(p: float) -> str:
    if p >= 0.7:
        return "🟢"
    elif p >= 0.4:
        return "🟡"
    return "🔴"


# ===========================================================
# Config Management
# ===========================================================

def load_config() -> dict:
    if AUTO_EVOLVE_RC.exists():
        return json.loads(AUTO_EVOLVE_RC.read_text())
    return get_default_config()


def save_config(config: dict) -> None:
    AUTO_EVOLVE_RC.parent.mkdir(parents=True, exist_ok=True)
    AUTO_EVOLVE_RC.write_text(json.dumps(config, indent=2))


def get_default_config() -> dict:
    return {
        "mode": "semi-auto",
        "full_auto_rules": {
            "execute_low_risk": True,
            "execute_medium_risk": False,
            "execute_high_risk": False,
        },
        "semi_auto_rules": {
            "notify_on_each_scan": True,
            "require_confirm_before_execute": True,
        },
        "schedule_interval_hours": 168,
        "schedule_cron_id": None,
        "repositories": [
            {
                "path": str(HOME / ".openclaw" / "workspace" / "skills" / "soul-force"),
                "type": "skill",
                "visibility": "public",
                "auto_monitor": True,
            }
        ],
        "notification": {
            "mode": "log",
            "log_file": str(HOME / ".auto-evolve-notifications.log"),
        },
        "git": {
            "remote": "origin",
            "branch": "main",
            "pr_branch_prefix": "auto-evolve",
        },
    }


def config_to_repos(config: dict) -> list[Repository]:
    repos: list[Repository] = []
    for r in config.get("repositories", []):
        repos.append(Repository(
            path=r["path"],
            type=r.get("type", "skill"),
            visibility=r.get("visibility", "public"),
            auto_monitor=r.get("auto_monitor", True),
            risk_override=r.get("risk_override"),
            scan_interval_hours=r.get("scan_interval_hours", 168),
        ))
    return repos


def repos_to_config(repos: list[Repository], config: dict) -> dict:
    config["repositories"] = [
        {
            "path": r.path,
            "type": r.type,
            "visibility": r.visibility,
            "auto_monitor": r.auto_monitor,
            "risk_override": r.risk_override,
            "scan_interval_hours": r.scan_interval_hours,
        }
        for r in repos
    ]
    return config


def get_operation_mode(config: dict) -> OperationMode:
    mode_str = config.get("mode", "semi-auto")
    try:
        return OperationMode(mode_str)
    except ValueError:
        return OperationMode.SEMI_AUTO


def get_full_auto_rules(config: dict) -> dict:
    return config.get("full_auto_rules", {
        "execute_low_risk": True,
        "execute_medium_risk": False,
        "execute_high_risk": False,
    })


def should_auto_execute(rules: dict, risk: RiskLevel) -> bool:
    if risk == RiskLevel.LOW:
        return rules.get("execute_low_risk", True)
    elif risk == RiskLevel.MEDIUM:
        return rules.get("execute_medium_risk", False)
    elif risk == RiskLevel.HIGH:
        return rules.get("execute_high_risk", False)
    return False


# ===========================================================
# Learning History
# ===========================================================

def ensure_learnings_dir() -> Path:
    LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    return LEARNINGS_DIR


def load_learnings() -> dict:
    ensure_learnings_dir()
    rejections_file = LEARNINGS_DIR / "rejections.json"
    approvals_file = LEARNINGS_DIR / "approvals.json"

    data: dict = {"rejections": [], "approvals": []}

    if rejections_file.exists():
        try:
            data["rejections"] = json.loads(rejections_file.read_text()).get("rejections", [])
        except (json.JSONDecodeError, OSError):
            data["rejections"] = []

    if approvals_file.exists():
        try:
            data["approvals"] = json.loads(approvals_file.read_text()).get("approvals", [])
        except (json.JSONDecodeError, OSError):
            data["approvals"] = []

    return data


def save_learnings(data: dict) -> None:
    ensure_learnings_dir()
    rejections_file = LEARNINGS_DIR / "rejections.json"
    approvals_file = LEARNINGS_DIR / "approvals.json"
    rejections_file.write_text(json.dumps({"rejections": data.get("rejections", [])}, indent=2))
    approvals_file.write_text(json.dumps({"approvals": data.get("approvals", [])}, indent=2))


def add_learning(
    learning_type: str,
    change_id: str,
    description: str,
    reason: Optional[str],
    repo: str,
    approved_by: Optional[str] = None,
) -> None:
    data = load_learnings()
    entry: dict = {
        "id": hashlib.sha256(
            f"{change_id}{description}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12],
        "type": learning_type,
        "change_id": str(change_id),
        "description": description,
        "reason": reason,
        "date": datetime.now(timezone.utc).date().isoformat(),
        "repo": repo,
    }
    if learning_type == "approval" and approved_by:
        entry["approved_by"] = approved_by

    if learning_type == "rejection":
        data["rejections"].insert(0, entry)
    else:
        data["approvals"].insert(0, entry)

    save_learnings(data)


def is_rejected(change_desc: str, repo: str, learnings: dict) -> bool:
    for rej in learnings.get("rejections", []):
        if rej.get("repo") == repo and rej.get("description") == change_desc:
            return True
    return False


# ===========================================================
# Git Operations
# ===========================================================

def git_run(repo: Repository, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git"] + list(args),
        cwd=str(repo.resolve_path()),
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"Git command failed: git {' '.join(args)}\n{result.stderr}")
    return result


def git_status(repo: Repository) -> list[dict]:
    result = git_run(repo, "status", "--porcelain")
    if not result.stdout.strip():
        return []

    changes: list[dict] = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        status_code = line[:2]
        file_path = line[3:].strip()
        if status_code == "??":
            change_type = "untracked"
        elif status_code == "DD":
            change_type = "deleted"
        elif "D" in status_code:
            change_type = "removed"
        elif "A" in status_code:
            change_type = "added"
        else:
            change_type = "modified"
        changes.append({"type": change_type, "file": file_path})
    return changes


def git_current_branch(repo: Repository) -> str:
    result = git_run(repo, "branch", "--show-current")
    return result.stdout.strip()


def git_commit(repo: Repository, message: str) -> str:
    git_run(repo, "add", ".")
    # Check if there are staged changes before committing
    status_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(repo.resolve_path()),
        capture_output=True,
    )
    if status_result.returncode != 0:
        # There are staged changes, commit them
        git_run(repo, "commit", "-m", message)
    else:
        # Nothing to commit, skip
        pass
    hash_result = git_run(repo, "rev-parse", "--short", "HEAD")
    return hash_result.stdout.strip()


def git_push(repo: Repository, remote: str = "origin", branch: Optional[str] = None) -> None:
    branch = branch or git_current_branch(repo)
    git_run(repo, "push", "-u", remote, branch)


def git_create_branch(repo: Repository, branch_name: str) -> None:
    git_run(repo, "checkout", "-b", branch_name)


def git_revert(repo: Repository, ref: str) -> str:
    git_run(repo, "revert", "--no-edit", ref)
    hash_result = git_run(repo, "rev-parse", "--short", "HEAD")
    return hash_result.stdout.strip()


def git_log(repo: Repository, limit: int = 50) -> list[dict]:
    result = git_run(repo, "log", "--pretty=format:%H|%s|%ad", "--date=iso", f"-n{limit}")
    commits: list[dict] = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"hash": parts[0], "message": parts[1], "date": parts[2]})
    return commits


def git_diff(repo: Repository, ref: Optional[str] = None) -> str:
    if ref:
        result = git_run(repo, "diff", "--stat", ref)
    else:
        result = git_run(repo, "diff", "--stat")
    return result.stdout


def compute_file_hash(repo: Repository, file_path: str) -> Optional[str]:
    try:
        full_path = repo.resolve_path() / file_path
        if full_path.exists():
            h = hashlib.sha256()
            h.update(full_path.read_bytes())
            return h.hexdigest()[:12]
    except OSError:
        pass
    return None


def git_diff_lines_added_removed(repo: Repository) -> tuple[int, int]:
    try:
        result = git_run(repo, "diff", "--numstat", "HEAD")
        lines_added = 0
        lines_removed = 0
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                try:
                    added = int(parts[0]) if parts[0] != "-" else 0
                    removed = int(parts[1]) if parts[1] != "-" else 0
                    lines_added += added
                    lines_removed += removed
                except ValueError:
                    pass
        return lines_added, lines_removed
    except Exception:
        return 0, 0


def get_conflict_files(repo_path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().split("\n") if f]


def resolve_conflicts_simple(repo_path: Path, conflict_files: list[str]) -> None:
    for f in conflict_files:
        subprocess.run(["git", "checkout", "--theirs", f], cwd=str(repo_path), capture_output=True)
        subprocess.run(["git", "add", f], cwd=str(repo_path), capture_output=True)


def handle_pr_conflict(repo: Repository, branch: str) -> str:
    try:
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=str(repo.resolve_path()),
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            ["git", "rebase", "origin/main"],
            cwd=str(repo.resolve_path()),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return "clean"

        conflict_files = get_conflict_files(repo.resolve_path())
        if len(conflict_files) <= 2:
            resolve_conflicts_simple(repo.resolve_path(), conflict_files)
            cont_result = subprocess.run(
                ["git", "rebase", "--continue"],
                cwd=str(repo.resolve_path()),
                capture_output=True,
                text=True,
            )
            if cont_result.returncode == 0:
                return "auto_resolved"

        return "manual_required"
    except Exception:
        return "manual_required"


# ===========================================================
# Risk Classification
# ===========================================================

def classify_change(repo: Repository, change_type: str, file_path: str) -> RiskLevel:
    default_risk = repo.get_default_risk(change_type, file_path)
    file_lower = file_path.lower()

    high_risk_patterns = ["remove", "delete", "deprecate", "break", "rename", "migrate", "architect", "security"]
    if any(p in file_lower for p in high_risk_patterns):
        return RiskLevel.HIGH

    low_risk_patterns = ["readme", "skill.md", "changelog", ".gitignore", "license", "comments", "typo", "format", "lint", "refactor", "rename"]
    if change_type == "removed":
        if any(p in file_lower for p in ["__init__", "config", "core"]):
            return RiskLevel.HIGH
        return default_risk

    if any(p in file_lower for p in low_risk_patterns):
        return RiskLevel.LOW

    return default_risk


# ===========================================================
# Optimization Scanner
# ===========================================================

ANNOTATION_PATTERN = re.compile(r"(\b(TODO|FIXME|XXX|HACK|NOTE)\b.*?)$", re.IGNORECASE | re.MULTILINE)
PINNED_VERSION = re.compile(r"==\d+\.\d+\.\d+")


def scan_optimizations(repo: Repository) -> list[OptimizationFinding]:
    findings = []
    repo_path = repo.resolve_path()
    findings.extend(scan_todos_multilang(repo))
    for py_file in repo_path.rglob("*.py"):
        rel_path = py_file.relative_to(repo_path)
        findings.extend(_scan_python_file(py_file, rel_path))
    for ext in ("*.js", "*.ts", "*.go"):
        for code_file in repo_path.rglob(ext):
            rel_path = code_file.relative_to(repo_path)
            findings.extend(_scan_code_file(code_file, rel_path))
    findings.extend(_scan_test_coverage(repo_path, repo_path))
    findings.extend(_scan_dependencies(repo_path))
    return findings


def _scan_python_file(py_file: Path, rel_path: Path) -> list[OptimizationFinding]:
    findings = []
    try:
        content = py_file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return findings
    findings.extend(_scan_annotations(py_file, rel_path, content=content))
    findings.extend(_scan_duplicate_code(content, rel_path))
    findings.extend(_scan_long_functions(content, rel_path))
    return findings


def _scan_annotations(file_path: Path, rel_path: Path, content: Optional[str] = None) -> list[OptimizationFinding]:
    findings = []
    if content is None:
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return findings
    for i, line in enumerate(content.split("\n"), 1):
        if ANNOTATION_PATTERN.search(line):
            findings.append(OptimizationFinding(
                type="todo_fixme",
                file_path=str(rel_path),
                line=i,
                description=f"Unresolved annotation: {line.strip()}",
                suggestion="Address or document this TODO/FIXME/XXX",
                risk=RiskLevel.LOW,
            ))
    return findings


def _scan_code_file(code_file: Path, rel_path: Path) -> list[OptimizationFinding]:
    findings = []
    try:
        content = code_file.read_text(encoding="utf-8")
    except Exception:
        return findings
    lines = content.split("\n")
    open_braces = 0
    func_start = 0
    in_func = False
    func_name = ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"(?:export\s+)?(?:async\s+)?function\s+\w+", stripped):
            m = re.search(r"function\s+(\w+)", stripped)
            func_name = m.group(1) if m else "anon"
            func_start = i
            in_func = True
            open_braces = 0
        elif re.match(r"(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?\(", stripped):
            m = re.search(r"(?:const|let|var)\s+(\w+)", stripped)
            func_name = m.group(1) if m else "anon"
            func_start = i
            in_func = True
            open_braces = 0
        elif re.match(r"func\s+\w+", stripped):
            m = re.search(r"func\s+(\w+)", stripped)
            func_name = m.group(1) if m else "anon"
            func_start = i
            in_func = True
            open_braces = 0
        if in_func:
            open_braces += stripped.count("{") - stripped.count("}")
            if open_braces <= 0 and "{" in stripped:
                func_lines = i - func_start + 1
                if func_lines > 100:
                    findings.append(OptimizationFinding(
                        type="long_function",
                        file_path=str(rel_path),
                        line=func_start + 1,
                        description=f"Function [{func_name}] is {func_lines} lines (>100)",
                        suggestion="Split into smaller functions",
                        risk=RiskLevel.MEDIUM,
                    ))
                in_func = False
    return findings


def _scan_duplicate_code(content: str, rel_path: Path) -> list[OptimizationFinding]:
    findings = []
    strings = re.findall(r'"""{1,}[\s\S]*?"{3}|"{1,2}[^"]{30,200}"{1,2}', content)
    string_counts: dict[str, list[int]] = {}
    for s in strings:
        key = s[:50]
        string_counts.setdefault(key, []).append(len(s))
    for key, counts in string_counts.items():
        if len(counts) >= 3:
            findings.append(OptimizationFinding(
                type="duplicate_code",
                file_path=str(rel_path),
                line=0,
                description=f"Duplicate string pattern detected ({len(counts)} occurrences)",
                suggestion="Extract repeated string into a constant or variable",
                risk=RiskLevel.LOW,
            ))
            break
    return findings


def _scan_long_functions(content: str, rel_path: Path) -> list[OptimizationFinding]:
    findings = []
    lines = content.split("\n")
    in_function = False
    func_start = 0
    func_indent = 0
    prev_func_name = ""

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        func_match = re.match(r"(?:async )?def (\w+)\s*\(", stripped)
        if func_match:
            if in_function:
                func_lines = i - func_start - 1
                if func_lines > 100:
                    findings.append(OptimizationFinding(
                        type="long_function",
                        file_path=str(rel_path),
                        line=func_start + 1,
                        description=f"Function '{prev_func_name}' is {func_lines} lines (>100)",
                        suggestion="Split into smaller, focused functions",
                        risk=RiskLevel.MEDIUM,
                    ))
            in_function = True
            func_start = i
            func_indent = indent
            prev_func_name = func_match.group(1)
        elif in_function:
            if stripped and indent <= func_indent:
                func_lines = i - func_start - 1
                if func_lines > 100:
                    findings.append(OptimizationFinding(
                        type="long_function",
                        file_path=str(rel_path),
                        line=func_start + 1,
                        description=f"Function '{prev_func_name}' is {func_lines} lines (>100)",
                        suggestion="Split into smaller, focused functions",
                        risk=RiskLevel.MEDIUM,
                    ))
                in_function = False
    return findings


def _scan_test_coverage(repo_path: Path, scan_root: Path) -> list[OptimizationFinding]:
    findings = []
    tests_dir = scan_root / "tests"
    if not tests_dir.exists():
        return findings
    main_modules: set[Path] = set()
    for py_file in scan_root.rglob("*.py"):
        rel = py_file.relative_to(scan_root)
        if rel.parts[0] in ("tests", ".git", ".iterations", "__pycache__"):
            continue
        if rel.name == "__init__.py" or rel.name.startswith("_"):
            continue
        main_modules.add(rel.parent / rel.stem)
    test_modules: set[Path] = set()
    if tests_dir.exists():
        for test_file in tests_dir.rglob("test_*.py"):
            rel = test_file.relative_to(tests_dir)
            test_modules.add(rel.parent / rel.stem)
    untested = []
    for mod in sorted(main_modules):
        test_path = tests_dir / ("test_" + mod.name + ".py")
        if not test_path.exists():
            untested.append(str(mod))
    if untested:
        findings.append(OptimizationFinding(
            type="missing_test",
            file_path=".",
            line=0,
            description=f"{len(untested)} modules lack test coverage: {', '.join(untested[:5])}",
            suggestion="Add tests for the untested modules",
            risk=RiskLevel.MEDIUM,
        ))
    return findings


def _scan_dependencies(repo_path: Path) -> list[OptimizationFinding]:
    findings = []
    req_file = repo_path / "requirements.txt"
    if req_file.exists():
        try:
            content = req_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.split("\n"), 1):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                if PINNED_VERSION.search(line):
                    findings.append(OptimizationFinding(
                        type="outdated_dep",
                        file_path="requirements.txt",
                        line=i,
                        description=f"Pinned version: {line}",
                        suggestion="Use semver range (e.g., >=1.0.0,<2.0.0)",
                        risk=RiskLevel.LOW,
                    ))
        except (UnicodeDecodeError, OSError):
            pass
    return findings


# ===========================================================
# Iteration Management
# ===========================================================

def generate_iteration_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def ensure_iterations_dir() -> Path:
    ITERATIONS_DIR.mkdir(parents=True, exist_ok=True)
    return ITERATIONS_DIR


def load_iteration(version: str) -> dict:
    manifest_file = ITERATIONS_DIR / version / "manifest.json"
    if not manifest_file.exists():
        raise FileNotFoundError(f"Iteration {version} not found")
    return json.loads(manifest_file.read_text())


def save_iteration(
    iteration_id: str,
    manifest: IterationManifest,
    plan_lines: list[str],
    pending_items: list[dict],
    report_lines: list[str],
    alert: Optional[AlertEntry] = None,
) -> None:
    iter_dir = ensure_iterations_dir() / iteration_id
    iter_dir.mkdir(parents=True, exist_ok=True)

    manifest_dict = asdict(manifest)
    manifest_dict["items_pending_approval"] = pending_items
    manifest_dict["has_alert"] = alert is not None

    (iter_dir / "manifest.json").write_text(json.dumps(manifest_dict, indent=2))
    (iter_dir / "plan.md").write_text("\n".join(plan_lines))
    (iter_dir / "pending-review.json").write_text(json.dumps(pending_items, indent=2))
    (iter_dir / "report.md").write_text("\n".join(report_lines))

    if alert:
        alert_data = {
            "iteration_id": alert.iteration_id,
            "date": alert.date,
            "alert_type": alert.alert_type,
            "message": alert.message,
            "details": alert.details,
        }
        (iter_dir / "alert.json").write_text(json.dumps(alert_data, indent=2))


def save_metrics(metrics: IterationMetrics) -> None:
    iter_dir = ensure_iterations_dir() / metrics.iteration_id
    iter_dir.mkdir(parents=True, exist_ok=True)
    (iter_dir / "metrics.json").write_text(json.dumps(asdict(metrics), indent=2))


def update_catalog(manifest: IterationManifest) -> None:
    catalog_file = ITERATIONS_DIR / "catalog.json"
    if catalog_file.exists():
        catalog = json.loads(catalog_file.read_text())
    else:
        catalog = {"iterations": []}

    catalog["iterations"] = [
        i for i in catalog.get("iterations", [])
        if i.get("version") != manifest.version
    ]

    catalog_entry = {
        "version": manifest.version,
        "date": manifest.date,
        "status": manifest.status,
        "risk_level": manifest.risk_level,
        "items_auto": manifest.items_auto,
        "items_approved": manifest.items_approved,
        "items_rejected": manifest.items_rejected,
        "items_optimization": manifest.items_optimization,
        "rollback_of": manifest.rollback_of,
        "has_alert": manifest.has_alert,
        "metrics_id": manifest.metrics_id,
        "test_coverage_delta": manifest.test_coverage_delta,
        "contributors": manifest.contributors,
        "total_cost_usd": manifest.total_cost_usd,
        "llm_calls": manifest.llm_calls,
    }

    catalog["iterations"].insert(0, catalog_entry)
    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    catalog_file.write_text(json.dumps(catalog, indent=2))


def load_catalog() -> dict:
    catalog_file = ITERATIONS_DIR / "catalog.json"
    if catalog_file.exists():
        return json.loads(catalog_file.read_text())
    return {"iterations": []}


# ===========================================================
# Quality Gates
# ===========================================================

def check_syntax(file_path: str) -> bool:
    result = subprocess.run(
        ["python3", "-m", "py_compile", file_path],
        capture_output=True,
    )
    return result.returncode == 0


def run_quality_gates(repo: Repository) -> dict:
    results: dict = {
        "passed": True,
        "syntax_ok": True,
        "syntax_errors": [],
        "lint_errors_fixed": 0,
    }
    for py_file in repo.resolve_path().rglob("*.py"):
        if not check_syntax(str(py_file)):
            results["syntax_ok"] = False
            results["syntax_errors"].append(str(py_file))
            results["passed"] = False
    return results


# ===========================================================
# Iteration Helpers (DRY: shared patterns across commands)
# ===========================================================

def _find_target_iteration(
    catalog: dict,
    iteration_id: Optional[str],
    status_filter: Optional[str] = None,
) -> tuple[Optional[dict], str]:
    """
    DRY helper: find a target iteration by ID or latest matching status.
    Returns (target_iter, iteration_id) or (None, iteration_id) on error.
    """
    if not catalog.get("iterations"):
        print("No iterations found.")
        return None, ""

    if iteration_id:
        target_iter = next(
            (i for i in catalog["iterations"] if i["version"] == iteration_id),
            None,
        )
        if not target_iter:
            print(f"Iteration {iteration_id} not found.")
            return None, ""
    else:
        if status_filter:
            target_iter = next(
                (i for i in catalog["iterations"] if i.get("status") == status_filter),
                None,
            )
            if not target_iter:
                print(f"No {status_filter} iteration found.")
                return None, ""
        else:
            return None, ""

    return target_iter, target_iter["version"]


def _load_iteration_pending(iteration_id: str) -> tuple[Optional[dict], list[dict]]:
    """DRY helper: load iteration manifest and extract pending items."""
    try:
        manifest_data = load_iteration(iteration_id)
        pending_items = manifest_data.get("items_pending_approval", [])
        return manifest_data, pending_items
    except FileNotFoundError:
        print(f"Iteration {iteration_id} manifest not found.")
        return None, []


def _finalize_iteration_status(
    iteration_id: str,
    manifest_data: dict,
    catalog: dict,
    status: str,
    **extra_fields: Any,
) -> None:
    """DRY helper: update manifest + catalog and persist both."""
    manifest_data.update({"status": status, **extra_fields})
    (ITERATIONS_DIR / iteration_id / "manifest.json").write_text(
        json.dumps(manifest_data, indent=2)
    )
    for i, cat_iter in enumerate(catalog["iterations"]):
        if cat_iter["version"] == iteration_id:
            catalog["iterations"][i].update({"status": status, **extra_fields})
            break
    (ITERATIONS_DIR / "catalog.json").write_text(json.dumps(catalog, indent=2))


# ===========================================================
# Closed-Repo Sanitization
# ===========================================================

def sanitize_pending_item(item: dict, repo: Repository) -> dict:
    if not repo.is_closed():
        return item
    sanitized = dict(item)
    if "file_path" in sanitized:
        fp = sanitized["file_path"]
        try:
            full_path = repo.resolve_path() / fp
            if full_path.exists():
                h = hashlib.sha256()
                h.update(full_path.read_bytes())
                sanitized["file_path_hash"] = h.hexdigest()[:12]
        except OSError:
            pass
        sanitized["file_path"] = "[REDACTED]"
    sanitized["description"] = "[CLOSED REPO] Change requires manual review"
    sanitized["content_redacted"] = True
    return sanitized


def sanitize_change_for_log(change: ChangeItem, repo: Repository) -> str:
    if not repo.is_closed():
        return f"{change.change_type}: {change.file_path}"
    return f"{change.change_type}: [FILE REDACTED for closed repo]"


# ===========================================================
# Execution Preview
# ===========================================================

def print_execution_preview(
    changes: list[ChangeItem],
    auto_exec: list[ChangeItem],
    mode: OperationMode,
    rules: dict,
) -> None:
    if mode == OperationMode.SEMI_AUTO:
        print("\n⚠️  Semi-Auto Mode: About to execute auto-changes:")
    else:
        print("\n⚠️  Full-Auto Mode: About to execute changes:")

    print(f"  Total: {len(auto_exec)} change(s)")
    sorted_exec = sort_by_priority(auto_exec)

    for i, c in enumerate(sorted_exec, 1):
        color = priority_color(c.priority)
        opt_badge = " [opt]" if c.category == ChangeCategory.OPTIMIZATION else ""
        risk_label = c.risk.value.upper()
        print(f"  [{i}] {color} P={c.priority:.2f} {risk_label}: {c.description[:60]}{opt_badge}")
    print()


# ===========================================================
# PR Batch Merging
# ===========================================================

def should_merge_prs(changes: list[dict]) -> bool:
    if len(changes) < 3:
        return False
    types = set(c.get("type", "") for c in changes)
    files = set(c.get("file", "") for c in changes)
    return len(types) <= 2 and len(files) <= 5


def group_similar_changes(changes: list[dict]) -> list[list[dict]]:
    if not should_merge_prs(changes):
        return [[c] for c in changes]
    by_type: dict[str, list[dict]] = {}
    for c in changes:
        t = c.get("type", "unknown")
        by_type.setdefault(t, []).append(c)
    groups: list[list[dict]] = []
    for t, type_changes in by_type.items():
        by_file: dict[str, list[dict]] = {}
        for c in type_changes:
            files_key = ",".join(sorted(c.get("file", "").split("/")[:2]))
            by_file.setdefault(files_key, []).append(c)
        for file_key, file_changes in by_file.items():
            if len(file_changes) >= 2:
                groups.append(file_changes)
            else:
                groups.extend([[c] for c in file_changes])
    return groups


def build_merged_pr_body(groups: list[list[dict]]) -> str:
    lines = ["## auto-evolve: Batch improvement", "", "### Changes", ""]
    for group in groups:
        if len(group) == 1:
            c = group[0]
            lines.append(f"- {c.get('description', c.get('change_type', 'unknown'))}")
        else:
            lines.append(f"- {len(group)} changes of type: {group[0].get('type', 'unknown')}")
            for c in group:
                lines.append(f"  - {c.get('description', c.get('file_path', 'unknown'))}")
    lines.extend(["", "### Approval", "", "This PR was auto-generated and merged for efficiency.", "Run `auto-evolve.py log` to review all changes."])
    return "\n".join(lines)


# ===========================================================
# LLM Analysis on Changes
# ===========================================================

def run_llm_analysis_on_changes(
    changes: list[ChangeItem],
    repo: Repository,
    cost_tracker: Optional[CostTracker] = None,
) -> list[ChangeItem]:
    """Run LLM analysis on pending high-priority changes. Tracks costs if CostTracker provided."""
    config = get_openclaw_llm_config()
    if not config["api_key"] or not config["base_url"]:
        return changes

    pending = [c for c in changes if c.category == ChangeCategory.PENDING_APPROVAL]
    top = sort_by_priority(pending)[:5]
    analyzed: set[int] = set()

    for item in top:
        if item.id in analyzed:
            continue
        fp = repo.resolve_path() / item.file_path
        if not fp.exists() or not fp.is_file():
            continue
        try:
            content = fp.read_text(encoding="utf-8")
        except Exception:
            continue

        ctx = f"File: {item.file_path}\nChange type: {item.change_type}\nRisk: {item.risk.value}\nCategory: {item.category.value}"
        result = analyze_with_llm(content, ctx, item.file_path)

        # v3.2: Track LLM call cost
        if cost_tracker:
            prompt_tokens = len(ctx + content[:2000]) // 4  # rough estimate
            completion_tokens = len(result.get("suggestion", "")) // 4
            cost_tracker.track_llm_call(prompt_tokens, completion_tokens, config["model"])

        if result.get("available"):
            item.llm_suggestion = result.get("suggestion", "")
            item.llm_risk = result.get("risk_level", item.risk.value)
            item.llm_implementation_hint = result.get("implementation_hint", "")
            if item.llm_risk in RISK_LEVELS:
                item.risk = RiskLevel(item.llm_risk)
                enrich_change_with_priority(item)
            analyzed.add(item.id)
            if item.llm_suggestion:
                print("  [LLM] " + item.llm_suggestion[:80])

    return changes


# ============================================================
# v3.3: Product Thinking Scanner
# Changes the question from "is the code clean?" to
# "what is broken from a USER perspective?"
# ============================================================

PRODUCT_CATEGORIES = (
    "user_complaint",
    "friction_point",
    "unused_feature",
    "competitive_gap",
    "stop_doing",
    "add_feature",
)


@dataclass
class ProductThinkingFinding:
    """A product-level insight about what should evolve, not just what should be cleaned up."""
    description: str
    category: str
    evidence: list[str]
    impact_score: float
    suggested_direction: str
    file_path: str
    risk: RiskLevel = RiskLevel.MEDIUM


class ProductThinkingScanner:
    """
    Scans the codebase asking: what is actually broken for users?
    This is NOT a code quality scanner.
    """

    def __init__(self, repos: list[Repository], config: dict) -> None:
        self.repos = repos
        self.config = config

    def scan(self) -> list[ProductThinkingFinding]:
        all_findings: list[ProductThinkingFinding] = []
        print(f"[ProductThinkingScanner] Starting scan of {len(self.repos)} repos...")
        for repo in self.repos:
            if not repo.auto_monitor:
                continue
            repo_path = repo.resolve_path()
            if not repo_path.exists():
                continue
            findings = self._scan_key_files(repo)
            all_findings.extend(findings)
            learnings_findings = self._analyze_learnings_patterns(repo)
            all_findings.extend(learnings_findings)
        all_findings.sort(key=lambda f: f.impact_score, reverse=True)
        return all_findings

    def _scan_key_files(self, repo: Repository) -> list[ProductThinkingFinding]:
        findings: list[ProductThinkingFinding] = []
        repo_path = repo.resolve_path()
        priority_files: list[Path] = []
        for fp in [repo_path / "README.md", repo_path / "SOUL.md", repo_path / "AGENTS.md"]:
            if fp.exists():
                priority_files.append(fp)
        for skill_dir in (repo_path / "skills").glob("*"):
            md = skill_dir / "SKILL.md"
            if md.exists():
                priority_files.append(md)
        for script in list(repo_path.glob("scripts/*.py")) + list(repo_path.glob("*.py")):
            if script.exists():
                priority_files.append(script)
        for fp in priority_files:
            try:
                content = fp.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = str(fp.relative_to(repo_path))
            if len(content) > 8000:
                content = content[:8000]
            finding = self._analyze_file_for_product_thinking(content, rel, repo)
            if finding:
                findings.append(finding)
        return findings

    def _analyze_file_for_product_thinking(
        self, content: str, file_path: str, repo: Repository
    ) -> Optional[ProductThinkingFinding]:
        config = get_openclaw_llm_config()
        if not config.get("api_key") or not config.get("base_url"):
            return None
        system = (
            "You are a brutally honest product advisor. "
            "You see code and docs, and you ask: "
            "  1. What would a user complain about after 5 minutes of this? "
            "  2. What is this project's blind spot — the thing they built but nobody asked for? "
            "  3. What is secretly annoying but presented as a feature? "
            "  4. What should they STOP doing and start doing instead? "
            "Answer ONLY with a JSON object with keys: "
            "  insight (max 150 chars, sharp and honest), "
            "  category (one of: user_complaint | friction_point | unused_feature | competitive_gap | stop_doing | add_feature), "
            "  impact (0.0 to 1.0), "
            "  evidence (array of 1-2 short text snippets from the content). "
            "If nothing significant is broken, return {\"insight\": \"\", \"category\": \"ok\", \"impact\": 0.0, \"evidence\": []}. "
            "Be harsh. Surface the uncomfortable truth."
        )
        lang = detect_language_from_path(file_path)
        prompt = (
            "IMPORTANT: Answer with ONLY a JSON object. No explanation.\n\n"
            f"File: {file_path}\n\n"
            f"Content (excerpt):\n```{lang}\n{content[:5000]}\n```\n\n"
            "What is broken from a user's perspective?"
        )
        result = call_llm(prompt=prompt, system=system, model=config["model"],
                          base_url=config["base_url"], api_key=config["api_key"])
        if not result:
            return None
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            m = re.search(r'\{[^{}]*\}', result, re.DOTALL)
            if not m:
                return None
            try:
                parsed = json.loads(m.group())
            except Exception:
                return None
        insight = parsed.get("insight", "").strip()
        if not insight or parsed.get("category") == "ok" or parsed.get("impact", 0.0) == 0.0:
            return None
        return ProductThinkingFinding(
            description=insight,
            category=parsed.get("category", "user_complaint"),
            evidence=parsed.get("evidence", []),
            impact_score=float(parsed.get("impact", 0.5)),
            suggested_direction="",
            file_path=file_path,
            risk=RiskLevel.MEDIUM,
        )

    def _analyze_learnings_patterns(self, repo: Repository) -> list[ProductThinkingFinding]:
        findings: list[ProductThinkingFinding] = []
        learnings = load_learnings()
        rejections = learnings.get("rejections", [])
        approvals = learnings.get("approvals", [])
        if not rejections:
            return findings
        reason_count: dict[str, int] = {}
        type_count: dict[str, int] = {}
        for r in rejections:
            reason = r.get("reason", "no reason given")[:80]
            desc = r.get("description", "")[:80]
            reason_count[reason] = reason_count.get(reason, 0) + 1
            type_count[desc] = type_count.get(desc, 0) + 1
        for reason, count in reason_count.items():
            if count >= 3:
                findings.append(ProductThinkingFinding(
                    description=(
                        f"STOP: This keeps getting rejected ({count}x) — '{reason}'. "
                        "Auto-evolve keeps trying the same thing. Rules need adjustment."
                    ),
                    category="stop_doing",
                    evidence=[f"Rejected {count} times: {reason}"],
                    impact_score=min(1.0, count * 0.2),
                    suggested_direction="Review full_auto_rules. This pattern keeps failing.",
                    file_path="auto-evolve config",
                    risk=RiskLevel.HIGH,
                ))
        for desc, count in type_count.items():
            if count >= 3:
                findings.append(ProductThinkingFinding(
                    description=(
                        f"Stop attempting this: '{desc}' — rejected {count} times. "
                        "The system keeps generating changes nobody wants."
                    ),
                    category="unused_feature",
                    evidence=[f"Rejected {count} times: {desc}"],
                    impact_score=min(1.0, count * 0.25),
                    suggested_direction=f"Add to learnings blocklist.",
                    file_path="auto-evolve learnings",
                    risk=RiskLevel.MEDIUM,
                ))
        approval_themes: dict[str, int] = {}
        for a in approvals:
            theme = a.get("description", "")[:50]
            approval_themes[theme] = approval_themes.get(theme, 0) + 1
        for theme, count in approval_themes.items():
            if count >= 5:
                findings.append(ProductThinkingFinding(
                    description=(
                        f"This type of change keeps getting approved ({count}x): '{theme}'. "
                        "Consider doing MORE of this automatically."
                    ),
                    category="add_feature",
                    evidence=[f"Approved {count} times: {theme}"],
                    impact_score=min(1.0, count * 0.15),
                    suggested_direction="Increase auto-execution of this category",
                    file_path="auto-evolve learnings",
                    risk=RiskLevel.LOW,
                ))
        return findings


def print_product_findings(findings: list[ProductThinkingFinding]) -> None:
    if not findings:
        print(f"\n🎯 Product Evolution Insights: none (all clear — or LLM returned empty)")
        return
    print(f"\n🎯 Product Evolution Insights (from {len(findings)} finding(s)):")
    print("=" * 60)
    icons = {
        "user_complaint": "😤",
        "friction_point": "🛑",
        "unused_feature": "💤",
        "competitive_gap": "📊",
        "stop_doing": "🚫",
        "add_feature": "✨",
    }
    for i, f in enumerate(findings[:10], 1):
        icon = icons.get(f.category, "❓")
        impact_bar = "█" * int(f.impact_score * 10) + "░" * (10 - int(f.impact_score * 10))
        print(f"\n  {i}. {icon} [{f.category.replace('_', ' ').upper()}]")
        print(f"     {f.description}")
        if f.evidence:
            print(f"     Evidence: {' | '.join(str(e)[:60] for e in f.evidence[:2])}")
        print(f"     Impact: {impact_bar} {f.impact_score:.1f}")
        if f.suggested_direction:
            print(f"     → {f.suggested_direction}")
        print(f"     File: {f.file_path}")
    if len(findings) > 10:
        print(f"\n  ... and {len(findings) - 10} more insights")


# ===========================================================
# Main Scan Logic
# ===========================================================

def run_scan(
    repo: Repository,
    dry_run: bool = False,
    learnings: Optional[dict] = None,
    before_snapshots: Optional[dict[str, dict]] = None,
    cost_tracker: Optional[CostTracker] = None,
) -> tuple[list[ChangeItem], list[OptimizationFinding], list[str], dict[str, dict]]:
    """
    Run a full scan on a repository.
    Returns: (changes, optimizations, plan_lines, after_snapshots)
    """
    changes: list[ChangeItem] = []
    opts: list[OptimizationFinding] = []
    plan_lines: list[str] = []
    change_id = 1
    learnings = learnings or {"rejections": [], "approvals": []}

    # Take before snapshot for effect tracking
    if before_snapshots is not None:
        effect_tracker = EffectTracker()
        before_snapshots[repo.path] = effect_tracker.snapshot(repo.resolve_path())

    # 1. Git changes
    git_changes = git_status(repo)
    changed_files = [gc["file"] for gc in git_changes]

    # Dependency analysis
    dep_affected: dict[str, list[str]] = {}
    if changed_files:
        dep_affected = analyze_dependencies(repo, changed_files)
        for changed, deps in dep_affected.items():
            print("  [!] Dependency Alert: Changing: " + changed)
            for dep in deps:
                print("     May affect: " + dep)

    for gc in git_changes:
        if is_rejected(gc["file"], repo.path, learnings):
            continue
        risk = classify_change(repo, gc["type"], gc["file"])
        category = ChangeCategory.AUTO_EXEC if risk == RiskLevel.LOW else ChangeCategory.PENDING_APPROVAL
        item = ChangeItem(
            id=change_id,
            description=f"{gc['type']}: {gc['file']}",
            file_path=gc["file"],
            change_type=gc["type"],
            risk=risk,
            category=category,
            repo_path=repo.path,
            repo_type=repo.type,
        )
        if gc["file"] in dep_affected:
            item.affected_files = dep_affected[gc["file"]]
        enrich_change_with_priority(item)
        changes.append(item)
        change_id += 1

    # 2. Proactive optimizations
    opts = scan_optimizations(repo)
    for o in opts:
        if is_rejected(o.description, repo.path, learnings):
            continue
        item = ChangeItem(
            id=change_id,
            description=f"[opt] {o.type}: {o.description}",
            file_path=o.file_path,
            change_type="optimization",
            risk=o.risk,
            category=ChangeCategory.OPTIMIZATION,
            repo_path=repo.path,
            repo_type=repo.type,
            optimization_type=o.type,
        )
        enrich_change_with_priority(item)
        changes.append(item)
        change_id += 1

    # Take after snapshot
    after_snapshots: dict[str, dict] = {}
    if before_snapshots is not None:
        effect_tracker = EffectTracker()
        after_snapshots[repo.path] = effect_tracker.snapshot(repo.resolve_path())

    return changes, opts, plan_lines, after_snapshots


# ===========================================================
# Metrics Generation
# ===========================================================

def generate_metrics(
    iteration_id: str,
    todos_resolved: int,
    lint_errors_fixed: int,
    files_changed: int,
    lines_added: int,
    lines_removed: int,
    quality_gate_passed: bool,
) -> IterationMetrics:
    return IterationMetrics(
        iteration_id=iteration_id,
        date=datetime.now(timezone.utc).isoformat(),
        todos_resolved=todos_resolved,
        lint_errors_fixed=lint_errors_fixed,
        test_coverage_delta=0.0,
        files_changed=files_changed,
        lines_added=lines_added,
        lines_removed=lines_removed,
        quality_gate_passed=quality_gate_passed,
    )


def compute_todos_resolved(changes: list[ChangeItem]) -> int:
    return sum(1 for c in changes if c.optimization_type == "todo_fixme" or "todo" in c.description.lower())


# ===========================================================
# Cron Integration
# ===========================================================

def setup_cron(interval_hours: int) -> bool:
    result = subprocess.run(["which", "openclaw"], capture_output=True)
    if result.returncode != 0:
        return False

    cmd = [
        "openclaw", "cron", "add",
        "--name", "auto-evolve-scan",
        "--every", f"{interval_hours}h",
        "--message", "exec python3 ~/.openclaw/workspace/skills/auto-evolve/scripts/auto-evolve.py scan",
    ]
    add_result = subprocess.run(cmd, capture_output=True, text=True)
    if add_result.returncode == 0:
        cron_id_match = re.search(r"cron[_-]?id[:\s]+([\w-]+)", add_result.stdout + add_result.stderr)
        cron_id = cron_id_match.group(1) if cron_id_match else None
        config = load_config()
        config["schedule_cron_id"] = cron_id
        save_config(config)
        return True
    return False


def remove_cron() -> bool:
    result = subprocess.run(["which", "openclaw"], capture_output=True)
    if result.returncode != 0:
        return False
    config = load_config()
    cron_id = config.get("schedule_cron_id")
    cmd = ["openclaw", "cron", "remove"]
    if cron_id:
        cmd.append(cron_id)
    else:
        cmd.append("auto-evolve-scan")
    rem_result = subprocess.run(cmd, capture_output=True, text=True)
    if rem_result.returncode == 0:
        config["schedule_cron_id"] = None
        save_config(config)
        return True
    return False


# ===========================================================
# Pending Review
# ===========================================================

def load_pending_review(iteration_id: str) -> list[dict]:
    try:
        return json.loads((ITERATIONS_DIR / iteration_id / "pending-review.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_pending_review(iteration_id: str, items: list[dict]) -> None:
    (ITERATIONS_DIR / iteration_id / "pending-review.json").write_text(json.dumps(items, indent=2))


# ===========================================================
# Commands
# ===========================================================

# ===========================================================
# cmd_scan helpers (reduce function length)
# ===========================================================

def _scan_repos(
    config: dict,
    args,
    learnings: dict,
    before_snapshots: dict[str, dict],
    cost_tracker: CostTracker,
    iteration_id: str,
) -> tuple[list[ChangeItem], list[OptimizationFinding], dict[str, dict], list[Repository], Optional[AlertEntry], dict]:
    """
    Scan all configured repositories.
    Returns (all_changes, all_opts, after_snapshots, repos, alert, qg).
    """
    repos = config_to_repos(config)
    all_changes: list[ChangeItem] = []
    all_opts: list[OptimizationFinding] = []
    after_snapshots: dict[str, dict] = {}
    alert: Optional[AlertEntry] = None
    qg_result: dict = {}

    for repo in repos:
        if not repo.auto_monitor:
            print(f"\n⏭️  Skipping {repo.path} (auto_monitor=false)")
            continue
        if not repo.resolve_path().exists():
            print(f"\n⚠️  Repository not found: {repo.path}")
            continue

        print(f"\n📦 Scanning: {repo.path} ({repo.type})")

        qg_result = run_quality_gates(repo)
        if not qg_result["passed"]:
            print(f"  ⚠️  Quality gate failed: {len(qg_result['syntax_errors'])} syntax error(s)")
            alert = AlertEntry(
                iteration_id=iteration_id,
                date=datetime.now(timezone.utc).isoformat(),
                alert_type="quality_gate_failed",
                message="Syntax errors detected in repository",
                details={"errors": qg_result["syntax_errors"]},
            )
        else:
            print(f"  ✅ Quality gates passed")

        changes, opts, _, after_snaps = run_scan(
            repo,
            dry_run=args.dry_run,
            learnings=learnings,
            before_snapshots=before_snapshots,
            cost_tracker=cost_tracker,
        )
        all_changes.extend(changes)
        all_opts.extend(opts)
        after_snapshots.update(after_snaps)

    return all_changes, all_opts, after_snapshots, repos, alert, qg_result


def _auto_execute_changes(
    auto_exec: list[ChangeItem],
    rules: dict,
    pending_sorted: list[ChangeItem],
    mode: OperationMode,
    dry_run: bool,
) -> tuple[list[ChangeItem], set[str], int, str, list[ChangeItem]]:
    """
    Execute auto-approved low-risk changes in full-auto mode.
    Returns (auto_executed, repos_affected, todos_resolved, iteration_status, remaining_pending).
    """
    auto_executed: list[ChangeItem] = []
    repos_affected: set[str] = set()
    todos_resolved = 0
    remaining_pending: list[ChangeItem] = []
    iteration_status = "dry-run" if dry_run else mode.value

    if mode == OperationMode.FULL_AUTO and not dry_run:
        for change in auto_exec:
            if should_auto_execute(rules, change.risk):
                try:
                    repo_obj = Repository(path=change.repo_path, type=change.repo_type)
                    commit_hash = git_commit(repo_obj, f"auto: {change.description}")
                    change.commit_hash = commit_hash
                    auto_executed.append(change)
                    repos_affected.add(change.repo_path)
                    if change.optimization_type == "todo_fixme":
                        todos_resolved += 1
                    log_desc = sanitize_change_for_log(change, repo_obj)
                    print(f"  ✅ {log_desc} ({commit_hash})")
                except Exception as e:
                    print(f"  ❌ {change.file_path}: {e}")
        remaining_pending = pending_sorted
        iteration_status = "full-auto-completed"

    elif mode == OperationMode.SEMI_AUTO and not dry_run:
        remaining_pending = auto_exec + pending_sorted
        iteration_status = "pending-approval"
        if auto_exec:
            print(f"\n📋 {len(auto_exec)} auto-changes held for confirmation (semi-auto mode)")
            print(f"   Run `auto-evolve.py confirm` after reviewing pending items")
    else:
        remaining_pending = auto_exec + pending_sorted

    return auto_executed, repos_affected, todos_resolved, iteration_status, remaining_pending


def _build_pending_items(pending_sorted: list[ChangeItem]) -> tuple[list[dict], list[str]]:
    """Convert sorted pending ChangeItems to dicts and plan_lines."""
    pending_items: list[dict] = []
    for c in pending_sorted:
        repo_obj = Repository(path=c.repo_path, type=c.repo_type)
        item: dict = {
            "id": c.id,
            "description": c.description,
            "file_path": c.file_path,
            "risk": c.risk.value,
            "category": c.category.value,
            "repo_path": c.repo_path,
            "optimization_type": c.optimization_type,
            "priority": c.priority,
            "value_score": c.value_score,
            "risk_score": c.risk_score,
            "cost_score": c.cost_score,
        }
        if repo_obj.is_closed():
            item = sanitize_pending_item(item, repo_obj)
        pending_items.append(item)
    return pending_items, []


def _display_remaining_pending(
    remaining_pending: list[ChangeItem],
    plan_lines: list[str],
) -> None:
    """Print remaining pending items and extend plan_lines."""
    if remaining_pending:
        display_items = remaining_pending[:20]
        print(f"\n📋 Pending Items ({len(remaining_pending)}):")
        for i, c in enumerate(display_items, 1):
            risk_icon = RISK_COLORS.get(c.risk.value, "⚪")
            opt_badge = " [opt]" if c.category == ChangeCategory.OPTIMIZATION else ""
            print(f"  [{i}] {risk_icon} P={c.priority:.2f} {c.description[:55]}{opt_badge}")
        if len(remaining_pending) > 20:
            print(f"  ... and {len(remaining_pending) - 20} more")
        plan_lines.extend(["## Pending Items ({})".format(len(remaining_pending)), ""])
        for i, c in enumerate(remaining_pending, 1):
            plan_lines.append(f"- [{i}] **{c.risk.value.upper()}** P={c.priority:.2f} {c.description}")


def _push_repos(repos_affected: set[str]) -> None:
    """Push all affected repos to remote."""
    for rp in repos_affected:
        repo_obj = Repository(path=rp, type="skill")
        try:
            git_push(repo_obj)
            print(f"  📤 Pushed to remote")
        except Exception as e:
            print(f"  ⚠️  Push failed: {e}")


def _build_pending_items_with_plan(
    pending_sorted: list[ChangeItem],
    plan_lines: list[str],
) -> tuple[list[dict], list[str]]:
    """Convert pending ChangeItems to dicts and append to plan_lines."""
    pending_items: list[dict] = []
    for c in pending_sorted:
        repo_obj = Repository(path=c.repo_path, type=c.repo_type)
        item: dict = {
            "id": c.id,
            "description": c.description,
            "file_path": c.file_path,
            "risk": c.risk.value,
            "category": c.category.value,
            "repo_path": c.repo_path,
            "optimization_type": c.optimization_type,
            "priority": c.priority,
            "value_score": c.value_score,
            "risk_score": c.risk_score,
            "cost_score": c.cost_score,
        }
        if repo_obj.is_closed():
            item = sanitize_pending_item(item, repo_obj)
        pending_items.append(item)
    return pending_items, plan_lines


def _compute_diff_stats(repos_affected: set[str]) -> tuple[int, int, int]:
    """Compute lines added/removed and files changed across repos."""
    lines_added_total = lines_removed_total = files_changed_total = 0
    for rp in repos_affected:
        repo_obj = Repository(path=rp, type="skill")
        la, lr = git_diff_lines_added_removed(repo_obj)
        lines_added_total += la
        lines_removed_total += lr
        files_changed_total += len(git_status(repo_obj))
    return lines_added_total, lines_removed_total, files_changed_total


def _post_scan_cleanup(
    cost_tracker: CostTracker,
    iteration_id: str,
    effect_tracker: EffectTracker,
    before_snapshots: dict[str, dict],
    after_snapshots: dict[str, dict],
    auto_executed: list[ChangeItem],
    remaining_pending: list[ChangeItem],
    todos_resolved: int,
    qg: dict,
    repos_affected: set[str],
) -> dict:
    """Flush LLM costs, compute effects, link issues. Returns cost_summary."""
    cost_tracker.flush_calls(iteration_id)
    cost_summary = cost_tracker.get_iteration_cost(iteration_id)

    if before_snapshots and after_snapshots and (auto_executed or remaining_pending):
        effect_report = effect_tracker.track_iteration_effect(
            iteration_id=iteration_id,
            before_snapshots=before_snapshots,
            after_snapshots=after_snapshots,
            todos_resolved=todos_resolved,
            lint_errors_fixed=qg.get("lint_errors_fixed", 0),
            coverage_delta=0.0,
        )
        verdict_icon = {"positive": "✅", "neutral": "➖", "negative": "❌"}.get(effect_report["verdict"], "➖")
        print(f"\n  {verdict_icon} Effect: {effect_report['summary']}")

    if auto_executed:
        issue_linker = IssueLinker()
        for rp in repos_affected:
            repo_path = Path(rp)
            repo_changed = [g["file"] for g in git_status(Repository(path=rp, type="skill"))]
            if repo_changed:
                close_result = issue_linker.close_related_issues(repo_path, repo_changed, iteration_id)
                if close_result["found"] > 0:
                    print(f"\n  🔗 IssueLinker: found {close_result['found']} related issue(s), closed {close_result['closed']}")

    return cost_summary


def _print_scan_summary(
    all_changes: list[ChangeItem],
    all_opts: list[OptimizationFinding],
    auto_exec: list[ChangeItem],
    pending_sorted: list[ChangeItem],
    mode: OperationMode,
    dry_run: bool,
    rules: dict,
) -> None:
    """Print scan result summary and priority queue."""
    print(f"\n📊 Scan Results:")
    print(f"  Changes detected: {len(all_changes) - len(all_opts)}")
    print(f"  Optimizations found: {len(all_opts)}")
    print(f"  Auto-executable:     {len(auto_exec)}")
    print(f"  Pending review:      {len(pending_sorted)}")

    if pending_sorted:
        print(f"\n📊 Priority Queue:")
        for i, c in enumerate(pending_sorted[:10], 1):
            color = priority_color(c.priority)
            risk_label = c.risk.value.upper()
            opt_badge = " [opt]" if c.category == ChangeCategory.OPTIMIZATION else ""
            print(f"  [{i}] {color} P={c.priority:.2f} {risk_label}: {c.description[:55]}{opt_badge}")
        if len(pending_sorted) > 10:
            print(f"  ... and {len(pending_sorted) - 10} more")

    if auto_exec and not dry_run:
        print_execution_preview(all_changes, auto_exec, mode, rules)


def _build_plan_and_report(
    iteration_id: str,
    mode: OperationMode,
    dry_run: bool,
    repos: list[Repository],
    duration: float,
    all_changes: list[ChangeItem],
    all_opts: list[OptimizationFinding],
    pending_sorted: list[ChangeItem],
) -> tuple[list[str], list[str], list[dict]]:
    """Build plan_lines, report_lines, and pending_items from scan results."""
    plan_lines = [
        f"# Iteration Plan — {iteration_id}",
        "",
        f"**Date:** {datetime.now(timezone.utc).isoformat()}",
        f"**Mode:** {mode.value}",
        f"**Repositories:** {len(repos)}",
        f"**Duration:** {duration:.1f}s",
        "",
        "## Changes",
        "",
    ]
    report_lines = [
        f"# Iteration Report — {iteration_id}",
        "",
        f"**Date:** {datetime.now(timezone.utc).isoformat()}",
        f"**Mode:** {mode.value}",
        f"**Status:** {'dry-run' if dry_run else mode.value}",
        "",
        "## Summary",
        "",
        f"- Changes detected: {len(all_changes) - len(all_opts)}",
        f"- Optimizations found: {len(all_opts)}",
        f"- Pending review: {len(pending_sorted)}",
        "",
    ]
    pending_items, plan_lines = _build_pending_items_with_plan(pending_sorted, plan_lines)
    return plan_lines, report_lines, pending_items


def _track_contributors(repos_affected: set[str]) -> dict:
    """Collect contributor stats for all affected repos."""
    contributors: dict = {}
    for rp in repos_affected:
        repo_obj = Repository(path=rp, type="skill")
        contributors[rp] = track_contributors(repo_obj)
    return contributors


def _build_scan_manifest(
    iteration_id: str,
    iteration_status: str,
    duration: float,
    num_auto: int,
    num_opts: int,
    pending_items: list[dict],
    alert: Optional[AlertEntry],
    contributors: dict,
    cost_summary: dict,
) -> IterationManifest:
    """Build and return the IterationManifest for a scan iteration."""
    return IterationManifest(
        version=iteration_id,
        date=datetime.now(timezone.utc).isoformat(),
        status=iteration_status,
        risk_level="mixed",
        items_auto=num_auto,
        items_approved=0,
        items_rejected=0,
        items_optimization=num_opts,
        duration_seconds=round(duration, 1),
        items_pending_approval=pending_items,
        has_alert=alert is not None,
        metrics_id=iteration_id,
        test_coverage_delta=None,
        contributors=contributors,
        total_cost_usd=cost_summary.get("total_cost_usd"),
        llm_calls=cost_summary.get("total_calls", 0),
    )


def _print_contributors(contributors: dict) -> None:
    """Print contributor stats."""
    for rp, contrib in contributors.items():
        rn = Path(rp).name
        print(f"   [C] {rn}: {contrib['auto_commits']} auto / "
              f"{contrib['manual_commits']} manual ({contrib['auto_percentage']}% auto)")


def _print_iteration_summary(
    iteration_id: str,
    pending_items: list[dict],
    metrics,
    cost_summary: dict,
    mode: OperationMode,
    auto_exec: list[ChangeItem],
    dry_run: bool,
    opt_executed: Optional[list[ChangeItem]] = None,
    opt_stats: Optional[dict] = None,
) -> None:
    """Print final iteration summary."""
    print(f"\n📁 Iteration {iteration_id} saved to .iterations/{iteration_id}/")
    print(f"   pending-review.json: {len(pending_items)} items")
    print(f"   metrics.json: todos={metrics.todos_resolved}, files={metrics.files_changed}, "
          f"+{metrics.lines_added}/-{metrics.lines_removed}")
    if opt_executed:
        print(f"   ⚡ Optimizations executed: {len(opt_executed)} "
              f"(via LLM auto-fix, v3.2)")
        if opt_stats:
            by_type = opt_stats.get("by_type", {})
            for ot, cnt in by_type.items():
                print(f"      - {ot}: {cnt}")
    if cost_summary.get("total_calls", 0) > 0:
        print(f"   💰 LLM cost: ${cost_summary['total_cost_usd']:.6f} "
              f"({cost_summary['total_calls']} calls)")

    if mode == OperationMode.SEMI_AUTO and auto_exec and not dry_run:
        print(f"\n   Confirm with: auto-evolve.py confirm")

    if dry_run:
        print("\n⚠️  Dry-run mode — no changes committed")


def cmd_scan(args) -> int:
    """Scan all configured repositories and produce an iteration."""
    config = load_config()
    dry_run = args.dry_run
    mode = get_operation_mode(config)
    rules = get_full_auto_rules(config)
    learnings = load_learnings()

    print("🔍 Auto-Evolve v3.3 Scanner")
    print(f"   Mode: {mode.value}")
    print("=" * 50)

    start_time = time.time()
    iteration_id = generate_iteration_id()

    # Trackers
    effect_tracker = EffectTracker()
    cost_tracker = CostTracker()
    before_snapshots: dict[str, dict] = {}

    # Scan repos
    all_changes, all_opts, after_snapshots, repos, alert, qg = _scan_repos(
        config, args, learnings, before_snapshots, cost_tracker, iteration_id,
    )
    duration = time.time() - start_time

    # Categorize changes
    auto_exec = [c for c in all_changes if c.category == ChangeCategory.AUTO_EXEC and c.risk == RiskLevel.LOW]
    pending = [c for c in all_changes if c.category in (ChangeCategory.PENDING_APPROVAL, ChangeCategory.OPTIMIZATION)]
    pending_sorted = sort_by_priority(pending)

    # Print scan summary and priority queue
    _print_scan_summary(all_changes, all_opts, auto_exec, pending_sorted, mode, dry_run, rules)

    # v3.3: Product Thinking Scanner — ask the RIGHT questions
    print("\n" + "=" * 50)
    product_scanner = ProductThinkingScanner(repos, config)
    product_findings = product_scanner.scan()
    print_product_findings(product_findings)

    # Build plan and report lines
    plan_lines, report_lines, pending_items = _build_plan_and_report(
        iteration_id, mode, dry_run, repos, duration,
        all_changes, all_opts, pending_sorted,
    )

    # Auto-execute changes
    (auto_executed, repos_affected, todos_resolved, iteration_status, remaining_pending) = \
        _auto_execute_changes(auto_exec, rules, pending_sorted, mode, dry_run)

    # Auto-execute LLM-driven optimizations (v3.2)
    (opt_executed, opt_stats) = _auto_execute_optimizations(
        all_changes, all_opts, mode, rules, dry_run,
    )

    # Merge optimization repos into repos_affected
    for item in opt_executed:
        repos_affected.add(item.repo_path)

    # Update todos_resolved with optimization todos
    todos_resolved += sum(
        1 for item in opt_executed if item.optimization_type == "todo_fixme"
    )

    # Diff stats
    lines_added_total, lines_removed_total, files_changed_total = _compute_diff_stats(repos_affected)

    # Pending items display
    _display_remaining_pending(remaining_pending, plan_lines)

    # Push auto-executed (both git changes and LLM optimizations)
    if (auto_executed or opt_executed) and not dry_run:
        _push_repos(repos_affected)

    # Post-scan: costs, effects, issue linking
    cost_summary = _post_scan_cleanup(
        cost_tracker, iteration_id, effect_tracker,
        before_snapshots, after_snapshots,
        auto_executed, remaining_pending,
        todos_resolved, qg, repos_affected,
    )

    # Metrics and contributors
    quality_passed = alert is None
    metrics = generate_metrics(
        iteration_id=iteration_id,
        todos_resolved=todos_resolved,
        lint_errors_fixed=qg.get("lint_errors_fixed", 0),
        files_changed=files_changed_total,
        lines_added=lines_added_total,
        lines_removed=lines_removed_total,
        quality_gate_passed=quality_passed,
    )
    save_metrics(metrics)
    contributors = _track_contributors(repos_affected)

    # Build manifest and save
    total_auto = len(auto_executed) + len(opt_executed)
    manifest = _build_scan_manifest(
        iteration_id, iteration_status, duration,
        total_auto, len(all_opts),
        pending_items, alert, contributors, cost_summary,
    )
    _print_contributors(contributors)
    save_iteration(iteration_id, manifest, plan_lines, pending_items, report_lines, alert)
    update_catalog(manifest)

    # Final summary
    _print_iteration_summary(
        iteration_id, pending_items, metrics, cost_summary,
        mode, auto_exec, dry_run, opt_executed, opt_stats,
    )
    return 0


def cmd_confirm(args) -> int:
    """Confirm pending changes from a semi-auto scan iteration."""
    catalog = load_catalog()
    target_iter, iteration_id = _find_target_iteration(
        catalog, args.iteration_id, status_filter="pending-approval",
    )
    if not iteration_id:
        return 1

    manifest_data, pending_items = _load_iteration_pending(iteration_id)
    if manifest_data is None:
        return 1
    if not pending_items:
        print(f"No pending items in iteration {iteration_id}.")
        return 0

    print(f"Confirming {len(pending_items)} pending items from {iteration_id}...")

    repos_affected: set[str] = set(p.get("repo_path", "") for p in pending_items)
    confirmed_count = 0

    for rp in repos_affected:
        repo_obj = Repository(path=rp, type="skill")
        if not repo_obj.resolve_path().exists():
            continue
        repo_items = [p for p in pending_items if p.get("repo_path") == rp]
        for p in repo_items:
            try:
                commit_hash = git_commit(repo_obj, f"auto-evolve: {p['description']}")
                print(f"  ✅ [{p['id']}] {p['description'][:60]} ({commit_hash})")
                confirmed_count += 1
                add_learning(
                    learning_type="approval",
                    change_id=str(p["id"]),
                    description=p["description"],
                    reason=None,
                    repo=rp,
                    approved_by="user",
                )
            except Exception as e:
                print(f"  ❌ [{p['id']}] {p['description'][:60]}: {e}")

    # v3.2: Issue linking after confirm
    if confirmed_count > 0:
        issue_linker = IssueLinker()
        for rp in repos_affected:
            repo_path = Path(rp)
            repo_changed = [g["file"] for g in git_status(Repository(path=rp, type="skill"))]
            if repo_changed:
                close_result = issue_linker.close_related_issues(repo_path, repo_changed, iteration_id)
                if close_result["found"] > 0:
                    print(f"\n  🔗 IssueLinker: closed {close_result['closed']} of {close_result['found']} related issue(s)")

    for rp in repos_affected:
        repo_obj = Repository(path=rp, type="skill")
        try:
            git_push(repo_obj)
        except Exception as e:
            print(f"  ⚠️  Push failed for {rp}: {e}")

    _finalize_iteration_status(
        iteration_id, manifest_data, catalog,
        "completed", items_approved=confirmed_count,
    )
    print(f"\n✅ Confirmed and executed {confirmed_count} items")
    return 0


def cmd_reject(args) -> int:
    """Reject a specific pending change and record it in learnings."""
    catalog = load_catalog()
    target_iter, iteration_id = _find_target_iteration(
        catalog, args.iteration_id, status_filter="pending-approval",
    )
    if not iteration_id:
        return 1

    manifest_data, pending_items = _load_iteration_pending(iteration_id)
    if manifest_data is None:
        return 1

    item = next((p for p in pending_items if p.get("id") == args.id), None)
    if not item:
        print(f"Item {args.id} not found in pending items.")
        return 1

    add_learning(
        learning_type="rejection",
        change_id=str(args.id),
        description=item["description"],
        reason=args.reason,
        repo=item.get("repo_path", ""),
    )

    remaining = [p for p in pending_items if p.get("id") != args.id]
    save_pending_review(iteration_id, remaining)

    manifest_data["items_pending_approval"] = remaining
    manifest_data["items_rejected"] = manifest_data.get("items_rejected", 0) + 1
    (ITERATIONS_DIR / iteration_id / "manifest.json").write_text(
        json.dumps(manifest_data, indent=2),
    )

    print(f"❌ Rejected item {args.id}: {item['description'][:60]}")
    if args.reason:
        print(f"   Reason: {args.reason}")
    print(f"   Recorded in .learnings/rejections.json")

    return 0


def cmd_approve(args) -> int:
    """Approve and execute pending changes (supports --all, --ids, or interactive)."""
    catalog = load_catalog()
    target_iter, iteration_id = _find_target_iteration(
        catalog, args.iteration_id,
        status_filter="pending-approval",
    )
    if not iteration_id:
        # Fallback: also check full-auto-completed
        catalog = load_catalog()
        target_iter, iteration_id = _find_target_iteration(
            catalog, args.iteration_id,
            status_filter="full-auto-completed",
        )
        if not iteration_id:
            return 1

    manifest_data, pending_items = _load_iteration_pending(iteration_id)
    if manifest_data is None:
        return 1
    if not pending_items:
        print(f"No pending items in iteration {iteration_id}.")
        return 0

    # Resolve which IDs to approve
    approved_ids = _resolve_approved_ids(args, pending_items)
    if approved_ids is None:
        return 0  # Interactive listing was shown

    # Batch merge check for high-risk
    changes_for_pr = [p for p in pending_items if p["id"] in approved_ids and p.get("risk") == "high"]
    if len(changes_for_pr) >= 3 and should_merge_prs(changes_for_pr):
        print(f"\n📦 Batch-merging {len(changes_for_pr)} high-risk changes into single PR...")
        groups = group_similar_changes(changes_for_pr)
        print(f"   Created {len(groups)} change group(s)")

    # Execute approvals
    approved_count, repos_affected = _execute_approved_items(
        pending_items, approved_ids, iteration_id, args,
    )

    # Push
    if approved_count > 0:
        _push_repos(repos_affected)

    _finalize_iteration_status(
        iteration_id, manifest_data, catalog,
        "completed", items_approved=approved_count,
    )
    print(f"\n✅ Approved and executed {approved_count} items")
    return 0


def _resolve_approved_ids(
    args,
    pending_items: list[dict],
) -> Optional[list[int]]:
    """Resolve which item IDs to approve. Returns None if displaying interactive list."""
    if args.all:
        approved_ids = [p["id"] for p in pending_items]
        reason = getattr(args, "reason", None)
        print(f"✅ Approving all {len(approved_ids)} pending items...")
        if reason:
            print(f"   Reason: {reason}")
        return approved_ids

    ids_str = getattr(args, "ids", None)
    if ids_str:
        try:
            return [int(x.strip()) for x in str(ids_str).split(",") if x.strip()]
        except ValueError:
            print("Invalid IDs. Use: approve 1,2,3")
            return None

    # Interactive listing
    iteration_id = getattr(args, "iteration_id", None)
    print(f"Iteration: {iteration_id}")
    print(f"Pending items ({len(pending_items)}):")
    for p in pending_items:
        risk_icon = RISK_COLORS.get(p.get("risk", "medium"), "⚪")
        pri = p.get("priority", 0)
        llm_b = " [LLM]" if p.get("llm_suggestion") else ""
        dep_b = ""
        if p.get("affected_files"):
            dep_b = f" [!]{len(p['affected_files'])}deps"
        print(f"  [{p['id']}] {risk_icon} P={pri:.2f} {p.get('risk', '?').upper()} "
              f"{p.get('description', '')[:55]}{llm_b}{dep_b}")
    print("\nRun: auto-evolve.py approve --all [--reason 'your reason']")
    print("Or:  auto-evolve.py approve 1,3 [--reason 'your reason']")
    return None


def _execute_approved_items(
    pending_items: list[dict],
    approved_ids: list[int],
    iteration_id: str,
    args,
) -> tuple[int, set[str]]:
    """Execute approved items. Returns (approved_count, repos_affected)."""
    approved_count = 0
    repos_affected: set[str] = set()
    issue_linker = IssueLinker()
    approval_reason = getattr(args, "reason", None)

    for p in pending_items:
        if p["id"] not in approved_ids:
            continue

        repo_obj = Repository(path=p["repo_path"], type=p.get("repo_type", "skill"))
        if not repo_obj.resolve_path().exists():
            print(f"  ⚠️  Repo not found: {repo_obj.path}")
            continue

        if p.get("risk") == "high":
            _approve_high_risk(p, repo_obj, issue_linker, iteration_id)
            approved_count += 1
            repos_affected.add(p["repo_path"])
        else:
            try:
                commit_hash = git_commit(repo_obj, f"auto-evolve: {p['description']}")
                print(f"  ✅ [{p['id']}] {p['description'][:60]} ({commit_hash})")
                approved_count += 1
                repos_affected.add(p["repo_path"])
                add_learning(
                    learning_type="approval",
                    change_id=str(p["id"]),
                    description=p["description"],
                    reason=approval_reason,
                    repo=repo_obj.path,
                    approved_by="user",
                )
                repo_changed = [p.get("file_path", "")]
                close_result = issue_linker.close_related_issues(
                    repo_obj.resolve_path(), repo_changed, iteration_id,
                )
                if close_result["found"] > 0:
                    print(f"  🔗 IssueLinker: closed {close_result['closed']} of {close_result['found']} related issue(s)")
            except Exception as e:
                print(f"  ❌ [{p['id']}] {p['description'][:60]}: {e}")

    return approved_count, repos_affected


def _approve_high_risk(
    p: dict,
    repo_obj: Repository,
    issue_linker: IssueLinker,
    iteration_id: str,
) -> None:
    """Handle approval of a high-risk item (branch + PR)."""
    print(f"\n🔴 High-risk: {p['description'][:60]}")
    print(f"  Creating branch and PR...")
    branch = create_branch_for_change(repo_obj, p["description"][:50])
    conflict_result = handle_pr_conflict(repo_obj, branch)
    try:
        commit_hash = git_commit(repo_obj, f"auto-evolve: {p['description']}")
        pr_body = f"## auto-evolve: {p['description']}\n\n### Changes\n\n- {p['description']}"
        pr_url = create_pr(
            repo_obj, branch,
            p["description"],
            [ChangeItem(
                id=p["id"],
                description=p["description"],
                file_path=p["file_path"],
                change_type="approved",
                risk=RiskLevel.HIGH,
                category=ChangeCategory.PENDING_APPROVAL,
                repo_path=repo_obj.path,
            )],
            extra_body=pr_body,
        )
        print(f"  ✅ Branch: {branch}")
        print(f"  ✅ Commit: {commit_hash}")
        if conflict_result == "auto_resolved":
            print(f"  🔧 Conflicts auto-resolved during rebase")
        elif conflict_result == "manual_required":
            print(f"  ⚠️  Conflicts require manual resolution")
        print(f"  🔗 {pr_url}")
    except Exception as e:
        print(f"  ❌ Failed: {e}")


def create_branch_for_change(repo: Repository, change_desc: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", change_desc.lower())[:50]
    branch_name = f"auto-evolve/{sanitized}"
    git_create_branch(repo, branch_name)
    return branch_name


def create_pr(repo: Repository, branch_name: str, description: str, changes: list[ChangeItem], extra_body: Optional[str] = None) -> str:
    result = git_run(repo, "remote", "get-url", "origin", check=False)
    remote_url = result.stdout.strip()
    match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", remote_url)
    if not match:
        return f"Branch created: {branch_name} (PR creation requires gh CLI and GitHub remote)"
    repo_slug = match.group(1)

    pr_body_lines = [
        f"## auto-evolve: {description}",
        "",
        "### Changes",
        "",
    ]
    for c in changes:
        pr_body_lines.append(f"- **{c.risk.value}** {c.description} (`{c.file_path}`)")
    if extra_body:
        pr_body_lines.extend(["", extra_body])
    pr_body_lines.extend([
        "",
        "### Approval",
        "",
        "This PR requires explicit approval. Run:",
        "```",
        "auto-evolve.py approve",
        "```",
    ])
    pr_body = "\n".join(pr_body_lines)

    result = subprocess.run(
        [
            "gh", "pr", "create",
            "--repo", repo_slug,
            "--title", f"[auto-evolve] {description}",
            "--body", pr_body,
            "--base", "main",
            "--head", branch_name,
        ],
        cwd=str(repo.resolve_path()),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"Branch {branch_name} created. PR creation failed: {result.stderr.strip()}"
    return result.stdout.strip()


def cmd_repo_add(args) -> int:
    config = load_config()
    repos = config_to_repos(config)
    repo_path = Path(args.path).expanduser().resolve()
    if not repo_path.exists():
        print(f"❌ Repository not found: {repo_path}")
        return 1
    repo_type = args.type or "skill"
    if repo_type not in REPO_TYPES:
        print(f"Invalid type. Must be one of: {', '.join(REPO_TYPES)}")
        return 1
    for r in repos:
        if Path(r.path).resolve() == repo_path:
            print(f"Repository already monitored: {repo_path}")
            return 0
    new_repo = Repository(
        path=str(repo_path),
        type=repo_type,
        visibility="public",
        auto_monitor=True,
    )
    repos.append(new_repo)
    config = repos_to_config(repos, config)
    save_config(config)
    print(f"✅ Added repository: {repo_path}")
    print(f"   Type: {repo_type}")
    print(f"   Auto-monitor: True")
    return 0


def cmd_repo_list(args) -> int:
    config = load_config()
    repos = config_to_repos(config)
    if not repos:
        print("No repositories configured.")
        print("Run: auto-evolve.py repo-add <path> --type <type>")
        return 0
    print("📦 Configured Repositories:")
    print("=" * 50)
    for i, r in enumerate(repos, 1):
        exists = "✅" if r.resolve_path().exists() else "❌"
        mon = "🟢" if r.auto_monitor else "⏭️"
        vis = "🔒" if r.is_closed() else "🌐"
        print(f"{i}. {exists} {mon} {vis} {r.path}")
        print(f"   Type: {r.type} | Visibility: {r.visibility}")
        print(f"   Auto-monitor: {r.auto_monitor} | Scan interval: {r.scan_interval_hours}h")
        if r.risk_override:
            print(f"   Risk override: {r.risk_override}")
        if r.resolve_path().exists():
            det = detect_repo_languages(r.resolve_path())
            if det:
                print(f"   Languages: {', '.join(sorted(det))}")
        print()
    return 0


def cmd_rollback(args) -> int:
    version = args.to
    item_id = getattr(args, "item", None)
    reason = args.reason or "User-initiated rollback"

    catalog = load_catalog()
    iteration_ids = [i["version"] for i in catalog["iterations"]]

    if version not in iteration_ids:
        print(f"❌ Version {version} not found.")
        print("Available versions:")
        for vid in iteration_ids:
            print(f"  - {vid}")
        return 1

    iter_data = load_iteration(version)
    rollback_iter_id = generate_iteration_id()

    print(f"⚠️  Rolling back iteration {version}")
    if item_id is not None:
        print(f"   Cherry-pick mode: only item #{item_id}")
    print(f"   Reason: {reason}")

    items = iter_data.get("items_pending_approval", [])
    repos_affected: dict[str, list] = {}
    for item in items:
        rp = item.get("repo_path", "")
        repos_affected.setdefault(rp, []).append(item)

    reverted = 0
    for repo_path_str, repo_items in repos_affected.items():
        repo_obj = Repository(path=repo_path_str, type="skill")
        if not repo_obj.resolve_path().exists():
            print(f"  ⚠️  Repo not found: {repo_path_str}")
            continue

        items_to_revert = repo_items
        if item_id is not None:
            items_to_revert = [i for i in repo_items if i.get("id") == item_id]
            if not items_to_revert:
                print(f"  Item {item_id} not found in {repo_path_str}")
                continue

        try:
            commits = git_log(repo_obj, limit=len(repo_items) + 1)
            for commit in commits[: len(items_to_revert)]:
                try:
                    git_revert(repo_obj, commit["hash"])
                    print(f"  ✅ Reverted: {commit['message'][:60]}")
                    reverted += 1
                except Exception as e:
                    print(f"  ⚠️  Could not revert {commit['hash']}: {e}")
        except Exception as e:
            print(f"  ❌ Git error for {repo_path_str}: {e}")

    manifest = IterationManifest(
        version=rollback_iter_id,
        date=datetime.now(timezone.utc).isoformat(),
        status="rolled-back",
        risk_level="medium",
        items_auto=0,
        items_approved=0,
        items_rejected=reverted,
        duration_seconds=0.0,
        rollback_of=version,
        rollback_reason=reason,
    )

    report_lines = [
        f"# Rollback Report — {rollback_iter_id}",
        "",
        f"**Rolled back:** {version}",
        f"**Reason:** {reason}",
        f"**Reverted items:** {reverted}",
        "",
    ]

    save_iteration(rollback_iter_id, manifest, [], [], report_lines)
    update_catalog(manifest)

    print(f"\n✅ Rollback complete: {rollback_iter_id}")
    print(f"   Reverted: {reverted} items from {version}")
    if item_id is not None:
        print(f"   (cherry-pick: only item #{item_id})")
    return 0


def cmd_release(args) -> int:
    version = args.version
    changelog = args.changelog or ""
    config = load_config()
    repos = config_to_repos(config)
    if not repos:
        print("No repositories configured.")
        return 1
    if len(repos) > 1:
        print("Multiple repos -- creating release for first repo.")
    repo = repos[0]
    if not repo.resolve_path().exists():
        print("Repository not found: " + repo.path)
        return 1
    print("Creating release v" + version.lstrip("v") + " for " + repo.path + "...")
    try:
        create_release(repo, version, changelog)
        print("Release v" + version.lstrip("v") + " created successfully")
    except Exception as e:
        print("Release failed: " + str(e))
        return 1
    return 0


def cmd_schedule(args) -> int:
    """
    v3.2: Schedule management with smart scheduling.
    --suggest: Show activity-based scheduling recommendations
    --auto: Apply recommendations to config
    --every: Set interval (creates cron)
    --show: Show current schedule
    --remove: Remove cron job
    """
    config = load_config()

    if args.remove:
        removed = remove_cron()
        if removed:
            print("✅ Cron job removed via openclaw CLI.")
        else:
            print("# Remove auto-evolve cron job manually:")
            print("openclaw cron remove auto-evolve-scan")
            print()
            print("Or manually delete the cron in your OpenClaw config.")
        return 0

    if args.show:
        interval = config.get("schedule_interval_hours", 168)
        cron_id = config.get("schedule_cron_id")
        print("# Auto-Evolve Schedule Configuration")
        print("#")
        if cron_id:
            print(f"# Cron ID: {cron_id}")
        print(f"# Current interval: every {interval} hour(s)")
        print()
        print("# To change interval, run:")
        print(f"#   auto-evolve.py schedule --every {interval}")
        return 0

    if args.suggest:
        return _schedule_suggest(config)

    if args.auto:
        return _schedule_auto(config)

    if args.every:
        interval = args.every
        if interval < 1:
            print("❌ Interval must be at least 1 hour.")
            return 1
        config["schedule_interval_hours"] = interval
        save_config(config)
        print(f"✅ Schedule interval set to {interval} hour(s)")
        cron_created = setup_cron(interval)
        if cron_created:
            print(f"✅ Cron job created via openclaw CLI (ID: {config.get('schedule_cron_id', 'unknown')})")
        else:
            print()
            print("⚠️  openclaw CLI not available — create cron manually:")
            print(f"  openclaw cron add --name auto-evolve-scan \\")
            print(f"    --every {interval}h \\")
            print(f"    --message 'exec python3 {SKILL_DIR}/scripts/auto-evolve.py scan'")
        return 0

    # No subcommand
    print("auto-evolve.py schedule --every HOURS   Set scan interval (creates cron)")
    print("auto-evolve.py schedule --suggest        Smart scheduling recommendations (v3.2)")
    print("auto-evolve.py schedule --auto           Apply recommended intervals (v3.2)")
    print("auto-evolve.py schedule --show            Show current schedule")
    print("auto-evolve.py schedule --remove          Remove cron job")
    return 0


def _schedule_suggest(config: dict) -> int:
    """Show smart scheduling recommendations."""
    scheduler = SmartScheduler(config)
    suggestions = scheduler.suggest_schedule()
    if not suggestions:
        print("No repositories configured.")
        return 0
    print("📊 Smart Schedule Suggestions")
    print("=" * 60)
    activity_icons = {"very_active": "🔥", "active": "⚡", "normal": "📅", "idle": "💤"}
    for path, sug in suggestions.items():
        icon = activity_icons.get(sug["activity"], "📦")
        action_icon = {"increase": "⬆️", "decrease": "⬇️", "maintain": "➡️"}.get(sug["action"], "➡️")
        print(f"\n{icon} {sug['name']} ({path})")
        print(f"   Activity: {sug['activity']} ({sug['commits_last_7_days']} commits/7d)")
        print(f"   Current interval:  {sug['current_interval_hours']}h")
        print(f"   Recommended:       {sug['recommended_interval_hours']}h {action_icon}")
        if sug["change_hours"] != 0:
            print(f"   → Change by {abs(sug['change_hours'])}h ({sug['action']})")
    print("\n💡 Apply with: auto-evolve.py schedule --auto")
    return 0


def _schedule_auto(config: dict) -> int:
    """Auto-apply scheduling recommendations."""
    scheduler = SmartScheduler(config)
    suggestions = scheduler.suggest_schedule()
    if not suggestions:
        print("No repositories configured.")
        return 0
    updates: dict[str, int] = {}
    for path, sug in suggestions.items():
        if sug["action"] != "maintain":
            updates[path] = sug["recommended_interval_hours"]
    if not updates:
        print("✅ All repositories already at recommended intervals.")
        return 0
    result = scheduler.apply_schedule(updates)
    print("✅ Applied schedule changes:")
    for a in result["applied"]:
        print(f"   {a['path']}: {a['old_interval']}h → {a['new_interval']}h")
    return 0


def cmd_set_mode(args) -> int:
    mode = args.mode
    if mode not in ("semi-auto", "full-auto"):
        print(f"❌ Invalid mode. Must be 'semi-auto' or 'full-auto'.")
        return 1
    config = load_config()
    old_mode = config.get("mode", "semi-auto")
    config["mode"] = mode
    save_config(config)
    mode_desc = {
        "semi-auto": "semi-auto (confirm before execution)",
        "full-auto": "full-auto (execute per rules)",
    }
    print(f"✅ Mode changed: {old_mode} → {mode}")
    print(f"   {mode_desc.get(mode, mode)}")
    return 0


def cmd_set_rules(args) -> int:
    config = load_config()
    rules = config.get("full_auto_rules", {})
    rules["execute_low_risk"] = (
        args.low if args.low is not None else rules.get("execute_low_risk", True)
    )
    rules["execute_medium_risk"] = (
        args.medium if args.medium is not None else rules.get("execute_medium_risk", False)
    )
    rules["execute_high_risk"] = (
        args.high if args.high is not None else rules.get("execute_high_risk", False)
    )
    config["full_auto_rules"] = rules
    save_config(config)
    print("✅ Full-auto rules updated:")
    print(f"   execute_low_risk:    {rules['execute_low_risk']}")
    print(f"   execute_medium_risk: {rules['execute_medium_risk']}")
    print(f"   execute_high_risk:   {rules['execute_high_risk']}")
    return 0


def cmd_learnings(args) -> int:
    data = load_learnings()

    if args.type == "rejections" or args.type is None:
        rejections = data.get("rejections", [])
        print(f"📕 Rejections ({len(rejections)} total):")
        print("=" * 50)
        if not rejections:
            print("  (none)")
        for r in rejections[: args.limit or 20]:
            print(f"  [{r['date']}] {r['repo'].split('/')[-1]}")
            print(f"    {r['description'][:70]}")
            if r.get("reason"):
                print(f"    Reason: {r['reason']}")
            print()

    if args.type == "approvals" or args.type is None:
        approvals = data.get("approvals", [])
        print(f"📗 Approvals ({len(approvals)} total):")
        print("=" * 50)
        if not approvals:
            print("  (none)")
        for a in approvals[: args.limit or 20]:
            print(f"  [{a['date']}] {a['repo'].split('/')[-1]}")
            print(f"    {a['description'][:70]}")
            if a.get("reason"):
                print(f"    Reason: {a['reason']}")
            if a.get("approved_by"):
                print(f"    Approved by: {a['approved_by']}")
            print()

    if args.type not in ("rejections", "approvals", None):
        print(f"❌ Unknown type: {args.type}. Use --type rejections or --type approvals.")
        return 1
    return 0


def cmd_log(args) -> int:
    catalog = load_catalog()
    if not catalog["iterations"]:
        print("No iterations recorded yet.")
        return 0
    print("📚 Iteration Log")
    print("=" * 50)
    limit = args.limit or 10
    for iteration in catalog["iterations"][:limit]:
        status_icon = {
            "completed": "✅",
            "pending-approval": "⏳",
            "full-auto-completed": "⚡",
            "dry-run": "⚡",
            "rolled-back": "🔄",
        }.get(iteration["status"], "❓")

        alert_flag = " 🚨" if iteration.get("has_alert") else ""
        cost_str = ""
        if iteration.get("total_cost_usd"):
            cost_str = f" 💰${iteration['total_cost_usd']:.4f}"
        llm_str = f" 🤖{iteration.get('llm_calls', 0)}calls" if iteration.get("llm_calls", 0) > 0 else ""

        print(f"\n{status_icon} {iteration['version']}{alert_flag}{cost_str}{llm_str}")
        print(f"   Date: {iteration['date']}")
        print(f"   Status: {iteration['status']}")
        print(f"   Risk: {iteration.get('risk_level', 'unknown')}")
        if iteration.get("items_auto"):
            print(f"   Auto: {iteration['items_auto']}")
        if iteration.get("items_approved"):
            print(f"   Approved: {iteration['items_approved']}")
        if iteration.get("items_rejected"):
            print(f"   Rejected: {iteration['items_rejected']}")
        if iteration.get("rollback_of"):
            print(f"   Rolled back: {iteration['rollback_of']}")
        if iteration.get("has_alert"):
            print(f"   🚨 Alert: quality gate failed")
    return 0


# ===========================================================
# v3.2: effects command
# ===========================================================

def cmd_effects(args) -> int:
    """Show effect tracking reports for iterations."""
    iteration_id = args.iteration_id

    catalog = load_catalog()
    if not catalog["iterations"]:
        print("No iterations found.")
        return 0

    if iteration_id:
        target_iter = next((i for i in catalog["iterations"] if i["version"] == iteration_id), None)
        if not target_iter:
            print(f"Iteration {iteration_id} not found.")
            return 1
        iteration_ids = [iteration_id]
    else:
        iteration_ids = [i["version"] for i in catalog["iterations"][: args.limit or 5]]

    for iid in iteration_ids:
        effect_file = ITERATIONS_DIR / iid / "effect.json"
        if not effect_file.exists():
            continue
        effect = json.loads(effect_file.read_text())
        verdict_icon = {"positive": "✅", "neutral": "➖", "negative": "❌"}.get(effect["verdict"], "➖")
        print(f"\n{verdict_icon} Iteration {iid} — {effect['verdict'].upper()}")
        print(f"   Date: {effect['date']}")
        print(f"   Summary: {effect['summary']}")
        totals = effect.get("totals", {})
        if totals.get("todos_resolved"):
            print(f"   TODOs resolved: {totals['todos_resolved']}")
        if totals.get("coverage_delta"):
            print(f"   Coverage delta: {totals['coverage_delta']:+.1f}%")
        if totals.get("duplicate_lines_delta"):
            print(f"   Duplicate lines: {totals['duplicate_lines_delta']:+,}")
        if totals.get("code_lines_delta"):
            print(f"   Code lines: {totals['code_lines_delta']:+,}")

    if not iteration_ids:
        print("No effect reports found. Run a scan first.")
    return 0


# ===========================================================
# v3.2: costs command
# ===========================================================

def cmd_costs(args) -> int:
    """Show LLM cost tracking for iterations."""
    iteration_id = args.iteration_id

    catalog = load_catalog()
    if not catalog["iterations"]:
        print("No iterations found.")
        return 0

    if iteration_id:
        target_iter = next((i for i in catalog["iterations"] if i["version"] == iteration_id), None)
        if not target_iter:
            print(f"Iteration {iteration_id} not found.")
            return 1
        iteration_ids = [iteration_id]
    else:
        iteration_ids = [i["version"] for i in catalog["iterations"][: args.limit or 5]]

    cost_tracker = CostTracker()
    total_all = 0.0
    total_calls = 0

    for iid in iteration_ids:
        cost_summary = cost_tracker.get_iteration_cost(iid)
        if cost_summary["total_calls"] == 0:
            continue
        total_all += cost_summary["total_cost_usd"]
        total_calls += cost_summary["total_calls"]
        print(f"\n💰 Iteration {iid}")
        print(f"   Calls: {cost_summary['total_calls']}")
        print(f"   Tokens: {cost_summary['total_tokens']:,}")
        print(f"   Cost: ${cost_summary['total_cost_usd']:.6f}")

        # Show per-model breakdown
        calls = cost_tracker.load_calls(iid)
        by_model: dict[str, dict] = {}
        for call in calls:
            model = call["model"]
            by_model.setdefault(model, {"calls": 0, "tokens": 0, "cost": 0.0})
            by_model[model]["calls"] += 1
            by_model[model]["tokens"] += call["total_tokens"]
            by_model[model]["cost"] += call["estimated_cost_usd"]
        for model, stats in by_model.items():
            print(f"   [{model}] {stats['calls']} calls, {stats['tokens']:,} tokens, ${stats['cost']:.6f}")

    if total_calls == 0:
        print("No LLM costs recorded. Run a scan with LLM analysis.")
    else:
        print(f"\n💰 TOTAL: {total_calls} calls, ${total_all:.6f}")
    return 0


# ===========================================================
# CLI Entry Point
# ===========================================================

def _build_argument_parser() -> argparse.ArgumentParser:
    """Build and return the root argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        description="Auto-Evolve v3.3 — LLM-driven automated skill iteration manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    scan_p = subparsers.add_parser("scan", help="Scan and evolve skills")
    scan_p.add_argument("--dry-run", action="store_true", help="Preview only, no commits")

    # confirm
    confirm_p = subparsers.add_parser("confirm", help="Confirm pending changes (semi-auto mode)")
    confirm_p.add_argument("--iteration", dest="iteration_id", type=str, help="Iteration ID")

    # reject
    reject_p = subparsers.add_parser("reject", help="Reject a pending change")
    reject_p.add_argument("id", type=int, help="Item ID to reject")
    reject_p.add_argument("--reason", type=str, help="Rejection reason")
    reject_p.add_argument("--iteration", dest="iteration_id", type=str, help="Iteration ID")

    # approve
    approve_p = subparsers.add_parser("approve", help="Approve pending changes")
    approve_p.add_argument("--all", action="store_true", help="Approve all pending items")
    approve_p.add_argument("--ids", type=str, help="Comma-separated IDs (e.g. 1,2,3)")
    approve_p.add_argument("ids", nargs="?", type=str, help="IDs to approve (positional)")
    approve_p.add_argument("--iteration", dest="iteration_id", type=str, help="Iteration ID")
    approve_p.add_argument("--reason", type=str, help="Reason for approval (recorded in learnings)")

    # repo-add
    repo_add_p = subparsers.add_parser("repo-add", help="Add a repository to monitor")
    repo_add_p.add_argument("path", type=str, help="Repository path")
    repo_add_p.add_argument("--type", type=str, choices=REPO_TYPES, help="Repository type")
    repo_add_p.add_argument("--monitor", action="store_true", default=True, help="Enable auto-monitor")

    # repo-list
    subparsers.add_parser("repo-list", help="List configured repositories")

    # rollback
    rollback_p = subparsers.add_parser("rollback", help="Rollback to a previous iteration")
    rollback_p.add_argument("--to", required=True, dest="to", type=str, help="Target version")
    rollback_p.add_argument("--reason", type=str, help="Rollback reason")
    rollback_p.add_argument("--item", type=int, dest="item", help="Cherry-pick: only rollback specific item ID")

    # release
    release_p = subparsers.add_parser("release", help="Create a GitHub release")
    release_p.add_argument("--version", required=True, dest="version", type=str, help="Version tag (e.g. 2.3.0)")
    release_p.add_argument("--changelog", type=str, default="", help="Changelog / release notes")

    # schedule (v3.2)
    schedule_p = subparsers.add_parser("schedule", help="Schedule management (cron setup)")
    schedule_p.add_argument("--every", type=int, help="Set scan interval in hours")
    schedule_p.add_argument("--suggest", action="store_true", help="Smart scheduling recommendations (v3.2)")
    schedule_p.add_argument("--auto", action="store_true", help="Apply recommended intervals (v3.2)")
    schedule_p.add_argument("--show", action="store_true", help="Show current schedule")
    schedule_p.add_argument("--remove", action="store_true", help="Remove cron job")

    # set-mode
    set_mode_p = subparsers.add_parser("set-mode", help="Set operation mode")
    set_mode_p.add_argument("mode", type=str, choices=["semi-auto", "full-auto"], help="Mode")

    # set-rules
    set_rules_p = subparsers.add_parser("set-rules", help="Set full-auto execution rules")
    set_rules_p.add_argument("--low", type=lambda x: x.lower() == "true", help="Execute low-risk (true/false)")
    set_rules_p.add_argument("--medium", type=lambda x: x.lower() == "true", help="Execute medium-risk (true/false)")
    set_rules_p.add_argument("--high", type=lambda x: x.lower() == "true", help="Execute high-risk (true/false)")

    # learnings
    learnings_p = subparsers.add_parser("learnings", help="Show learning history")
    learnings_p.add_argument("--type", type=str, choices=["rejections", "approvals"], help="Filter by type")
    learnings_p.add_argument("--limit", type=int, default=20, help="Limit entries")

    # log
    log_p = subparsers.add_parser("log", help="Show iteration log")
    log_p.add_argument("--limit", type=int, default=10, help="Limit entries")

    # effects (v3.2)
    effects_p = subparsers.add_parser("effects", help="Show effect tracking reports (v3.2)")
    effects_p.add_argument("--iteration", dest="iteration_id", type=str, help="Specific iteration ID")
    effects_p.add_argument("--limit", type=int, default=5, help="Limit iterations shown")

    # costs (v3.2)
    costs_p = subparsers.add_parser("costs", help="Show LLM cost tracking (v3.2)")
    costs_p.add_argument("--iteration", dest="iteration_id", type=str, help="Specific iteration ID")
    costs_p.add_argument("--limit", type=int, default=5, help="Limit iterations shown")

    return parser


def main() -> int:
    parser = _build_argument_parser()
    args = parser.parse_args()

    commands: dict[str, callable] = {
        "scan": cmd_scan,
        "confirm": cmd_confirm,
        "reject": cmd_reject,
        "approve": cmd_approve,
        "repo-add": cmd_repo_add,
        "repo-list": cmd_repo_list,
        "rollback": cmd_rollback,
        "release": cmd_release,
        "schedule": cmd_schedule,
        "set-mode": cmd_set_mode,
        "set-rules": cmd_set_rules,
        "learnings": cmd_learnings,
        "log": cmd_log,
        "effects": cmd_effects,
        "costs": cmd_costs,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

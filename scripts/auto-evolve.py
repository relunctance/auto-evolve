#!/usr/bin/env python3
"""
Auto-Evolve v2.1 — Automated skill iteration manager.

Features (v2.1):
- Two operation modes: semi-auto (default) and full-auto
- Cron scheduling via OpenClaw cron API
- Rejection/approval learning history
- Privacy sanitization for closed repositories
- Execution preview before applying changes
- Alert generation on quality gate failure

Usage:
    auto-evolve.py scan [--dry-run]
    auto-evolve.py approve [--all | ID...]
    auto-evolve.py confirm                       # confirm pending changes (semi-auto)
    auto-evolve.py reject <id> [--reason TEXT]   # reject a pending item
    auto-evolve.py repo-add <path> --type TYPE [--monitor]
    auto-evolve.py repo-list
    auto-evolve.py rollback --to VERSION
    auto-evolve.py schedule --every HOURS
    auto-evolve.py schedule --show
    auto-evolve.py schedule --remove
    auto-evolve.py set-mode semi-auto|full-auto
    auto-evolve.py set-rules [--low] [--medium] [--high]
    auto-evolve.py log [--limit N]
    auto-evolve.py learnings                    # show learning history
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
from typing import Optional


# ===========================================================
# Constants
# ===========================================================

HOME = Path.home()
AUTO_EVOLVE_RC = HOME / ".auto-evolverc.json"
SKILL_DIR = HOME / ".openclaw" / "workspace" / "skills" / "auto-evolve"
ITERATIONS_DIR = SKILL_DIR / ".iterations"
LEARNINGS_DIR = SKILL_DIR / ".learnings"

REPO_TYPES = ("skill", "norms", "project", "closed")
RISK_LEVELS = ("low", "medium", "high")
RISK_COLORS = {
    "low": "🟢",
    "medium": "🟡",
    "high": "🔴",
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
    content_hash: Optional[str] = None  # For closed-repo sanitization


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


@dataclass
class LearningEntry:
    id: str
    type: str  # rejection or approval
    change_id: str
    description: str
    reason: Optional[str]
    date: str
    repo: str


@dataclass
class AlertEntry:
    iteration_id: str
    date: str
    alert_type: str
    message: str
    details: dict


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
    repos = []
    for r in config.get("repositories", []):
        repos.append(Repository(
            path=r["path"],
            type=r.get("type", "skill"),
            visibility=r.get("visibility", "public"),
            auto_monitor=r.get("auto_monitor", True),
            risk_override=r.get("risk_override"),
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

    data = {"rejections": [], "approvals": []}

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
) -> None:
    """Add an entry to learning history (rejections or approvals)."""
    data = load_learnings()
    entry: dict = {
        "id": hashlib.sha256(f"{change_id}{description}{datetime.now().isoformat()}".encode()).hexdigest()[:12],
        "type": learning_type,
        "change_id": str(change_id),
        "description": description,
        "reason": reason,
        "date": datetime.now(timezone.utc).date().isoformat(),
        "repo": repo,
    }

    if learning_type == "rejection":
        data["rejections"].insert(0, entry)
    else:
        data["approvals"].insert(0, entry)

    save_learnings(data)


def is_rejected(change_desc: str, repo: str, learnings: dict) -> bool:
    """Check if a change matching the description has been rejected before."""
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

    changes = []
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
    git_run(repo, "commit", "-m", message)
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
    result = git_run(
        repo, "log", "--pretty=format:%H|%s|%ad", "--date=iso", f"-n{limit}"
    )
    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({
                "hash": parts[0],
                "message": parts[1],
                "date": parts[2],
            })
    return commits


def git_diff(repo: Repository, ref: Optional[str] = None) -> str:
    if ref:
        result = git_run(repo, "diff", "--stat", ref)
    else:
        result = git_run(repo, "diff", "--stat")
    return result.stdout


def compute_file_hash(repo: Repository, file_path: str) -> Optional[str]:
    """Compute SHA256 hash of a file for closed-repo sanitization."""
    try:
        full_path = repo.resolve_path() / file_path
        if full_path.exists():
            h = hashlib.sha256()
            h.update(full_path.read_bytes())
            return h.hexdigest()[:12]
    except OSError:
        pass
    return None


# ===========================================================
# Risk Classification
# ===========================================================

def classify_change(repo: Repository, change_type: str, file_path: str) -> RiskLevel:
    default_risk = repo.get_default_risk(change_type, file_path)
    file_lower = file_path.lower()

    high_risk_patterns = [
        "remove", "delete", "deprecate", "break",
        "rename", "migrate", "architect", "security",
    ]
    if any(p in file_lower for p in high_risk_patterns):
        return RiskLevel.HIGH

    low_risk_patterns = [
        "readme", "skill.md", "changelog", ".gitignore",
        "license", "comments", "typo", "format", "lint",
        "refactor", "rename",
    ]
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

ANNOTATION_PATTERN = re.compile(
    r"(\b(TODO|FIXME|XXX|HACK|NOTE)\b.*?)$",
    re.IGNORECASE | re.MULTILINE,
)

LONG_FUNCTION_PATTERN = re.compile(
    r"^(?:def |async def |class |async def .*?\([\s\S]*?\):[ \t]*\n)",
    re.MULTILINE,
)

PINNED_VERSION = re.compile(r"==\d+\.\d+\.\d+")


def scan_optimizations(repo: Repository) -> list[OptimizationFinding]:
    findings = []
    repo_path = repo.resolve_path()

    for py_file in repo_path.rglob("*.py"):
        rel_path = py_file.relative_to(repo_path)
        findings.extend(_scan_python_file(py_file, rel_path))

    for code_file in repo_path.rglob("*"):
        if code_file.is_dir():
            continue
        if code_file.suffix.lower() not in (".py", ".js", ".ts", ".go", ".rs", ".md"):
            continue
        findings.extend(_scan_annotations(code_file, code_file.relative_to(repo_path)))

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


def _scan_annotations(
    file_path: Path,
    rel_path: Path,
    content: Optional[str] = None,
) -> list[OptimizationFinding]:
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


def _scan_duplicate_code(content: str, rel_path: Path) -> list[OptimizationFinding]:
    findings = []
    strings = re.findall(r'"{3}[\s\S]*?"{3}|"{1,2}[^"]{30,200}"{1,2}', content)
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
        mod_parts = mod.parts
        if len(mod_parts) <= 2:
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

    catalog["iterations"].insert(0, {
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
    })

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
    }

    for py_file in repo.resolve_path().rglob("*.py"):
        if not check_syntax(str(py_file)):
            results["syntax_ok"] = False
            results["syntax_errors"].append(str(py_file))
            results["passed"] = False

    return results


# ===========================================================
# Closed-Repo Sanitization
# ===========================================================

def sanitize_pending_item(item: dict, repo: Repository) -> dict:
    """Remove sensitive content from pending items for closed repos."""
    if not repo.is_closed():
        return item

    sanitized = dict(item)
    # Remove file_path details — replace with hash reference
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

    # Remove description specifics for closed repos
    sanitized["description"] = "[CLOSED REPO] Change requires manual review"
    sanitized["content_redacted"] = True

    return sanitized


def sanitize_change_for_log(change: ChangeItem, repo: Repository) -> str:
    """Return sanitized change representation for log files."""
    if not repo.is_closed():
        return f"{change.change_type}: {change.file_path}"

    # Closed repo: only show type, no file content
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
    """Print a preview of what will be executed."""
    if mode == OperationMode.SEMI_AUTO:
        print("\n⚠️  Semi-Auto Mode: About to execute auto-changes:")
    else:
        print("\n⚠️  Full-Auto Mode: About to execute changes:")

    print(f"  Total: {len(auto_exec)} change(s)")
    for i, c in enumerate(auto_exec, 1):
        color = RISK_COLORS.get(c.risk.value, "⚪")
        opt_badge = " [opt]" if c.category == ChangeCategory.OPTIMIZATION else ""
        print(f"  [{i}] {color} {c.risk.value.upper()}: {c.description[:60]}{opt_badge}")

    print()


# ===========================================================
# Main Scan Logic
# ===========================================================

def run_scan(
    repo: Repository,
    dry_run: bool = False,
    learnings: Optional[dict] = None,
) -> tuple[list[ChangeItem], list[OptimizationFinding], list[str]]:
    changes = []
    opts = []
    plan_lines = []
    change_id = 1
    learnings = learnings or {"rejections": [], "approvals": []}

    # 1. Git changes
    git_changes = git_status(repo)
    for gc in git_changes:
        # Skip if previously rejected
        if is_rejected(gc["file"], repo.path, learnings):
            continue

        risk = classify_change(repo, gc["type"], gc["file"])
        category = ChangeCategory.AUTO_EXEC if risk == RiskLevel.LOW else ChangeCategory.PENDING_APPROVAL
        changes.append(ChangeItem(
            id=change_id,
            description=f"{gc['type']}: {gc['file']}",
            file_path=gc["file"],
            change_type=gc["type"],
            risk=risk,
            category=category,
            repo_path=repo.path,
            repo_type=repo.type,
        ))
        change_id += 1

    # 2. Proactive optimizations
    opts = scan_optimizations(repo)
    for o in opts:
        # Skip if previously rejected
        if is_rejected(o.description, repo.path, learnings):
            continue

        risk = o.risk
        changes.append(ChangeItem(
            id=change_id,
            description=f"[opt] {o.type}: {o.description}",
            file_path=o.file_path,
            change_type="optimization",
            risk=risk,
            category=ChangeCategory.OPTIMIZATION,
            repo_path=repo.path,
            repo_type=repo.type,
            optimization_type=o.type,
        ))
        change_id += 1

    return changes, opts, plan_lines


# ===========================================================
# Pending Review (Semi-Auto Mode)
# ===========================================================

def load_pending_review(iteration_id: str) -> list[dict]:
    """Load pending items for a given iteration."""
    try:
        return json.loads((ITERATIONS_DIR / iteration_id / "pending-review.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_pending_review(iteration_id: str, items: list[dict]) -> None:
    """Save pending review items."""
    (ITERATIONS_DIR / iteration_id / "pending-review.json").write_text(json.dumps(items, indent=2))


# ===========================================================
# Commands
# ===========================================================

def cmd_scan(args) -> int:
    config = load_config()
    dry_run = args.dry_run
    mode = get_operation_mode(config)
    rules = get_full_auto_rules(config)
    learnings = load_learnings()

    print("🔍 Auto-Evolve v2.1 Scanner")
    print(f"   Mode: {mode.value}")
    print("=" * 50)

    start_time = time.time()
    repos = config_to_repos(config)
    all_changes: list[ChangeItem] = []
    all_opts: list[OptimizationFinding] = []
    iteration_id = generate_iteration_id()

    for repo in repos:
        if not repo.auto_monitor:
            print(f"\n⏭️  Skipping {repo.path} (auto_monitor=false)")
            continue

        if not repo.resolve_path().exists():
            print(f"\n⚠️  Repository not found: {repo.path}")
            continue

        print(f"\n📦 Scanning: {repo.path} ({repo.type})")

        # Run quality gates
        qg = run_quality_gates(repo)
        if not qg["passed"]:
            print(f"  ⚠️  Quality gate failed: {len(qg['syntax_errors'])} syntax error(s)")
            alert = AlertEntry(
                iteration_id=iteration_id,
                date=datetime.now(timezone.utc).isoformat(),
                alert_type="quality_gate_failed",
                message="Syntax errors detected in repository",
                details={"errors": qg["syntax_errors"]},
            )
        else:
            alert = None

        changes, opts, _ = run_scan(repo, dry_run=dry_run, learnings=learnings)
        all_changes.extend(changes)
        all_opts.extend(opts)

    duration = time.time() - start_time

    # Categorize
    auto_exec = [
        c for c in all_changes
        if c.category == ChangeCategory.AUTO_EXEC and c.risk == RiskLevel.LOW
    ]
    pending = [
        c for c in all_changes
        if c.category in (ChangeCategory.PENDING_APPROVAL, ChangeCategory.OPTIMIZATION)
    ]

    print(f"\n📊 Scan Results:")
    print(f"  Changes detected: {len(all_changes) - len(all_opts)}")
    print(f"  Optimizations found: {len(all_opts)}")
    print(f"  Auto-executable:     {len(auto_exec)}")
    print(f"  Pending review:      {len(pending)}")

    # Execution preview
    if auto_exec and not dry_run:
        print_execution_preview(all_changes, auto_exec, mode, rules)

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
        f"- Pending review: {len(pending)}",
        "",
    ]

    # Build pending items (with sanitization for closed repos)
    pending_items: list[dict] = []
    for c in pending:
        repo = Repository(path=c.repo_path, type=c.repo_type)
        item = {
            "id": c.id,
            "description": c.description,
            "file_path": c.file_path,
            "risk": c.risk.value,
            "category": c.category.value,
            "repo_path": c.repo_path,
            "optimization_type": c.optimization_type,
        }
        if repo.is_closed():
            item = sanitize_pending_item(item, repo)
        pending_items.append(item)

    # Mode-specific execution
    auto_executed: list[ChangeItem] = []
    iteration_status = "dry-run" if dry_run else mode.value

    if mode == OperationMode.FULL_AUTO and not dry_run:
        # Full-auto: execute according to rules, then pending for remainder
        for change in auto_exec:
            if should_auto_execute(rules, change.risk):
                try:
                    repo = Repository(path=change.repo_path, type=change.repo_type)
                    commit_hash = git_commit(repo, f"auto: {change.description}")
                    change.commit_hash = commit_hash
                    auto_executed.append(change)
                    # Log sanitized for closed repos
                    log_desc = sanitize_change_for_log(change, repo)
                    print(f"  ✅ {log_desc} ({commit_hash})")
                except Exception as e:
                    print(f"  ❌ {change.file_path}: {e}")

        remaining_pending = pending
        iteration_status = "full-auto-completed"

    elif mode == OperationMode.SEMI_AUTO and not dry_run:
        # Semi-auto: in semi-auto, auto_exec is NOT executed until confirmed
        # pending items remain pending for review
        remaining_pending = auto_exec + pending
        iteration_status = "pending-approval"

        if auto_exec:
            print(f"\n📋 {len(auto_exec)} auto-changes held for confirmation (semi-auto mode)")
            print(f"   Run `auto-evolve.py confirm` after reviewing pending items")

    else:
        remaining_pending = auto_exec + pending

    # Pending items display
    if remaining_pending:
        print(f"\n📋 Pending Items ({len(remaining_pending)}):")
        display_items = remaining_pending[:20]
        for i, c in enumerate(display_items, 1):
            risk_icon = RISK_COLORS.get(c.risk.value, "⚪")
            opt_badge = " [opt]" if c.category == ChangeCategory.OPTIMIZATION else ""
            print(f"  [{i}] {risk_icon} {c.risk.value.upper()} {c.description[:60]}{opt_badge}")

        if len(remaining_pending) > 20:
            print(f"  ... and {len(remaining_pending) - 20} more")

        plan_lines.extend([
            f"## Pending Items ({len(remaining_pending)})",
            "",
        ])
        for i, c in enumerate(remaining_pending, 1):
            plan_lines.append(f"- [{i}] **{c.risk.value.upper()}** {c.description}")

    # Push auto-executed
    if auto_executed and not dry_run:
        repos_affected: set[str] = set(c.repo_path for c in auto_executed)
        for rp in repos_affected:
            repo = Repository(path=rp, type="skill")
            try:
                git_push(repo)
                print(f"  📤 Pushed to remote")
            except Exception as e:
                print(f"  ⚠️  Push failed: {e}")

    # Build manifest
    manifest = IterationManifest(
        version=iteration_id,
        date=datetime.now(timezone.utc).isoformat(),
        status=iteration_status,
        risk_level="mixed",
        items_auto=len(auto_executed),
        items_approved=0,
        items_rejected=0,
        items_optimization=len(all_opts),
        duration_seconds=round(duration, 1),
        items_pending_approval=pending_items,
        has_alert=alert is not None,
    )

    save_iteration(iteration_id, manifest, plan_lines, pending_items, report_lines, alert)
    update_catalog(manifest)

    print(f"\n📁 Iteration {iteration_id} saved to .iterations/{iteration_id}/")
    print(f"   pending-review.json: {len(pending_items)} items")

    if mode == OperationMode.SEMI_AUTO and auto_exec and not dry_run:
        print(f"\n   Confirm with: auto-evolve.py confirm")

    if dry_run:
        print("\n⚠️  Dry-run mode — no changes committed")

    return 0


def cmd_confirm(args) -> int:
    """Confirm and execute pending changes in semi-auto mode."""
    config = load_config()
    iteration_id = args.iteration_id

    # Find iteration
    catalog = load_catalog()
    if not catalog["iterations"]:
        print("No iterations found.")
        return 1

    if iteration_id:
        target_iter = next(
            (i for i in catalog["iterations"] if i["version"] == iteration_id),
            None,
        )
        if not target_iter:
            print(f"Iteration {iteration_id} not found.")
            return 1
    else:
        target_iter = next(
            (i for i in catalog["iterations"] if i["status"] == "pending-approval"),
            None,
        )
        if not target_iter:
            print("No pending-approval iteration found.")
            return 1

    iteration_id = target_iter["version"]

    try:
        manifest_data = load_iteration(iteration_id)
        pending_items = manifest_data.get("items_pending_approval", [])
    except FileNotFoundError:
        print(f"Iteration {iteration_id} manifest not found.")
        return 1

    if not pending_items:
        print(f"No pending items in iteration {iteration_id}.")
        return 0

    print(f"Confirming {len(pending_items)} pending items from {iteration_id}...")

    # Group by repo
    repos_affected: set[str] = set(p.get("repo_path", "") for p in pending_items)
    confirmed_count = 0

    for rp in repos_affected:
        repo = Repository(path=rp, type="skill")
        if not repo.resolve_path().exists():
            continue

        repo_items = [p for p in pending_items if p.get("repo_path") == rp]
        for p in repo_items:
            try:
                commit_msg = f"auto-evolve: {p['description']}"
                commit_hash = git_commit(repo, commit_msg)
                print(f"  ✅ [{p['id']}] {p['description'][:60]} ({commit_hash})")
                confirmed_count += 1

                # Record approval in learnings
                add_learning(
                    learning_type="approval",
                    change_id=str(p["id"]),
                    description=p["description"],
                    reason=None,
                    repo=rp,
                )
            except Exception as e:
                print(f"  ❌ [{p['id']}] {p['description'][:60]}: {e}")

    # Push
    for rp in repos_affected:
        repo = Repository(path=rp, type="skill")
        try:
            git_push(repo)
        except Exception as e:
            print(f"  ⚠️  Push failed for {rp}: {e}")

    # Update manifest
    manifest_data["items_approved"] = confirmed_count
    manifest_data["status"] = "completed"
    (ITERATIONS_DIR / iteration_id / "manifest.json").write_text(
        json.dumps(manifest_data, indent=2)
    )

    for i, cat_iter in enumerate(catalog["iterations"]):
        if cat_iter["version"] == iteration_id:
            catalog["iterations"][i]["status"] = "completed"
            catalog["iterations"][i]["items_approved"] = confirmed_count

    (ITERATIONS_DIR / "catalog.json").write_text(json.dumps(catalog, indent=2))

    print(f"\n✅ Confirmed and executed {confirmed_count} items")
    return 0


def cmd_reject(args) -> int:
    """Reject a pending change and record in learnings."""
    change_id = args.id
    reason = args.reason
    iteration_id = args.iteration_id

    catalog = load_catalog()

    # Find target iteration
    if iteration_id:
        target_iter = next(
            (i for i in catalog["iterations"] if i["version"] == iteration_id),
            None,
        )
        if not target_iter:
            print(f"Iteration {iteration_id} not found.")
            return 1
    else:
        target_iter = next(
            (i for i in catalog["iterations"] if i["status"] == "pending-approval"),
            None,
        )
        if not target_iter:
            print("No pending-approval iteration found.")
            return 1

    iteration_id = target_iter["version"]

    try:
        manifest_data = load_iteration(iteration_id)
        pending_items = manifest_data.get("items_pending_approval", [])
    except FileNotFoundError:
        print(f"Iteration {iteration_id} manifest not found.")
        return 1

    # Find the item
    item = next((p for p in pending_items if p.get("id") == change_id), None)
    if not item:
        print(f"Item {change_id} not found in pending items.")
        return 1

    # Record rejection
    add_learning(
        learning_type="rejection",
        change_id=str(change_id),
        description=item["description"],
        reason=reason,
        repo=item.get("repo_path", ""),
    )

    # Remove from pending
    pending_items = [p for p in pending_items if p.get("id") != change_id]
    save_pending_review(iteration_id, pending_items)

    manifest_data["items_pending_approval"] = pending_items
    manifest_data["items_rejected"] = manifest_data.get("items_rejected", 0) + 1
    (ITERATIONS_DIR / iteration_id / "manifest.json").write_text(
        json.dumps(manifest_data, indent=2)
    )

    print(f"❌ Rejected item {change_id}: {item['description'][:60]}")
    if reason:
        print(f"   Reason: {reason}")
    print(f"   Recorded in .learnings/rejections.json")

    return 0


def cmd_approve(args) -> int:
    """Approve and execute pending changes (direct execution, bypasses confirm)."""
    config = load_config()
    iteration_id = args.iteration_id
    approve_all = args.all

    catalog = load_catalog()
    if not catalog["iterations"]:
        print("No iterations found.")
        return 1

    if iteration_id:
        target_iter = next(
            (i for i in catalog["iterations"] if i["version"] == iteration_id),
            None,
        )
        if not target_iter:
            print(f"Iteration {iteration_id} not found.")
            return 1
    else:
        target_iter = next(
            (i for i in catalog["iterations"] if i["status"] in ("pending-approval", "full-auto-completed")),
            None,
        )
        if not target_iter:
            print("No pending iteration found.")
            return 1

    iteration_id = target_iter["version"]

    try:
        manifest_data = load_iteration(iteration_id)
        pending_items = manifest_data.get("items_pending_approval", [])
    except FileNotFoundError:
        print(f"Iteration {iteration_id} manifest not found.")
        return 1

    if not pending_items:
        print(f"No pending items in iteration {iteration_id}.")
        return 0

    if approve_all:
        approved_ids = [p["id"] for p in pending_items]
        print(f"✅ Approving all {len(approved_ids)} pending items...")
    else:
        ids_str = getattr(args, "ids", None)
        if ids_str:
            try:
                approved_ids = [int(x.strip()) for x in str(ids_str).split(",") if x.strip()]
            except ValueError:
                print("Invalid IDs. Use: approve 1,2,3")
                return 1
        else:
            print(f"Iteration: {iteration_id}")
            print(f"Pending items ({len(pending_items)}):")
            for p in pending_items:
                risk_icon = RISK_COLORS.get(p.get("risk", "medium"), "⚪")
                print(f"  [{p['id']}] {risk_icon} {p.get('risk', '?').upper()} {p.get('description', '')[:60]}")
            print("\nRun: auto-evolve.py approve --all")
            print("Or:  auto-evolve.py approve 1,3 (specific items)")
            return 0

    # Execute approved changes
    approved_count = 0
    for p in pending_items:
        if p["id"] not in approved_ids:
            continue

        repo = Repository(path=p["repo_path"], type=p.get("repo_type", "skill"))

        if not repo.resolve_path().exists():
            print(f"  ⚠️  Repo not found: {repo.path}")
            continue

        if p.get("risk") == "high":
            print(f"\n🔴 High-risk: {p['description'][:60]}")
            print(f"  Creating branch and PR...")
            branch = create_branch_for_change(repo, p["description"][:50])
            try:
                commit_hash = git_commit(repo, f"auto-evolve: {p['description']}")
                pr_url = create_pr(
                    repo, branch, p["description"],
                    [ChangeItem(
                        id=p["id"],
                        description=p["description"],
                        file_path=p["file_path"],
                        change_type="approved",
                        risk=RiskLevel.HIGH,
                        category=ChangeCategory.PENDING_APPROVAL,
                        repo_path=repo.path,
                    )],
                )
                print(f"  ✅ Branch: {branch}")
                print(f"  ✅ Commit: {commit_hash}")
                print(f"  🔗 {pr_url}")
            except Exception as e:
                print(f"  ❌ Failed: {e}")
            approved_count += 1
        else:
            try:
                commit_hash = git_commit(repo, f"auto-evolve: {p['description']}")
                print(f"  ✅ [{p['id']}] {p['description'][:60]} ({commit_hash})")
                approved_count += 1

                add_learning(
                    learning_type="approval",
                    change_id=str(p["id"]),
                    description=p["description"],
                    reason=None,
                    repo=repo.path,
                )
            except Exception as e:
                print(f"  ❌ [{p['id']}] {p['description'][:60]}: {e}")

    # Push
    if approved_count > 0:
        repos_affected: set[str] = set(
            p["repo_path"] for p in pending_items if p["id"] in approved_ids
        )
        for rp in repos_affected:
            repo = Repository(path=rp, type="skill")
            try:
                git_push(repo)
            except Exception as e:
                print(f"  ⚠️  Push failed for {rp}: {e}")

    # Update manifest
    manifest_data["items_approved"] = approved_count
    manifest_data["status"] = "completed"
    (ITERATIONS_DIR / iteration_id / "manifest.json").write_text(
        json.dumps(manifest_data, indent=2)
    )

    for i, cat_iter in enumerate(catalog["iterations"]):
        if cat_iter["version"] == iteration_id:
            catalog["iterations"][i]["status"] = "completed"
            catalog["iterations"][i]["items_approved"] = approved_count

    (ITERATIONS_DIR / "catalog.json").write_text(json.dumps(catalog, indent=2))

    print(f"\n✅ Approved and executed {approved_count} items")
    return 0


def create_branch_for_change(repo: Repository, change_desc: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", change_desc.lower())[:50]
    branch_name = f"auto-evolve/{sanitized}"
    git_create_branch(repo, branch_name)
    return branch_name


def create_pr(
    repo: Repository,
    branch_name: str,
    description: str,
    changes: list[ChangeItem],
) -> str:
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
        print(f"   Auto-monitor: {r.auto_monitor}")
        if r.risk_override:
            print(f"   Risk override: {r.risk_override}")
        print()

    return 0


def cmd_rollback(args) -> int:
    version = args.to
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
    print(f"   Reason: {reason}")

    items = iter_data.get("items_pending_approval", [])
    repos_affected: dict[str, list] = {}
    for item in items:
        rp = item.get("repo_path", "")
        repos_affected.setdefault(rp, []).append(item)

    reverted = 0
    for repo_path, repo_items in repos_affected.items():
        repo = Repository(path=repo_path, type="skill")
        if not repo.resolve_path().exists():
            print(f"  ⚠️  Repo not found: {repo_path}")
            continue

        try:
            commits = git_log(repo, limit=len(repo_items) + 1)
            for commit in commits[: len(repo_items)]:
                try:
                    git_revert(repo, commit["hash"])
                    print(f"  ✅ Reverted: {commit['message'][:60]}")
                    reverted += 1
                except Exception as e:
                    print(f"  ⚠️  Could not revert {commit['hash']}: {e}")
        except Exception as e:
            print(f"  ❌ Git error for {repo_path}: {e}")

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
    return 0


def cmd_schedule(args) -> int:
    """Output OpenClaw cron creation commands (no direct cron management)."""
    if args.remove:
        print("# Remove auto-evolve cron job:")
        print("# Run this command to remove the cron:")
        print("openclaw cron remove auto-evolve-scan")
        print()
        print("Or manually delete the cron in your OpenClaw config.")
        return 0

    if args.show:
        print("# Auto-Evolve Schedule Configuration")
        print("#")
        print("# To set up scheduled scanning, run one of the commands below")
        print("# based on your desired frequency.")
        print()
        config = load_config()
        interval = config.get("schedule_interval_hours", 168)
        print(f"# Current interval: every {interval} hour(s)")
        print()
        print("# To change interval, run:")
        print(f"#   auto-evolve.py schedule --every {interval}")
        print()
        print("# Setup commands:")
        print(f"#   openclaw cron add --name auto-evolve-scan \\")
        print(f"#     --command 'python3 {SKILL_DIR}/scripts/auto-evolve.py scan' \\")
        print(f"#     --interval {interval}h")
        return 0

    if args.every:
        interval = args.every
        if interval < 1:
            print("❌ Interval must be at least 1 hour.")
            return 1

        config = load_config()
        config["schedule_interval_hours"] = interval
        save_config(config)

        print(f"✅ Schedule interval set to {interval} hour(s)")
        print()
        print("To activate, create an OpenClaw cron job:")
        print(f"  openclaw cron add --name auto-evolve-scan \\")
        print(f"    --command 'python3 {SKILL_DIR}/scripts/auto-evolve.py scan' \\")
        print(f"    --interval {interval}h")
        print()
        print(f"# Or use --cron flag for cron expression:")
        print(f"#   openclaw cron add --name auto-evolve-scan \\")
        print(f"#     --command 'python3 {SKILL_DIR}/scripts/auto-evolve.py scan' \\")
        print(f"#     --cron '0 */{interval} * * *'")
        return 0

    # No subcommand: show help
    print("auto-evolve.py schedule --every HOURS   Set scan interval")
    print("auto-evolve.py schedule --show           Show setup instructions")
    print("auto-evolve.py schedule --remove         Show removal instructions")
    return 0


def cmd_set_mode(args) -> int:
    """Set operation mode (semi-auto or full-auto)."""
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
    """Set full-auto execution rules."""
    config = load_config()
    rules = config.get("full_auto_rules", {})

    rules["execute_low_risk"] = args.low if args.low is not None else rules.get("execute_low_risk", True)
    rules["execute_medium_risk"] = args.medium if args.medium is not None else rules.get("execute_medium_risk", False)
    rules["execute_high_risk"] = args.high if args.high is not None else rules.get("execute_high_risk", False)

    config["full_auto_rules"] = rules
    save_config(config)

    print("✅ Full-auto rules updated:")
    print(f"   execute_low_risk:    {rules['execute_low_risk']}")
    print(f"   execute_medium_risk: {rules['execute_medium_risk']}")
    print(f"   execute_high_risk:   {rules['execute_high_risk']}")
    return 0


def cmd_learnings(args) -> int:
    """Show learning history."""
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
        print(f"\n{status_icon} {iteration['version']}{alert_flag}")
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
# CLI Entry Point
# ===========================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-Evolve v2.1 — Automated skill iteration manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    scan_p = subparsers.add_parser("scan", help="Scan and evolve skills")
    scan_p.add_argument("--dry-run", action="store_true", help="Preview only, no commits")

    # confirm (semi-auto)
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

    # schedule
    schedule_p = subparsers.add_parser("schedule", help="Schedule management (cron setup)")
    schedule_p.add_argument("--every", type=int, help="Set scan interval in hours")
    schedule_p.add_argument("--show", action="store_true", help="Show schedule setup instructions")
    schedule_p.add_argument("--remove", action="store_true", help="Show cron removal instructions")

    # set-mode
    set_mode_p = subparsers.add_parser("set-mode", help="Set operation mode")
    set_mode_p.add_argument("mode", type=str, choices=["semi-auto", "full-auto"], help="Mode")

    # set-rules
    set_rules_p = subparsers.add_parser("set-rules", help="Set full-auto execution rules")
    set_rules_p.add_argument("--low", type=lambda x: x.lower() == "true",
                            help="Execute low-risk (true/false)")
    set_rules_p.add_argument("--medium", type=lambda x: x.lower() == "true",
                             help="Execute medium-risk (true/false)")
    set_rules_p.add_argument("--high", type=lambda x: x.lower() == "true",
                             help="Execute high-risk (true/false)")

    # learnings
    learnings_p = subparsers.add_parser("learnings", help="Show learning history")
    learnings_p.add_argument("--type", type=str, choices=["rejections", "approvals"],
                             help="Filter by type")
    learnings_p.add_argument("--limit", type=int, default=20, help="Limit entries")

    # log
    log_p = subparsers.add_parser("log", help="Show iteration log")
    log_p.add_argument("--limit", type=int, default=10, help="Limit entries")

    args = parser.parse_args()

    commands: dict[str, callable] = {
        "scan": cmd_scan,
        "confirm": cmd_confirm,
        "reject": cmd_reject,
        "approve": cmd_approve,
        "repo-add": cmd_repo_add,
        "repo-list": cmd_repo_list,
        "rollback": cmd_rollback,
        "schedule": cmd_schedule,
        "set-mode": cmd_set_mode,
        "set-rules": cmd_set_rules,
        "learnings": cmd_learnings,
        "log": cmd_log,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

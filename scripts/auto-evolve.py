#!/usr/bin/env python3
"""
Auto-Evolve v2 — Automated skill iteration manager.

Features:
- Multi-type repositories (skill/norms/project/closed)
- Branch + PR flow for high-risk changes
- Proactive optimization discovery
- File-based approval workflow
- Full git rollback support

Usage:
    auto-evolve.py scan [--dry-run]
    auto-evolve.py approve [--all | ID...]
    auto-evolve.py repo-add <path> --type TYPE [--monitor]
    auto-evolve.py repo-list
    auto-evolve.py rollback --to VERSION
"""

from __future__ import annotations

import argparse
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
ITERATIONS_DIR = HOME / ".openclaw" / "workspace" / "skills" / "auto-evolve" / ".iterations"

REPO_TYPES = ("skill", "norms", "project", "closed")
RISK_LEVELS = ("low", "medium", "high")


# ===========================================================
# Data Models
# ===========================================================

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ChangeCategory(Enum):
    AUTO_EXEC = "auto_exec"       # low risk, executed immediately
    PENDING_APPROVAL = "pending_approval"  # medium/high risk, needs approval
    OPTIMIZATION = "optimization"  # proactive improvement found


@dataclass
class Repository:
    path: str
    type: str  # skill, norms, project, closed
    visibility: str = "public"  # public, closed
    auto_monitor: bool = True
    risk_override: Optional[str] = None  # force a risk level

    def resolve_path(self) -> Path:
        return Path(self.path).expanduser().resolve()

    def get_default_risk(self, change_type: str, file_path: str) -> RiskLevel:
        """Determine default risk based on repo type and change characteristics."""
        if self.risk_override:
            return RiskLevel(self.risk_override)

        file_lower = file_path.lower()

        # closed repo: code changes default to medium
        if self.visibility == "closed":
            if change_type in ("modified", "added"):
                if any(ext in file_lower for ext in (".py", ".js", ".ts", ".go", ".rs")):
                    return RiskLevel.MEDIUM
            if change_type == "removed":
                return RiskLevel.MEDIUM

        # norms repo: doc changes default to low
        if self.type == "norms":
            if any(ext in file_lower for ext in (".md", ".txt", ".yaml", ".yml", ".json")):
                return RiskLevel.LOW

        # project repo: test changes default to medium
        if self.type == "project":
            if "test" in file_lower or "_test." in file_lower:
                return RiskLevel.MEDIUM

        return RiskLevel.MEDIUM  # safe default


@dataclass
class ChangeItem:
    id: int
    description: str
    file_path: str
    change_type: str  # added, modified, removed
    risk: RiskLevel
    category: ChangeCategory
    repo_path: str = ""
    repo_type: str = ""
    optimization_type: Optional[str] = None  # todo, duplicate_code, long_function, etc.
    commit_hash: Optional[str] = None
    pr_url: Optional[str] = None


@dataclass
class OptimizationFinding:
    type: str  # todo, duplicate_code, outdated_doc, long_function, missing_test, outdated_dep
    file_path: str
    line: int
    description: str
    suggestion: str
    risk: RiskLevel


@dataclass
class IterationManifest:
    version: str
    date: str
    status: str  # dry-run, pending-approval, completed, rolled-back
    risk_level: str
    items_auto: int = 0
    items_approved: int = 0
    items_rejected: int = 0
    items_optimization: int = 0
    duration_seconds: float = 0.0
    items_pending_approval: list = field(default_factory=list)
    rollback_of: Optional[str] = None
    rollback_reason: Optional[str] = None


# ===========================================================
# Config Management
# ===========================================================

def load_config() -> dict:
    """Load configuration from file."""
    if AUTO_EVOLVE_RC.exists():
        return json.loads(AUTO_EVOLVE_RC.read_text())
    return get_default_config()


def save_config(config: dict) -> None:
    """Save configuration to file."""
    AUTO_EVOLVE_RC.parent.mkdir(parents=True, exist_ok=True)
    AUTO_EVOLVE_RC.write_text(json.dumps(config, indent=2))


def get_default_config() -> dict:
    """Return default configuration."""
    return {
        "schedule_interval_hours": 168,
        "auto_execute_risk": ["low"],
        "notify_risk": ["medium", "high"],
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
    """Convert config dict to Repository objects."""
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
    """Convert Repository objects back to config dict, preserving other keys."""
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


# ===========================================================
# Git Operations
# ===========================================================

def git_run(repo: Repository, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the repository."""
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
    """Get list of changed files."""
    result = git_run(repo, "status", "--porcelain")
    if not result.stdout.strip():
        return []

    changes = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        # Format: XY filename, e.g. "M  README.md" or "?? newfile.py"
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
    """Get current branch name."""
    result = git_run(repo, "branch", "--show-current")
    return result.stdout.strip()


def git_commit(repo: Repository, message: str) -> str:
    """Stage all and commit. Returns short commit hash."""
    git_run(repo, "add", ".")
    result = git_run(repo, "commit", "-m", message)
    hash_result = git_run(repo, "rev-parse", "--short", "HEAD")
    return hash_result.stdout.strip()


def git_push(repo: Repository, remote: str = "origin", branch: Optional[str] = None) -> None:
    """Push to remote."""
    branch = branch or git_current_branch(repo)
    git_run(repo, "push", "-u", remote, branch)


def git_create_branch(repo: Repository, branch_name: str) -> None:
    """Create and switch to a new branch."""
    git_run(repo, "checkout", "-b", branch_name)


def git_checkout(repo: Repository, ref: str) -> None:
    """Checkout a branch or commit."""
    git_run(repo, "checkout", ref)


def git_revert(repo: Repository, ref: str) -> str:
    """Revert a specific commit and return the new commit hash."""
    git_run(repo, "revert", "--no-edit", ref)
    hash_result = git_run(repo, "rev-parse", "--short", "HEAD")
    return hash_result.stdout.strip()


def git_log(repo: Repository, limit: int = 50) -> list[dict]:
    """Get recent commit history."""
    result = git_run(repo, "log", f"--pretty=format:%H|%s|%ad", "--date=iso",
                     f"-n{limit}")
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
    """Get diff stat or diff against ref."""
    if ref:
        result = git_run(repo, "diff", "--stat", ref)
    else:
        result = git_run(repo, "diff", "--stat")
    return result.stdout


# ===========================================================
# Risk Classification
# ===========================================================

def classify_change(repo: Repository, change_type: str, file_path: str) -> RiskLevel:
    """Classify a change by risk level using repo configuration."""
    default_risk = repo.get_default_risk(change_type, file_path)

    file_lower = file_path.lower()

    # High risk patterns (override defaults)
    high_risk_patterns = [
        "remove", "delete", "deprecate", "break",
        "rename", "migrate", "architect", "security",
    ]
    if any(p in file_lower for p in high_risk_patterns):
        return RiskLevel.HIGH

    # Low risk patterns (override defaults)
    low_risk_patterns = [
        "readme", "skill.md", "changelog", ".gitignore",
        "license", "comments", "typo", "format", "lint",
        "refactor", "rename",  # refactors that don't break APIs
    ]
    if change_type == "removed":
        # Deletions are generally riskier
        if any(p in file_lower for p in ["__init__", "config", "core"]):
            return RiskLevel.HIGH
        return default_risk

    if any(p in file_lower for p in low_risk_patterns):
        return RiskLevel.LOW

    return default_risk


# ===========================================================
# Optimization Scanner
# ===========================================================

# Patterns for TODO/FIXME/XXX detection
ANNOTATION_PATTERN = re.compile(
    r"(\b(TODO|FIXME|XXX|HACK|NOTE)\b.*?)$",
    re.IGNORECASE | re.MULTILINE,
)

# Patterns for long functions (>100 lines of code in a single function)
LONG_FUNCTION_PATTERN = re.compile(
    r"^(?:def |async def |class |async def .*?\(.*?\):[ \t]*\n)",
    re.MULTILINE,
)

# Patterns for missing test coverage
TEST_PATTERN = re.compile(r"^def test_", re.MULTILINE)

# Dependency file patterns
DEP_FILES = {
    "package.json": ("dependencies", "devDependencies"),
    "requirements.txt": (),  # all deps
    "pyproject.toml": ("dependencies", "dev-dependencies"),
    "go.mod": ("require",),
    "Cargo.toml": ("dependencies", "dev-dependencies"),
}

# Outdated dep patterns (simple check: pinned version vs semver range)
PINNED_VERSION = re.compile(r"==\d+\.\d+\.\d+")


def scan_optimizations(repo: Repository) -> list[OptimizationFinding]:
    """Scan repository for optimization opportunities."""
    findings = []
    repo_path = repo.resolve_path()

    # Scan Python files
    for py_file in repo_path.rglob("*.py"):
        rel_path = py_file.relative_to(repo_path)
        findings.extend(_scan_python_file(py_file, rel_path))

    # Scan other code files for annotations
    for code_file in repo_path.rglob("*"):
        if code_file.is_dir():
            continue
        if code_file.suffix.lower() not in (".py", ".js", ".ts", ".go", ".rs", ".md"):
            continue
        findings.extend(_scan_annotations(code_file, code_file.relative_to(repo_path)))

    # Check for tests directory vs module coverage
    findings.extend(_scan_test_coverage(repo_path, repo_path))

    # Check dependency files
    findings.extend(_scan_dependencies(repo_path))

    return findings


def _scan_python_file(py_file: Path, rel_path: Path) -> list[OptimizationFinding]:
    """Scan a Python file for optimization opportunities."""
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
    """Find TODO/FIXME/XXX annotations."""
    findings = []
    if content is None:
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return findings

    for i, line in enumerate(content.split("\n"), 1):
        match = ANNOTATION_PATTERN.search(line)
        if match:
            annotation = match.group(1)
            findings.append(OptimizationFinding(
                type="todo_fixme",
                file_path=str(rel_path),
                line=i,
                description=f"Unresolved annotation: {annotation.strip()}",
                suggestion="Address or document this TODO/FIXME/XXX",
                risk=RiskLevel.LOW,
            ))

    return findings


def _scan_duplicate_code(content: str, rel_path: Path) -> list[OptimizationFinding]:
    """Detect simple duplicate string patterns."""
    findings = []
    # Find repeated string literals (3+ occurrences of same string > 30 chars)
    strings = re.findall(r'"{3,3}[\s\S]*?"{3,3}|"{1,2}[^"]{30,200}"{1,2}', content)
    string_counts: dict[str, list[int]] = {}
    for s in strings:
        key = s[:50]  # Use first 50 chars as fingerprint
        string_counts.setdefault(key, []).append(len(s))

    for key, counts in string_counts.items():
        if len(counts) >= 3:
            findings.append(OptimizationFinding(
                type="duplicate_code",
                file_path=str(rel_path),
                line=0,
                description=f"Duplicate string pattern detected ({len(counts)} occurrences)",
                suggestion="Consider extracting repeated string into a constant or variable",
                risk=RiskLevel.LOW,
            ))
            break  # Only report once per file

    return findings


def _scan_long_functions(content: str, rel_path: Path) -> list[OptimizationFinding]:
    """Detect functions that are too long (>100 lines)."""
    findings = []
    lines = content.split("\n")
    in_function = False
    func_start = 0
    func_indent = 0

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Detect function definition
        func_match = re.match(r"(?:async )?def (\w+)\s*\(", stripped)
        if func_match:
            # Calculate previous function length
            if in_function:
                func_lines = i - func_start - 1
                if func_lines > 100:
                    findings.append(OptimizationFinding(
                        type="long_function",
                        file_path=str(rel_path),
                        line=func_start + 1,
                        description=f"Function '{prev_func_name}' is {func_lines} lines (>{100})",
                        suggestion="Consider splitting into smaller, focused functions",
                        risk=RiskLevel.MEDIUM,
                    ))
            in_function = True
            func_start = i
            func_indent = indent
            prev_func_name = func_match.group(1)
        elif in_function:
            # Check if we've exited the function (dedent to same or less)
            if stripped and indent <= func_indent:
                func_lines = i - func_start - 1
                if func_lines > 100:
                    findings.append(OptimizationFinding(
                        type="long_function",
                        file_path=str(rel_path),
                        line=func_start + 1,
                        description=f"Function '{prev_func_name}' is {func_lines} lines (>{100})",
                        suggestion="Consider splitting into smaller, focused functions",
                        risk=RiskLevel.MEDIUM,
                    ))
                in_function = False

    return findings


def _scan_test_coverage(repo_path: Path, scan_root: Path) -> list[OptimizationFinding]:
    """Check if code modules lack test coverage."""
    findings = []
    tests_dir = scan_root / "tests"
    if not tests_dir.exists():
        return findings

    # Get all Python modules in the main package
    main_modules: set[Path] = set()
    for py_file in scan_root.rglob("*.py"):
        rel = py_file.relative_to(scan_root)
        if rel.parts[0] in ("tests", ".git", ".iterations", "__pycache__"):
            continue
        if rel.name == "__init__.py" or rel.name.startswith("_"):
            continue
        main_modules.add(rel.parent / rel.stem)

    # Get all test files
    test_modules: set[Path] = set()
    if tests_dir.exists():
        for test_file in tests_dir.rglob("test_*.py"):
            rel = test_file.relative_to(tests_dir)
            test_modules.add(rel.parent / rel.stem)

    # Report modules without tests (only top-level for brevity)
    untested = []
    for mod in sorted(main_modules):
        mod_parts = mod.parts
        if len(mod_parts) <= 2:  # Only check top 2 levels
            test_path = tests_dir / "test_" + mod.name + ".py"
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
    """Check for potentially outdated dependencies."""
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
                        suggestion="Consider using semver range (e.g., >=1.0.0,<2.0.0)",
                        risk=RiskLevel.LOW,
                    ))
        except (UnicodeDecodeError, OSError):
            pass

    return findings


# ===========================================================
# Proactive Optimization Scanner
# ===========================================================

def scan_for_optimizations(repo: Repository) -> list[OptimizationFinding]:
    """Alias for scan_optimizations for clarity."""
    return scan_optimizations(repo)


# ===========================================================
# Iteration Management
# ===========================================================

def generate_iteration_id() -> str:
    """Generate a unique iteration ID."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def ensure_iterations_dir() -> Path:
    """Ensure iterations directory exists."""
    ITERATIONS_DIR.mkdir(parents=True, exist_ok=True)
    return ITERATIONS_DIR


def load_iteration(version: str) -> dict:
    """Load iteration manifest by version."""
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
) -> None:
    """Save all iteration files."""
    iter_dir = ensure_iterations_dir() / iteration_id
    iter_dir.mkdir(parents=True, exist_ok=True)

    manifest_dict = asdict(manifest)
    # Convert RiskLevel enums to strings for JSON
    manifest_dict["items_pending_approval"] = pending_items

    (iter_dir / "manifest.json").write_text(json.dumps(manifest_dict, indent=2))
    (iter_dir / "plan.md").write_text("\n".join(plan_lines))
    (iter_dir / "pending-review.json").write_text(json.dumps(pending_items, indent=2))
    (iter_dir / "report.md").write_text("\n".join(report_lines))


def update_catalog(manifest: IterationManifest) -> None:
    """Add or update iteration in the catalog."""
    catalog_file = ITERATIONS_DIR / "catalog.json"
    if catalog_file.exists():
        catalog = json.loads(catalog_file.read_text())
    else:
        catalog = {"iterations": []}

    # Remove existing entry if updating
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
    })

    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    catalog_file.write_text(json.dumps(catalog, indent=2))


def load_catalog() -> dict:
    """Load the iteration catalog."""
    catalog_file = ITERATIONS_DIR / "catalog.json"
    if catalog_file.exists():
        return json.loads(catalog_file.read_text())
    return {"iterations": []}


# ===========================================================
# Branch & PR Management
# ===========================================================

def create_branch_for_change(repo: Repository, change_desc: str) -> str:
    """Create a branch for a high-risk change."""
    # Sanitize description for branch name
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
    """Create a GitHub PR using gh CLI."""
    # Get remote URL to determine repo
    result = git_run(repo, "remote", "get-url", "origin", check=False)
    remote_url = result.stdout.strip()

    # Extract owner/repo from URL
    match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", remote_url)
    if not match:
        return f"Branch created: {branch_name} (PR creation requires gh CLI and GitHub remote)"

    repo_slug = match.group(1)

    # Build PR body
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
        f"```",
        f"auto-evolve.py approve",
        f"```",
        "Or approve specific items:",
        f"```",
        f"auto-evolve.py approve 1,2,3",
        f"```",
    ])

    pr_body = "\n".join(pr_body_lines)

    # Create PR using gh
    title = f"[auto-evolve] {description}"
    result = subprocess.run(
        [
            "gh", "pr", "create",
            "--repo", repo_slug,
            "--title", title,
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


# ===========================================================
# Quality Gates
# ===========================================================

def check_syntax(file_path: str) -> bool:
    """Check Python file compiles."""
    result = subprocess.run(
        ["python3", "-m", "py_compile", file_path],
        capture_output=True,
    )
    return result.returncode == 0


def run_quality_gates(repo: Repository) -> dict:
    """Run quality gates on a repository."""
    results: dict = {
        "syntax_ok": True,
        "syntax_errors": [],
        "passed": True,
    }

    for py_file in repo.resolve_path().rglob("*.py"):
        if not check_syntax(str(py_file)):
            results["syntax_ok"] = False
            results["syntax_errors"].append(str(py_file))
            results["passed"] = False

    return results


# ===========================================================
# Main Scan Logic
# ===========================================================

def run_scan(
    repo: Repository,
    dry_run: bool = False,
) -> tuple[list[ChangeItem], list[OptimizationFinding], list[str]]:
    """
    Run a full scan on a repository.
    Returns: (changes, optimizations, plan_lines)
    """
    changes = []
    opts = []
    plan_lines = []
    change_id = 1

    # 1. Scan for git changes
    git_changes = git_status(repo)
    for gc in git_changes:
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

    # 2. Scan for proactive optimizations
    opts = scan_optimizations(repo)
    for o in opts:
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
# Commands
# ===========================================================

def cmd_scan(args) -> int:
    """Run scan and optionally execute."""
    config = load_config()
    dry_run = args.dry_run

    print("🔍 Auto-Evolve v2 Scanner")
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
        changes, opts, _ = run_scan(repo, dry_run=dry_run)
        all_changes.extend(changes)
        all_opts.extend(opts)

    duration = time.time() - start_time

    # Categorize
    low_risk = [c for c in all_changes if c.risk == RiskLevel.LOW and c.category == ChangeCategory.AUTO_EXEC]
    pending = [c for c in all_changes if c.category in (ChangeCategory.PENDING_APPROVAL, ChangeCategory.OPTIMIZATION)]
    auto_exec = [c for c in all_changes if c.category == ChangeCategory.AUTO_EXEC and c.risk == RiskLevel.LOW]

    print(f"\n📊 Scan Results:")
    print(f"  Changes detected: {len(all_changes) - len(all_opts)}")
    print(f"  Optimizations found: {len(all_opts)}")
    print(f"  Low risk (auto):    {len(auto_exec)}")
    print(f"  Pending approval:   {len(pending)}")

    plan_lines = [
        f"# Iteration Plan — {iteration_id}",
        "",
        f"**Date:** {datetime.now(timezone.utc).isoformat()}",
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
        f"**Status:** {'dry-run' if dry_run else 'pending-approval'}",
        "",
        "## Summary",
        "",
        f"- Changes detected: {len(all_changes) - len(all_opts)}",
        f"- Optimizations found: {len(all_opts)}",
        f"- Auto-executed: {len(auto_exec) if not dry_run else 0}",
        f"- Pending approval: {len(pending)}",
        "",
    ]

    # Auto-execute low-risk changes
    auto_executed: list[ChangeItem] = []
    if auto_exec and not dry_run:
        print(f"\n🟢 Auto-executing {len(auto_exec)} low-risk changes...")
        for change in auto_exec:
            try:
                commit_msg = f"auto: {change.description}"
                commit_hash = git_commit(
                    Repository(path=change.repo_path, type=change.repo_type),
                    commit_msg,
                )
                change.commit_hash = commit_hash
                auto_executed.append(change)
                print(f"  ✅ {change.file_path} ({commit_hash})")
            except Exception as e:
                print(f"  ❌ {change.file_path}: {e}")

        # Push
        if auto_executed:
            try:
                git_push(Repository(path=auto_executed[0].repo_path, type=auto_executed[0].repo_type))
                print(f"  📤 Pushed to remote")
            except Exception as e:
                print(f"  ⚠️  Push failed: {e}")

    # Process pending items
    pending_items = []
    if pending:
        print(f"\n📋 Pending Approval ({len(pending)} items):")
        for i, c in enumerate(pending, 1):
            risk_icon = "🟡" if c.risk == RiskLevel.MEDIUM else "🔴"
            opt_badge = " [opt]" if c.category == ChangeCategory.OPTIMIZATION else ""
            print(f"  [{i}] {risk_icon} {c.risk.value.upper()} {c.description}{opt_badge}")

            pending_items.append({
                "id": i,
                "description": c.description,
                "file_path": c.file_path,
                "risk": c.risk.value,
                "category": c.category.value,
                "repo_path": c.repo_path,
                "optimization_type": c.optimization_type,
            })

        plan_lines.extend([
            f"## Pending Approval ({len(pending)} items)",
            "",
        ])
        for i, c in enumerate(pending, 1):
            plan_lines.append(f"- [{i}] **{c.risk.value.upper()}** {c.description}")

    # Build manifest
    manifest = IterationManifest(
        version=iteration_id,
        date=datetime.now(timezone.utc).isoformat(),
        status="dry-run" if dry_run else "pending-approval",
        risk_level="mixed",
        items_auto=len(auto_executed),
        items_approved=0,
        items_rejected=0,
        items_optimization=len(all_opts),
        duration_seconds=round(duration, 1),
        items_pending_approval=pending_items,
    )

    # Save iteration files
    save_iteration(iteration_id, manifest, plan_lines, pending_items, report_lines)
    update_catalog(manifest)

    print(f"\n📁 Iteration {iteration_id} saved to .iterations/{iteration_id}/")
    print(f"   Run `auto-evolve.py approve` to approve pending items")

    if dry_run:
        print("\n⚠️  Dry-run mode — no changes committed")

    return 0


def cmd_approve(args) -> int:
    """Approve and execute pending changes."""
    config = load_config()
    iteration_id = args.iteration_id
    approve_all = args.all

    # Find iteration to approve
    catalog = load_catalog()
    if not catalog["iterations"]:
        print("No iterations found.")
        return 1

    if iteration_id:
        target_iter = next((i for i in catalog["iterations"] if i["version"] == iteration_id), None)
        if not target_iter:
            print(f"Iteration {iteration_id} not found.")
            return 1
    else:
        # Find most recent pending-approval iteration
        target_iter = next(
            (i for i in catalog["iterations"] if i["status"] == "pending-approval"),
            None,
        )
        if not target_iter:
            print("No pending-approval iteration found.")
            return 1

    iteration_id = target_iter["version"]

    # Load pending items
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
        # Parse IDs from args
        ids_str = getattr(args, "ids", None)
        if ids_str:
            try:
                approved_ids = [int(x.strip()) for x in ids_str.split(",") if x.strip()]
            except ValueError:
                print("Invalid IDs. Use: approve 1,2,3")
                return 1
        else:
            print(f"Iteration: {iteration_id}")
            print(f"Pending items ({len(pending_items)}):")
            for p in pending_items:
                print(f"  [{p['id']}] {p['risk'].upper()} {p['description']}")
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

        # High-risk changes need branch + PR flow
        if p["risk"] == "high":
            print(f"\n🔴 High-risk: {p['description']}")
            print(f"  Creating branch and PR...")
            branch = create_branch_for_change(repo, p["description"][:50])
            try:
                commit_msg = f"auto-evolve: {p['description']}"
                commit_hash = git_commit(repo, commit_msg)
                pr_url = create_pr(repo, branch, p["description"], [ChangeItem(
                    id=p["id"],
                    description=p["description"],
                    file_path=p["file_path"],
                    change_type="approved",
                    risk=RiskLevel.HIGH,
                    category=ChangeCategory.PENDING_APPROVAL,
                    repo_path=repo.path,
                )])
                print(f"  ✅ Branch: {branch}")
                print(f"  ✅ Commit: {commit_hash}")
                print(f"  🔗 {pr_url}")
            except Exception as e:
                print(f"  ❌ Failed: {e}")
            approved_count += 1
        else:
            # Medium/low: direct commit
            try:
                commit_msg = f"auto-evolve: {p['description']}"
                commit_hash = git_commit(repo, commit_msg)
                print(f"  ✅ [{p['id']}] {p['description']} ({commit_hash})")
                approved_count += 1
            except Exception as e:
                print(f"  ❌ [{p['id']}] {p['description']}: {e}")

    # Push all approved
    if approved_count > 0:
        repos_affected: set[str] = set(p["repo_path"] for p in pending_items if p["id"] in approved_ids)
        for repo_path in repos_affected:
            repo = Repository(path=repo_path, type="skill")
            try:
                git_push(repo)
            except Exception as e:
                print(f"  ⚠️  Push failed for {repo_path}: {e}")

    # Update manifest
    manifest_data["items_approved"] = approved_count
    manifest_data["status"] = "completed"

    iter_dir = ITERATIONS_DIR / iteration_id
    (iter_dir / "manifest.json").write_text(json.dumps(manifest_data, indent=2))

    # Update catalog
    for i, cat_iter in enumerate(catalog["iterations"]):
        if cat_iter["version"] == iteration_id:
            catalog["iterations"][i]["status"] = "completed"
            catalog["iterations"][i]["items_approved"] = approved_count
    (ITERATIONS_DIR / "catalog.json").write_text(json.dumps(catalog, indent=2))

    print(f"\n✅ Approved and executed {approved_count} items")
    return 0


def cmd_repo_add(args) -> int:
    """Add a repository to monitoring."""
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

    # Check if already exists
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
    """List all configured repositories."""
    config = load_config()
    repos = config_to_repos(config)

    if not repos:
        print("No repositories configured.")
        print(f"Run: auto-evolve.py repo-add <path> --type <type>")
        return 0

    print("📦 Configured Repositories:")
    print("=" * 50)
    for i, r in enumerate(repos, 1):
        exists = "✅" if r.resolve_path().exists() else "❌"
        mon = "🟢" if r.auto_monitor else "⏭️"
        print(f"{i}. {exists} {mon} {r.path}")
        print(f"   Type: {r.type} | Visibility: {r.visibility}")
        print(f"   Auto-monitor: {r.auto_monitor}")
        if r.risk_override:
            print(f"   Risk override: {r.risk_override}")
        print()

    return 0


def cmd_rollback(args) -> int:
    """Rollback to a previous iteration."""
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

    # Load the iteration to rollback
    iter_data = load_iteration(version)
    rollback_iter_id = generate_iteration_id()

    print(f"⚠️  Rolling back iteration {version}")
    print(f"   Reason: {reason}")

    # Group changes by repo
    items = iter_data.get("items_pending_approval", [])
    repos_affected: dict[str, list] = {}
    for item in items:
        rp = item.get("repo_path", "")
        repos_affected.setdefault(rp, []).append(item)

    # Also check manifest for items_auto (committed changes to revert)
    items_auto = iter_data.get("items_auto", 0)

    reverted = 0
    for repo_path, repo_items in repos_affected.items():
        repo = Repository(path=repo_path, type="skill")
        if not repo.resolve_path().exists():
            print(f"  ⚠️  Repo not found: {repo_path}")
            continue

        # Find commits to revert (last N commits by this iteration)
        try:
            commits = git_log(repo, limit=len(repo_items) + 1)
            if commits:
                for commit in commits[:len(repo_items)]:
                    try:
                        git_revert(repo, commit["hash"])
                        print(f"  ✅ Reverted: {commit['message']}")
                        reverted += 1
                    except Exception as e:
                        print(f"  ⚠️  Could not revert {commit['hash']}: {e}")
        except Exception as e:
            print(f"  ❌ Git error for {repo_path}: {e}")

    # Create rollback manifest
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


# ===========================================================
# CLI Entry Point
# ===========================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto-Evolve v2 — Automated skill iteration manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan and evolve skills")
    scan_parser.add_argument("--dry-run", action="store_true", help="Preview only, no commits")

    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve pending changes")
    approve_parser.add_argument("--all", action="store_true", help="Approve all pending items")
    approve_parser.add_argument("--ids", type=str, help="Comma-separated IDs (e.g. 1,2,3)")
    approve_parser.add_argument("ids", nargs="?", type=str, help="IDs to approve (positional)")
    approve_parser.add_argument("--iteration", dest="iteration_id", type=str, help="Iteration ID")

    # repo-add
    repo_add_parser = subparsers.add_parser("repo-add", help="Add a repository to monitor")
    repo_add_parser.add_argument("path", type=str, help="Repository path")
    repo_add_parser.add_argument("--type", type=str, choices=REPO_TYPES, help="Repository type")
    repo_add_parser.add_argument("--monitor", action="store_true", default=True, help="Enable auto-monitor")

    # repo-list
    subparsers.add_parser("repo-list", help="List configured repositories")

    # rollback
    rollback_parser = subparsers.add_parser("rollback", help="Rollback to a previous iteration")
    rollback_parser.add_argument("--to", required=True, dest="to", type=str, help="Target version")
    rollback_parser.add_argument("--reason", type=str, help="Rollback reason")

    # log (bonus command)
    log_parser = subparsers.add_parser("log", help="Show iteration log")
    log_parser.add_argument("--limit", type=int, default=10, help="Limit entries")

    args = parser.parse_args()

    commands = {
        "scan": cmd_scan,
        "approve": cmd_approve,
        "repo-add": cmd_repo_add,
        "repo-list": cmd_repo_list,
        "rollback": cmd_rollback,
        "log": cmd_log,
    }

    if args.command == "log":
        return cmd_log(args)
    if args.command == "approve":
        args.ids = args.ids  # positional already captured
        return cmd_approve(args)

    return commands[args.command](args)


def cmd_log(args) -> int:
    """Show iteration log."""
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
            "dry-run": "⚡",
            "rolled-back": "🔄",
        }.get(iteration["status"], "❓")

        print(f"\n{status_icon} {iteration['version']}")
        print(f"   Date: {iteration['date']}")
        print(f"   Status: {iteration['status']}")
        print(f"   Risk: {iteration.get('risk_level', 'unknown')}")
        if iteration.get("items_auto"):
            print(f"   Auto: {iteration['items_auto']}")
        if iteration.get("items_approved"):
            print(f"   Approved: {iteration['items_approved']}")
        if iteration.get("rollback_of"):
            print(f"   Rolled back: {iteration['rollback_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

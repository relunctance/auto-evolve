"""
Security Perspective Scanner — Example Implementation.

This scanner demonstrates how to implement a perspective scanner
according to the scanner-contract.md interface.

Usage:
    from security_scanner import SecurityScanner
    scanner = SecurityScanner()
    result = scanner.scan(context)
"""

import json
import time
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Import the base interfaces
# In practice: from project_standard.scanner_contract import ...
from llm_evaluator import LLMEvaluator, EvaluationContext, EvaluationResult, LLMConfig


# ─── Check Definitions ────────────────────────────────────────────────────────

SECURITY_CHECKS = {
    # Dimension: injection
    "injection_sql": {
        "id": "SEC_INJECTION_001",
        "check_id": "SEC_INJECTION_001",
        "description": "SQL queries use parameterized queries",
        "severity": "critical",
        "auto_actionable": True,
        "fix_action": "parameterize_query",
        "patterns": [
            r'f["\'].*SELECT.*\{.*\}',
            r'f["\'].*INSERT.*\{.*\}',
            r'f["\'].*UPDATE.*\{.*\}',
            r'f["\'].*DELETE.*\{.*\}',
            r'\.format\(.*["\'].*SELECT',
            r'["\'] %. %s .*(SELECT|INSERT|UPDATE|DELETE)',
        ],
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": "Check if this SQL query uses string interpolation or f-strings instead of parameterized queries.",
    },
    "injection_command": {
        "id": "SEC_INJECTION_002",
        "check_id": "SEC_INJECTION_002",
        "description": "No shell command injection via os.system/subprocess with user input",
        "severity": "critical",
        "auto_actionable": True,
        "fix_action": "replace_shell_exec",
        "patterns": [
            r'os\.system\(.*\+',
            r'os\.popen\(.*\+',
            r'subprocess\..*shell=True',
            r'exec\(.*\+',
            r'eval\(.*\)',
        ],
        "file_types": [".py", ".js", ".sh"],
        "llm_prompt_template": "Check if this code uses os.system, subprocess with shell=True, or eval with untrusted input.",
    },
    # Dimension: secrets
    "secrets_hardcoded": {
        "id": "SEC_SECRETS_001",
        "check_id": "SEC_SECRETS_001",
        "description": "No hardcoded secrets, API keys, or passwords in source code",
        "severity": "high",
        "auto_actionable": True,
        "fix_action": "substitute_env_var",
        "patterns": [
            r'["\'][a-zA-Z_]*password["\']\s*[=:]\s*["\'][a-zA-Z0-9+/=]{8,}["\']',
            r'["\'][a-zA-Z_]*api[_-]?key["\']\s*[=:]\s*["\'][a-zA-Z0-9+/=]{16,}["\']',
            r'["\'][a-zA-Z_]*secret["\']\s*[=:]\s*["\'][a-zA-Z0-9+/=]{16,}["\']',
            r'Bearer\s+[a-zA-Z0-9+/=]{20,}',
            r'ghp_[a-zA-Z0-9]{36}',
            r'AKIA[0-9A-Z]{16}',
        ],
        "file_types": [".py", ".js", ".ts", ".java", ".go", ".yaml", ".yml", ".env*"],
        "llm_prompt_template": "Check if this code contains hardcoded passwords, API keys, or secrets.",
    },
    # Dimension: auth
    "auth_weak": {
        "id": "SEC_AUTH_001",
        "check_id": "SEC_AUTH_001",
        "description": "Authentication uses strong password hashing",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "use_password_hash",
        "patterns": [
            r'md5\s*\(',
            r'hashlib\.md5\(',
            r'sha1\s*\(',
            r'HashPassword\s*\(\s*["\'][a-zA-Z0-9]{32}["\']',
        ],
        "file_types": [".py", ".js", ".java"],
        "llm_prompt_template": "Check if passwords are hashed with MD5 or SHA1 (weak) instead of bcrypt/scrypt/argon2.",
    },
    # Dimension: xss
    "xss_reflected": {
        "id": "SEC_XSS_001",
        "check_id": "SEC_XSS_001",
        "description": "User input is escaped before rendering",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "escape_user_input",
        "patterns": [
            r'innerHTML\s*=\s*.*\+',
            r'dangerouslySetInnerHTML',
            r'render\s*=\s*.*request\.args\.get',
            r'response\.write\(.*request\.',
        ],
        "file_types": [".html", ".js", ".ts", ".jsx", ".tsx", ".py"],
        "llm_prompt_template": "Check if user input could be reflected in HTML without proper escaping.",
    },
    # Dimension: tls
    "tls_missing": {
        "id": "SEC_TLS_001",
        "check_id": "SEC_TLS_001",
        "description": "External connections use TLS",
        "severity": "high",
        "auto_actionable": True,
        "fix_action": "enforce_tls",
        "patterns": [
            r'http://(?!localhost|127\.0\.0\.1)',
            r'verify=False',
            r'ssl_verify=False',
            r'requests\.(get|post)\(.*verify\s*=\s*False',
        ],
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": "Check if this code makes HTTP requests without TLS verification.",
    },
}


# ─── Dimension Definitions ────────────────────────────────────────────────────

SECURITY_DIMENSIONS = [
    {
        "name": "injection",
        "weight": 0.25,
        "checks": ["SEC_INJECTION_001", "SEC_INJECTION_002"],
    },
    {
        "name": "secrets",
        "weight": 0.20,
        "checks": ["SEC_SECRETS_001"],
    },
    {
        "name": "auth",
        "weight": 0.20,
        "checks": ["SEC_AUTH_001"],
    },
    {
        "name": "xss",
        "weight": 0.15,
        "checks": ["SEC_XSS_001"],
    },
    {
        "name": "tls",
        "weight": 0.10,
        "checks": ["SEC_TLS_001"],
    },
    {
        "name": "dependency",
        "weight": 0.10,
        "checks": [],  # Uses CVE scanning, not regex
    },
]


# ─── Security Scanner ─────────────────────────────────────────────────────────

class SecurityScanner:
    """
    Security perspective scanner implementation.

    This scanner:
    1. Scans code files with regex patterns (fast pass)
    2. Uses LLM to evaluate ambiguous findings (deep pass)
    3. Aggregates results into a ScanResult
    """

    PERSPECTIVE_NAME = "security"
    PERSPECTIVE_VERSION = "1.0"
    SCANNER_VERSION = "1.0.0"

    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self.evaluator = LLMEvaluator(llm_config or LLMConfig.from_env())
        self.findings = []
        self.dimension_results = {}

    def scan(self, context) -> dict:
        """
        Execute the security scan.

        Args:
            context: ScanContext with repo_path, project_type, tech_stack, etc.

        Returns:
            ScanResult dict matching scoring-algorithm.md schema
        """
        start_time = time.time()
        repo_path = Path(context.repo_path)
        all_findings = []

        # 1. Static pattern scan (fast pass)
        pattern_findings = self._scan_patterns(repo_path)
        all_findings.extend(pattern_findings)

        # 2. LLM evaluation for ambiguous findings
        llm_findings = self._scan_with_llm(repo_path, context)
        all_findings.extend(llm_findings)

        # 3. CVE dependency check
        cve_findings = self._scan_dependencies(repo_path)
        all_findings.extend(cve_findings)

        # 4. Compute dimension scores
        dimension_scores = self._compute_dimension_scores(all_findings)

        # 5. Compute overall score
        overall_score = sum(d.score * d.weight for d in dimension_scores.values())
        overall_grade = self._score_to_grade(overall_score)

        duration_ms = int((time.time() - start_time) * 1000)

        # Build result
        result = {
            "perspective": self.PERSPECTIVE_NAME,
            "version": self.PERSPECTIVE_VERSION,
            "scan_timestamp": self._iso_now(),
            "duration_ms": duration_ms,
            "overall_score": overall_score,
            "grade": overall_grade,
            "dimensions": [
                {
                    "name": dim_name,
                    "score": score,
                    "weight": next(d["weight"] for d in SECURITY_DIMENSIONS if d["name"] == dim_name),
                    "checks": self._get_checks_for_dimension(dim_name, all_findings),
                }
                for dim_name, score in dimension_scores.items()
            ],
            "findings": [
                {
                    "id": f.id,
                    "perspective": self.PERSPECTIVE_NAME,
                    "dimension": f.dimension,
                    "check_id": f.check_id,
                    "description": f.description,
                    "severity": f.severity,
                    "impact_score": f.impact_score,
                    "evidence": f.evidence,
                    "suggested_fix": f.suggested_fix,
                    "fix_action": f.fix_action,
                    "auto_actionable": f.auto_actionable,
                    "confidence": f.confidence,
                }
                for f in all_findings
            ],
            "summary": {
                "total_checks": len(SECURITY_CHECKS),
                "passed": 0,  # Would need per-check logic
                "failed": len(all_findings),
                "warnings": 0,
                "na": 0,
            },
            "errors": [],
            "scanner_errors": None,
            "perspective_version": self.PERSPECTIVE_VERSION,
            "scanner_version": self.SCANNER_VERSION,
        }

        return result

    def _scan_patterns(self, repo_path: Path) -> list["SecurityFinding"]:
        """Fast regex pattern scan."""
        findings = []
        for check_key, check_def in SECURITY_CHECKS.items():
            for pattern in check_def["patterns"]:
                for file_type in check_def["file_types"]:
                    for file_path in repo_path.rglob(f"*{file_type}"):
                        if self._should_skip(file_path):
                            continue
                        try:
                            content = file_path.read_text(errors="ignore")
                            matches = list(re.finditer(pattern, content))
                            if matches:
                                for m in matches:
                                    findings.append(SecurityFinding(
                                        check_id=check_def["id"],
                                        dimension=self._get_dimension_for_check(check_def["id"]),
                                        description=check_def["description"],
                                        severity=check_def["severity"],
                                        file_path=str(file_path.relative_to(repo_path)),
                                        line=m.start(),
                                        matched_text=m.group(),
                                        fix_action=check_def.get("fix_action", ""),
                                        auto_actionable=check_def.get("auto_actionable", False),
                                        confidence=0.95,
                                        is_llm=False,
                                    ))
                        except Exception:
                            continue
        return findings

    def _scan_with_llm(self, repo_path: Path, context) -> list["SecurityFinding"]:
        """Use LLM to evaluate files that might have issues."""
        findings = []

        # Files to evaluate with LLM (from pattern scan, or all for critical checks)
        files_to_evaluate = {}

        for check_key, check_def in SECURITY_CHECKS.items():
            # Only use LLM for checks marked as needing deep evaluation
            if not check_def.get("use_llm", False):
                continue

            for file_type in check_def["file_types"]:
                for file_path in repo_path.rglob(f"*{file_type}"):
                    if self._should_skip(file_path):
                        continue
                    rel_path = str(file_path.relative_to(repo_path))
                    try:
                        content = file_path.read_text(errors="ignore", encoding="utf-8")
                        files_to_evaluate[rel_path] = content
                    except Exception:
                        continue

        # Evaluate each file with LLM
        for file_path, content in files_to_evaluate.items():
            eval_context = EvaluationContext(
                perspective=self.PERSPECTIVE_NAME,
                dimension="security",
                check_id="SEC_LLM_001",
                file_path=file_path,
                code_snippet=content[:2000],
                perspective_doc=self._get_perspective_doc(),
                project_type=getattr(context, "project_type", "generic"),
                tech_stack=getattr(context, "tech_stack", "python"),
                previous_decisions=getattr(context, "learnings", {}).get("decisions", []),
            )

            result = self.evaluator.evaluate(eval_context)

            if result.status in ("fail", "warning"):
                findings.append(SecurityFinding(
                    check_id="SEC_LLM_001",
                    dimension=result.dimension or "security",
                    description=result.description,
                    severity=result.severity,
                    file_path=file_path,
                    line=0,
                    matched_text="",
                    fix_action=result.fix_action,
                    auto_actionable=result.auto_actionable,
                    confidence=result.confidence,
                    is_llm=True,
                    reasoning=result.reasoning,
                ))

        return findings

    def _scan_dependencies(self, repo_path: Path) -> list["SecurityFinding"]:
        """Scan dependencies for known CVEs."""
        findings = []

        # package.json
        pkg_file = repo_path / "package.json"
        if pkg_file.exists():
            try:
                pkg = json.loads(pkg_file.read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                # In practice, would call npm audit or Snyk API here
                # For now, just return empty (CVE check is external)
            except Exception:
                pass

        # requirements.txt
        req_file = repo_path / "requirements.txt"
        if req_file.exists():
            try:
                # Would call safety check or PyUp API here
                pass
            except Exception:
                pass

        return findings

    def _compute_dimension_scores(self, findings: list["SecurityFinding"]) -> dict:
        """Compute score per dimension using weighted severity."""
        dim_totals = {}
        dim_counts = {}

        for dim in SECURITY_DIMENSIONS:
            dim_totals[dim["name"]] = 0.0
            dim_counts[dim["name"]] = 0

        for f in findings:
            severity_map = {"critical": 0.0, "high": 25.0, "medium": 50.0, "low": 75.0}
            score = severity_map.get(f.severity, 50.0)
            dim_totals[f.dimension] = dim_totals.get(f.dimension, 0) + score
            dim_counts[f.dimension] += 1

        # Convert to 0-100 scale
        scores = {}
        for dim in SECURITY_DIMENSIONS:
            dim_name = dim["name"]
            if dim_counts[dim_name] == 0:
                scores[dim_name] = 100.0  # All clear
            else:
                scores[dim_name] = max(0.0, 100.0 - dim_totals[dim_name])

        return scores

    def _score_to_grade(self, score: float) -> str:
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 60:
            return "acceptable"
        elif score >= 40:
            return "poor"
        else:
            return "critical"

    def _get_dimension_for_check(self, check_id: str) -> str:
        for dim in SECURITY_DIMENSIONS:
            if check_id in dim["checks"]:
                return dim["name"]
        return "general"

    def _get_checks_for_dimension(self, dim_name: str, findings: list["SecurityFinding"]) -> list[dict]:
        check_ids = next((d["checks"] for d in SECURITY_DIMENSIONS if d["name"] == dim_name), [])
        dim_findings = [f for f in findings if f.check_id in check_ids]
        return [
            {
                "id": f.check_id,
                "status": "fail",
                "severity": f.severity,
                "evidence": [f"{f.file_path}:{f.line}"],
            }
            for f in dim_findings
        ]

    def _should_skip(self, path: Path) -> bool:
        skip_dirs = {
            "node_modules", ".venv", "venv", "env", "dist", "build",
            ".git", "__pycache__", "coverage", ".pytest_cache",
            ".tox", ".tox", "vendor", "third_party",
        }
        return any(part in path.parts for part in skip_dirs)

    def _get_perspective_doc(self) -> str:
        """Return the perspective standard text for LLM context."""
        return """Security Perspective: Injection & XSS checks.
        SQL queries must use parameterized queries. Command execution must not use user input.
        Secrets must not be hardcoded. Auth must use strong hashing. XSS must escape user input."""

    def _iso_now(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def get_dimensions(self) -> list:
        """Return dimension definitions."""
        return SECURITY_DIMENSIONS


# ─── Finding Data Class ────────────────────────────────────────────────────────

@dataclass
class SecurityFinding:
    check_id: str
    dimension: str
    description: str
    severity: str  # critical/high/medium/low
    file_path: str
    line: int
    matched_text: str
    fix_action: str
    auto_actionable: bool
    confidence: float
    is_llm: bool = False
    reasoning: str = ""
    impact_score: float = 0.5

    @property
    def evidence(self) -> list[str]:
        ev = [f"File: {self.file_path}"]
        if self.line:
            ev.append(f"Line {self.line}")
        if self.matched_text:
            ev.append(f"Match: {self.matched_text[:100]}")
        if self.reasoning:
            ev.append(f"LLM: {self.reasoning[:200]}")
        return ev


# ─── Smoke Test ──────────────────────────────────────────────────────────────

def smoke_test():
    """Test the security scanner."""
    import os

    config = LLMConfig(
        model=os.environ.get("LLM_MODEL", "gpt-4"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )

    scanner = SecurityScanner(llm_config=config)

    # Mock context
    class MockContext:
        repo_path = "/tmp/test-repo"
        project_type = "backend"
        tech_stack = "python"
        learnings = {"decisions": []}

    # In practice, would run against a real repo
    print("SecurityScanner initialized. Ready to scan.")


if __name__ == "__main__":
    smoke_test()

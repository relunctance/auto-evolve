"""
Testing Perspective Scanner — auto-evolve

This scanner evaluates a repository's testing practices across 6 dimensions:
  - Coverage:     Code coverage quality
  - Unit:         Unit test quality & isolation
  - Integration:  API / DB / Auth end-to-end tests
  - Maintenance:  Test hygiene (no commented-out, no flakiness)
  - CI:           CI pipeline integration
  - Strategy:     Frontend E2E, API contracts, security negative tests

Usage:
    from testing_scanner import TestingScanner
    scanner = TestingScanner()
    result = scanner.scan(context)
"""

import json
import time
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from llm_evaluator import LLMEvaluator, EvaluationContext, EvaluationResult, LLMConfig


# ─── Check Definitions ────────────────────────────────────────────────────────

TESTING_CHECKS = {
    # ── Coverage ──────────────────────────────────────────────────────────────
    "cov_core": {
        "id": "TEST_COV_001",
        "check_id": "TEST_COV_001",
        "description": "Core logic coverage ≥ 80%",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "add_unit_tests",
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": (
            "Check if the core business logic functions in this file have adequate "
            "unit test coverage (≥80%). Look for: covered branches, edge case handling, "
            "and whether critical paths are tested."
        ),
        "dimension": "coverage",
    },
    "cov_critical_paths": {
        "id": "TEST_COV_002",
        "check_id": "TEST_COV_002",
        "description": "Critical paths have explicit tests",
        "severity": "critical",
        "auto_actionable": False,
        "fix_action": "add_critical_path_tests",
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": (
            "Identify critical code paths (e.g. payment, auth, data mutations) and "
            "check whether they have explicit test cases."
        ),
        "dimension": "coverage",
    },
    "cov_edge_cases": {
        "id": "TEST_COV_003",
        "check_id": "TEST_COV_003",
        "description": "Edge cases (null, empty, max) tested",
        "severity": "medium",
        "auto_actionable": False,
        "fix_action": "add_edge_case_tests",
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": (
            "Check if this code handles edge cases: null/nil values, empty collections, "
            "maximum boundary values, and if these are explicitly tested."
        ),
        "dimension": "coverage",
    },
    # ── Unit Tests ─────────────────────────────────────────────────────────────
    "unit_speed": {
        "id": "TEST_UNIT_001",
        "check_id": "TEST_UNIT_001",
        "description": "Unit tests run in < 100ms each",
        "severity": "low",
        "auto_actionable": True,
        "fix_action": "optimize_test_speed",
        "file_types": ["pytest.ini", "pyproject.toml", "jest.config.js",
                        "jest.config.ts", "vitest.config.ts"],
        "llm_prompt_template": (
            "Check if test execution time is configured or if there are obvious "
            "signs of slow tests (e.g. sleep calls, large timeouts, heavy fixtures)."
        ),
        "dimension": "unit",
    },
    "unit_mocked": {
        "id": "TEST_UNIT_002",
        "check_id": "TEST_UNIT_002",
        "description": "Dependencies mocked in unit tests",
        "severity": "medium",
        "auto_actionable": True,
        "fix_action": "mock_dependencies",
        "file_types": [".py", ".js", ".ts"],
        "llm_prompt_template": (
            "Check if unit tests mock external dependencies (databases, APIs, file system). "
            "Tests that hit real external services are not properly isolated unit tests."
        ),
        "dimension": "unit",
    },
    "unit_isolated": {
        "id": "TEST_UNIT_003",
        "check_id": "TEST_UNIT_003",
        "description": "Tests are isolated (no shared state)",
        "severity": "high",
        "auto_actionable": True,
        "fix_action": "isolate_tests",
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": (
            "Check if tests share mutable state (global variables, class-level state, "
            "shared databases). Tests must be fully isolated from each other."
        ),
        "dimension": "unit",
    },
    # ── Integration Tests ──────────────────────────────────────────────────────
    "integ_api": {
        "id": "TEST_INTEG_001",
        "check_id": "TEST_INTEG_001",
        "description": "API endpoints tested end-to-end",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "add_api_integration_tests",
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": (
            "Check if API endpoints have end-to-end integration tests that verify "
            "request/response handling, status codes, and payloads."
        ),
        "dimension": "integration",
    },
    "integ_db": {
        "id": "TEST_INTEG_002",
        "check_id": "TEST_INTEG_002",
        "description": "DB operations tested with transactions",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "add_db_transaction_tests",
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": (
            "Check if database operations are tested within transactions that "
            "rollback after each test, ensuring tests don't pollute the database."
        ),
        "dimension": "integration",
    },
    "integ_auth": {
        "id": "TEST_INTEG_003",
        "check_id": "TEST_INTEG_003",
        "description": "Auth flows tested end-to-end",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "add_auth_integration_tests",
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": (
            "Check if authentication and authorization flows (login, logout, token "
            "refresh, permission checks) are tested end-to-end."
        ),
        "dimension": "integration",
    },
    # ── Maintenance ─────────────────────────────────────────────────────────────
    "maint_commented": {
        "id": "TEST_MAINT_001",
        "check_id": "TEST_MAINT_001",
        "description": "No commented-out tests",
        "severity": "low",
        "auto_actionable": True,
        "fix_action": "remove_commented_tests",
        "patterns": [
            r"#\s*(def test_|class Test|test_\w+\(|it\s*\(.*\)|expect\(|assert\s)",
            r"#\s*skip",
            r"@pytest\.mark\.skip",
            r"//\s*(test|it)\(",
            r"/\*\s*(test|it)\(",
        ],
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "dimension": "maintenance",
    },
    "maint_flaky": {
        "id": "TEST_MAINT_002",
        "check_id": "TEST_MAINT_002",
        "description": "Flaky tests tracked and fixed",
        "severity": "medium",
        "auto_actionable": False,
        "fix_action": "fix_flaky_tests",
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": (
            "Check if there are any signs of flaky tests: tests marked as flaky, "
            "tests with random data, timeouts, or network dependencies that cause "
            "non-deterministic results."
        ),
        "dimension": "maintenance",
    },
    # ── CI ─────────────────────────────────────────────────────────────────────
    "ci_pipeline": {
        "id": "TEST_CI_001",
        "check_id": "TEST_CI_001",
        "description": "Tests run in CI pipeline",
        "severity": "critical",
        "auto_actionable": True,
        "fix_action": "add_ci_test_pipeline",
        "patterns": [
            r"pytest",
            r"npm test",
            r"yarn test",
            r"go test",
            r"gradle test",
            r"mvn test",
        ],
        "file_types": [".github/workflows/*.yml", "Jenkinsfile", ".gitlab-ci.yml",
                        "tox.ini", "Makefile", "package.json", "pyproject.toml"],
        "dimension": "ci",
    },
    "ci_coverage": {
        "id": "TEST_CI_002",
        "check_id": "TEST_CI_002",
        "description": "Coverage reported in CI",
        "severity": "high",
        "auto_actionable": True,
        "fix_action": "add_coverage_reporting",
        "patterns": [
            r"coverage",
            r"--cov",
            r"codecov",
            r"coveralls",
            r"jacoco",
        ],
        "file_types": [".github/workflows/*.yml", "Jenkinsfile", ".gitlab-ci.yml",
                        "tox.ini", "package.json", "pyproject.toml"],
        "dimension": "ci",
    },
    "ci_blocking": {
        "id": "TEST_CI_003",
        "check_id": "TEST_CI_003",
        "description": "PR blocked if tests fail",
        "severity": "high",
        "auto_actionable": True,
        "fix_action": "enforce_ci_gate",
        "patterns": [
            r"required:\s*true",
            r"fail-fast:\s*false",
            r"status:\s*pending",
        ],
        "file_types": [".github/workflows/*.yml", "Jenkinsfile", ".gitlab-ci.yml"],
        "dimension": "ci",
    },
    # ── Strategy ────────────────────────────────────────────────────────────────
    "strat_frontend_e2e": {
        "id": "TEST_STRAT_001",
        "check_id": "TEST_STRAT_001",
        "description": "Frontend E2E tests for critical flows",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "add_frontend_e2e_tests",
        "patterns": [
            r"playwright",
            r"cypress",
            r"selenium",
            r"@e2e",
            r"e2e/",
        ],
        "file_types": [".py", ".js", ".ts", ".jsx", ".tsx", "package.json",
                        "cypress.config.js", "playwright.config.ts"],
        "llm_prompt_template": (
            "Check if there are frontend end-to-end tests (Playwright, Cypress, Selenium) "
            "covering critical user flows (e.g. sign-up, checkout, login)."
        ),
        "dimension": "strategy",
    },
    "strat_api_contract": {
        "id": "TEST_STRAT_002",
        "check_id": "TEST_STRAT_002",
        "description": "Backend API contract tests",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "add_api_contract_tests",
        "patterns": [
            r"pact",
            r"rest-assured",
            r"supertest",
            r"openapi.*test",
            r"schema.*valid",
        ],
        "file_types": [".py", ".js", ".ts", ".java", ".go", "package.json",
                        "pyproject.toml"],
        "llm_prompt_template": (
            "Check if API contracts (request/response schemas) are tested using "
            "contract testing frameworks like Pact, REST Assured, or Supertest."
        ),
        "dimension": "strategy",
    },
    "strat_security_negative": {
        "id": "TEST_STRAT_003",
        "check_id": "TEST_STRAT_003",
        "description": "Security paths have explicit negative tests",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "add_security_negative_tests",
        "file_types": [".py", ".js", ".ts", ".java", ".go"],
        "llm_prompt_template": (
            "Check if security-sensitive paths (auth, payment, file upload, admin) "
            "have negative test cases that verify rejection of invalid/malicious input."
        ),
        "dimension": "strategy",
    },
}


# ─── Dimension Definitions ────────────────────────────────────────────────────

TESTING_DIMENSIONS = [
    {"name": "coverage",   "weight": 0.20, "checks": ["TEST_COV_001", "TEST_COV_002", "TEST_COV_003"]},
    {"name": "unit",       "weight": 0.15, "checks": ["TEST_UNIT_001", "TEST_UNIT_002", "TEST_UNIT_003"]},
    {"name": "integration","weight": 0.20, "checks": ["TEST_INTEG_001", "TEST_INTEG_002", "TEST_INTEG_003"]},
    {"name": "maintenance","weight": 0.10, "checks": ["TEST_MAINT_001", "TEST_MAINT_002"]},
    {"name": "ci",         "weight": 0.20, "checks": ["TEST_CI_001", "TEST_CI_002", "TEST_CI_003"]},
    {"name": "strategy",   "weight": 0.15, "checks": ["TEST_STRAT_001", "TEST_STRAT_002", "TEST_STRAT_003"]},
]


# ─── Finding Data Class ────────────────────────────────────────────────────────

@dataclass
class TestingFinding:
    check_id: str
    dimension: str
    description: str
    severity: str
    file_path: str
    line: int
    matched_text: str
    fix_action: str
    auto_actionable: bool
    confidence: float
    is_llm: bool = False
    reasoning: str = ""

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


# ─── Testing Scanner ──────────────────────────────────────────────────────────

class TestingScanner:
    """
    Testing perspective scanner implementation.

    This scanner:
    1. Scans code/test files with regex patterns (fast pass)
    2. Uses LLM to evaluate nuanced testing quality checks (deep pass)
    3. Aggregates results into a ScanResult dict
    """

    PERSPECTIVE_NAME = "testing"
    PERSPECTIVE_VERSION = "1.0"
    SCANNER_VERSION = "1.0.0"

    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self.evaluator = LLMEvaluator(llm_config or LLMConfig.from_env())
        self.findings: list[TestingFinding] = []
        self.dimension_results: dict = {}

    def scan(self, context) -> dict:
        """
        Execute the testing perspective scan.

        Args:
            context: ScanContext with repo_path, project_type, tech_stack, etc.

        Returns:
            ScanResult dict matching scoring-algorithm.md schema
        """
        start_time = time.time()
        repo_path = Path(context.repo_path)
        all_findings: list[TestingFinding] = []

        # 1. Static pattern scan (fast pass)
        pattern_findings = self._scan_patterns(repo_path)
        all_findings.extend(pattern_findings)

        # 2. LLM evaluation for nuanced checks (deep pass)
        llm_findings = self._scan_with_llm(repo_path, context)
        all_findings.extend(llm_findings)

        # 3. Coverage file scan (coverage reports, pytest.ini, etc.)
        coverage_findings = self._scan_coverage_config(repo_path)
        all_findings.extend(coverage_findings)

        # 4. CI config scan
        ci_findings = self._scan_ci_config(repo_path)
        all_findings.extend(ci_findings)

        # 5. Compute dimension scores
        dimension_scores = self._compute_dimension_scores(all_findings)

        # 6. Compute overall score
        overall_score = sum(
            score * next(d["weight"] for d in TESTING_DIMENSIONS if d["name"] == dim_name)
            for dim_name, score in dimension_scores.items()
        )
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
                    "weight": next(d["weight"] for d in TESTING_DIMENSIONS if d["name"] == dim_name),
                    "checks": self._get_checks_for_dimension(dim_name, all_findings),
                }
                for dim_name, score in dimension_scores.items()
            ],
            "findings": [
                {
                    "id": f.check_id,
                    "perspective": self.PERSPECTIVE_NAME,
                    "dimension": f.dimension,
                    "check_id": f.check_id,
                    "description": f.description,
                    "severity": f.severity,
                    "evidence": f.evidence,
                    "suggested_fix": f.fix_action,
                    "fix_action": f.fix_action,
                    "auto_actionable": f.auto_actionable,
                    "confidence": f.confidence,
                }
                for f in all_findings
            ],
            "summary": {
                "total_checks": len(TESTING_CHECKS),
                "passed": 0,
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

    def _scan_patterns(self, repo_path: Path) -> list[TestingFinding]:
        """Fast regex pattern scan for obvious testing issues."""
        findings = []

        for check_key, check_def in TESTING_CHECKS.items():
            if "patterns" not in check_def:
                continue

            for pattern in check_def["patterns"]:
                for file_type in check_def["file_types"]:
                    # Handle wildcard in path patterns
                    if "*" in file_type:
                        import fnmatch
                        for file_path in repo_path.rglob("*"):
                            if fnmatch.fnmatch(str(file_path), f"*{file_type}") or \
                               fnmatch.fnmatch(file_path.name, file_type):
                                findings.extend(self._check_file_pattern(
                                    file_path, pattern, check_def, repo_path
                                ))
                    else:
                        for file_path in repo_path.rglob(f"*{file_type}"):
                            findings.extend(self._check_file_pattern(
                                file_path, pattern, check_def, repo_path
                            ))

        return findings

    def _check_file_pattern(
        self, file_path: Path, pattern: str, check_def: dict, repo_path: Path
    ) -> list[TestingFinding]:
        """Check a single file against a pattern."""
        findings = []
        if self._should_skip(file_path):
            return findings

        try:
            content = file_path.read_text(errors="ignore")
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            if matches:
                for m in matches:
                    findings.append(TestingFinding(
                        check_id=check_def["id"],
                        dimension=check_def["dimension"],
                        description=check_def["description"],
                        severity=check_def["severity"],
                        file_path=str(file_path.relative_to(repo_path)),
                        line=content[:m.start()].count("\n") + 1,
                        matched_text=m.group(),
                        fix_action=check_def.get("fix_action", ""),
                        auto_actionable=check_def.get("auto_actionable", False),
                        confidence=0.90,
                        is_llm=False,
                    ))
        except Exception:
            pass

        return findings

    def _scan_with_llm(self, repo_path: Path, context) -> list[TestingFinding]:
        """Use LLM to evaluate nuanced testing quality checks."""
        findings = []

        # Determine which checks need LLM evaluation
        for check_key, check_def in TESTING_CHECKS.items():
            if "llm_prompt_template" not in check_def:
                continue

            # Get relevant files for this check
            for file_type in check_def["file_types"]:
                for file_path in repo_path.rglob(f"*{file_type}"):
                    if self._should_skip(file_path):
                        continue
                    if "test" not in str(file_path).lower() and \
                       "spec" not in str(file_path).lower():
                        # Only scan test files for LLM evaluation
                        continue

                    rel_path = str(file_path.relative_to(repo_path))
                    try:
                        content = file_path.read_text(
                            errors="ignore", encoding="utf-8"
                        )
                    except Exception:
                        continue

                    eval_context = EvaluationContext(
                        perspective=self.PERSPECTIVE_NAME,
                        dimension=check_def["dimension"],
                        check_id=check_def["id"],
                        file_path=rel_path,
                        code_snippet=content[:2000],
                        perspective_doc=self._get_perspective_doc(),
                        project_type=getattr(context, "project_type", "generic"),
                        tech_stack=getattr(context, "tech_stack", "python"),
                        previous_decisions=getattr(
                            context, "learnings", {}
                        ).get("decisions", []),
                    )

                    result = self.evaluator.evaluate(eval_context)

                    if result.status in ("fail", "warning"):
                        findings.append(TestingFinding(
                            check_id=check_def["id"],
                            dimension=result.dimension or check_def["dimension"],
                            description=check_def["description"],
                            severity=check_def["severity"],
                            file_path=rel_path,
                            line=0,
                            matched_text="",
                            fix_action=result.fix_action or check_def.get("fix_action", ""),
                            auto_actionable=result.auto_actionable or check_def.get("auto_actionable", False),
                            confidence=result.confidence,
                            is_llm=True,
                            reasoning=result.reasoning,
                        ))

        return findings

    def _scan_coverage_config(self, repo_path: Path) -> list[TestingFinding]:
        """Scan for coverage configuration and report files."""
        findings = []
        coverage_indicators = [
            "coverage", ".coverage", "htmlcov", "cov.xml",
            "coverage.xml", "pytest.ini", "pyproject.toml",
        ]

        for indicator in coverage_indicators:
            for file_path in repo_path.rglob(indicator):
                if self._should_skip(file_path):
                    continue
                # Check for coverage threshold
                try:
                    content = file_path.read_text(errors="ignore")
                    # Look for coverage threshold settings
                    threshold_matches = re.findall(
                        r"fail_under\s*[=:]\s*(\d+)", content, re.IGNORECASE
                    )
                    if not threshold_matches:
                        # No explicit fail_under → coverage may not be enforced
                        findings.append(TestingFinding(
                            check_id="TEST_COV_001",
                            dimension="coverage",
                            description="Core logic coverage ≥ 80%",
                            severity="high",
                            file_path=str(file_path.relative_to(repo_path)),
                            line=0,
                            matched_text="coverage config found but no fail_under threshold",
                            fix_action="add_unit_tests",
                            auto_actionable=False,
                            confidence=0.60,
                            is_llm=False,
                        ))
                except Exception:
                    pass

        return findings

    def _scan_ci_config(self, repo_path: Path) -> list[TestingFinding]:
        """Scan CI configuration files for test integration."""
        findings = []
        ci_patterns = [
            (".github/workflows/*.yml", r"(pytest|npm test|go test|gradle test|mvn test)", "TEST_CI_001"),
            (".github/workflows/*.yml", r"(coverage|codecov|coveralls|jacoco|--cov)", "TEST_CI_002"),
            (".github/workflows/*.yml", r"(required:\s*true|status:\s*pending|fail-fast)", "TEST_CI_003"),
        ]

        for path_pattern, test_pattern, check_id in ci_patterns:
            check_def = TESTING_CHECKS.get(
                next(k for k, v in TESTING_CHECKS.items() if v["id"] == check_id), {}
            )
            for file_path in repo_path.rglob(path_pattern):
                if self._should_skip(file_path):
                    continue
                try:
                    content = file_path.read_text(errors="ignore")
                    if re.search(test_pattern, content, re.IGNORECASE):
                        # Found — this check passes (no finding)
                        pass
                    else:
                        # Missing CI test config
                        findings.append(TestingFinding(
                            check_id=check_id,
                            dimension="ci",
                            description=check_def.get("description", ""),
                            severity=check_def.get("severity", "high"),
                            file_path=str(file_path.relative_to(repo_path)),
                            line=0,
                            matched_text="CI config found but test step missing",
                            fix_action=check_def.get("fix_action", ""),
                            auto_actionable=True,
                            confidence=0.85,
                            is_llm=False,
                        ))
                except Exception:
                    pass

        return findings

    def _compute_dimension_scores(
        self, findings: list[TestingFinding]
    ) -> dict:
        """Compute score per dimension using weighted severity."""
        dim_totals: dict = {d["name"]: 0.0 for d in TESTING_DIMENSIONS}
        dim_counts: dict = {d["name"]: 0 for d in TESTING_DIMENSIONS}

        for f in findings:
            severity_map = {
                "critical": 0.0, "high": 25.0, "medium": 50.0, "low": 75.0
            }
            score = severity_map.get(f.severity, 50.0)
            dim_totals[f.dimension] = dim_totals.get(f.dimension, 0) + score
            dim_counts[f.dimension] += 1

        # Convert to 0-100 scale (0 = lots of critical/high issues)
        scores = {}
        for dim in TESTING_DIMENSIONS:
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

    def _get_checks_for_dimension(
        self, dim_name: str, findings: list[TestingFinding]
    ) -> list[dict]:
        check_ids = next(
            (d["checks"] for d in TESTING_DIMENSIONS if d["name"] == dim_name), []
        )
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
            ".tox", "vendor", "third_party", ".next", ".nuxt",
            "htmlcov", ".parcel-cache", "dist", ".cache",
        }
        return any(part in path.parts for part in skip_dirs)

    def _get_perspective_doc(self) -> str:
        """
        Return the testing perspective standard text for LLM context.
        Attempts to load from references/testing/testing-perspective.md,
        falls back to embedded text.
        """
        # Try to load from project-standard references
        possible_paths = [
            Path("/tmp/auto-evolve/references/testing/testing-perspective.md"),
            Path(__file__).parent.parent.parent / "references" / "testing" / "testing-perspective.md",
        ]

        for p in possible_paths:
            if p.exists():
                try:
                    return p.read_text(encoding="utf-8")
                except Exception:
                    pass

        # Fallback embedded perspective doc
        return """Testing Perspective Standard:

TEST_COV_001: Core logic coverage ≥ 80% (High)
TEST_COV_002: Critical paths have explicit tests (Critical)
TEST_COV_003: Edge cases (null, empty, max) tested (Medium)
TEST_UNIT_001: Unit tests run in < 100ms each (Low)
TEST_UNIT_002: Dependencies mocked in unit tests (Medium)
TEST_UNIT_003: Tests are isolated (no shared state) (High)
TEST_INTEG_001: API endpoints tested end-to-end (High)
TEST_INTEG_002: DB operations tested with transactions (High)
TEST_INTEG_003: Auth flows tested end-to-end (High)
TEST_MAINT_001: No commented-out tests (Low)
TEST_MAINT_002: Flaky tests tracked and fixed (Medium)
TEST_CI_001: Tests run in CI pipeline (Critical)
TEST_CI_002: Coverage reported in CI (High)
TEST_CI_003: PR blocked if tests fail (High)
TEST_STRAT_001: Frontend E2E tests for critical flows (High)
TEST_STRAT_002: Backend API contract tests (High)
TEST_STRAT_003: Security paths have explicit negative tests (High)
"""

    def _iso_now(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def get_dimensions(self) -> list:
        """Return dimension definitions."""
        return TESTING_DIMENSIONS


# ─── Smoke Test ───────────────────────────────────────────────────────────────

def smoke_test():
    """Test the testing scanner initialization."""
    import os

    config = LLMConfig(
        model=os.environ.get("LLM_MODEL", "gpt-4"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )

    scanner = TestingScanner(llm_config=config)

    class MockContext:
        repo_path = "/tmp/test-repo"
        project_type = "backend"
        tech_stack = "python"
        learnings = {"decisions": []}

    print("TestingScanner initialized. Ready to scan.")
    print(f"Perspective: {scanner.PERSPECTIVE_NAME}")
    print(f"Checks: {len(TESTING_CHECKS)}")
    print(f"Dimensions: {len(TESTING_DIMENSIONS)}")


if __name__ == "__main__":
    smoke_test()

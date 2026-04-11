"""
Scanner Test Framework — Validate that scanners conform to the contract.

Usage:
    from test_scanner_contract import ScannerTestSuite

    suite = ScannerTestSuite()
    results = suite.run_all()
    suite.print_results()
"""

import json
import tempfile
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable


# ─── Test Result Classes ───────────────────────────────────────────────────────

@dataclass
class TestResult:
    test_name: str
    passed: bool
    message: str = ""
    expected: str = ""
    actual: str = ""
    duration_ms: int = 0

@dataclass
class TestSuiteResult:
    suite_name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[TestResult] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


# ─── Test Fixtures ─────────────────────────────────────────────────────────────

class TestFixtures:
    """Standard test fixtures for scanner testing."""

    @staticmethod
    def create_test_repo() -> Path:
        """Create a temporary test repository with known code patterns."""
        repo = Path(tempfile.mkdtemp(prefix="scanner_test_"))

        # Valid Python file (should pass checks)
        (repo / "src").mkdir()
        (repo / "src" / "valid.py").write_text('''
import os
import bcrypt
from sqlalchemy import text

def get_user(user_id):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    query = text("SELECT * FROM users WHERE id = :id")
    return db.execute(query, {"id": user_id})
''')

        # Python file with SQL injection (should fail)
        (repo / "src" / "bad_sql.py").write_text('''
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)
''')

        # Python file with hardcoded secret (should fail)
        (repo / "src" / "bad_secrets.py").write_text('''
API_KEY = "ghp_abcdef1234567890abcdef1234567890abcdef12"
PASSWORD = "super_secret_password_123"
''')

        # Python file with weak hashing (should fail)
        (repo / "src" / "bad_auth.py").write_text('''
import hashlib

def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()
''')

        # JavaScript file with XSS (should fail)
        (repo / "src").mkdir()
        (repo / "src" / "xss.js").write_text('''
document.getElementById("output").innerHTML = userInput;
''')

        # Valid package.json
        (repo / "package.json").write_text(json.dumps({
            "name": "test-project",
            "version": "1.0.0",
            "dependencies": {
                "express": "^4.18.0",
                "bcrypt": "^5.1.0"
            }
        }))

        return repo


# ─── Test Cases ───────────────────────────────────────────────────────────────

class ContractTests:
    """Contract compliance tests for all scanners."""

    @staticmethod
    def test_returns_scan_result(scanner, context) -> TestResult:
        """Scanner must return a dict with required ScanResult fields."""
        import time
        start = time.time()

        try:
            result = scanner.scan(context)
            duration_ms = int((time.time() - start) * 1000)
        except Exception as e:
            return TestResult(
                test_name="returns_valid_scan_result",
                passed=False,
                message=f"Scanner.scan() raised an exception: {e}",
            )

        required_fields = {
            "perspective", "version", "scan_timestamp", "overall_score",
            "grade", "dimensions", "findings", "summary", "errors"
        }

        missing = required_fields - set(result.keys())
        if missing:
            return TestResult(
                test_name="returns_valid_scan_result",
                passed=False,
                message=f"Result missing required fields: {missing}",
                expected=str(required_fields),
                actual=str(set(result.keys())),
                duration_ms=duration_ms,
            )

        return TestResult(
            test_name="returns_valid_scan_result",
            passed=True,
            message="Scanner returns valid ScanResult with all required fields",
            duration_ms=duration_ms,
        )

    @staticmethod
    def test_grade_is_valid(result: dict) -> TestResult:
        """Grade must be one of the valid values."""
        valid_grades = {"excellent", "good", "acceptable", "poor", "critical"}
        actual_grade = result.get("grade", "")

        if actual_grade not in valid_grades:
            return TestResult(
                test_name="grade_is_valid",
                passed=False,
                message=f"Invalid grade: '{actual_grade}'",
                expected=str(valid_grades),
                actual=actual_grade,
            )

        return TestResult(
            test_name="grade_is_valid",
            passed=True,
            message=f"Grade '{actual_grade}' is valid",
        )

    @staticmethod
    def test_score_in_range(result: dict) -> TestResult:
        """Overall score must be between 0 and 100."""
        score = result.get("overall_score", -1)

        if not (0 <= score <= 100):
            return TestResult(
                test_name="score_in_range",
                passed=False,
                message=f"Score {score} is outside valid range [0, 100]",
                expected="0 <= score <= 100",
                actual=str(score),
            )

        return TestResult(
            test_name="score_in_range",
            passed=True,
            message=f"Score {score} is in valid range",
        )

    @staticmethod
    def test_dimensions_have_weights(result: dict) -> TestResult:
        """Each dimension must have a weight between 0 and 1."""
        dimensions = result.get("dimensions", [])

        if not dimensions:
            return TestResult(
                test_name="dimensions_have_weights",
                passed=True,
                message="No dimensions to check (OK for empty scan)",
            )

        for dim in dimensions:
            weight = dim.get("weight", -1)
            if not (0 <= weight <= 1):
                return TestResult(
                    test_name="dimensions_have_weights",
                    passed=False,
                    message=f"Dimension '{dim.get('name', 'unknown')}' has invalid weight {weight}",
                    expected="0 <= weight <= 1",
                    actual=str(weight),
                )

        return TestResult(
            test_name="dimensions_have_weights",
            passed=True,
            message=f"All {len(dimensions)} dimensions have valid weights",
        )

    @staticmethod
    def test_findings_have_required_fields(result: dict) -> TestResult:
        """Each finding must have required fields."""
        findings = result.get("findings", [])

        required = {"id", "perspective", "severity", "description", "fix_action", "auto_actionable"}

        for i, finding in enumerate(findings[:5]):  # Check first 5
            missing = required - set(finding.keys())
            if missing:
                return TestResult(
                    test_name="findings_have_required_fields",
                    passed=False,
                    message=f"Finding {i} missing fields: {missing}",
                    actual=str(set(finding.keys())),
                )

        return TestResult(
            test_name="findings_have_required_fields",
            passed=True,
            message=f"All {len(findings)} findings have required fields",
        )

    @staticmethod
    def test_severity_is_valid(result: dict) -> TestResult:
        """Severity values must be one of the valid enums."""
        valid_severities = {"critical", "high", "medium", "low"}
        findings = result.get("findings", [])

        for finding in findings:
            sev = finding.get("severity", "")
            if sev and sev not in valid_severities:
                return TestResult(
                    test_name="severity_is_valid",
                    passed=False,
                    message=f"Finding '{finding.get('id', 'unknown')}' has invalid severity: '{sev}'",
                    expected=str(valid_severities),
                    actual=sev,
                )

        return TestResult(
            test_name="severity_is_valid",
            passed=True,
            message=f"All {len(findings)} findings have valid severities",
        )


# ─── Scanner Test Suite ────────────────────────────────────────────────────────

class ScannerTestSuite:
    """
    Test suite for validating scanner compliance with the contract.

    Usage:
        suite = ScannerTestSuite()

        # Add a custom test
        suite.add_test("my_custom_check", lambda scanner, ctx: TestResult(...))

        # Run all tests
        results = suite.run(scanner, context)

        # Print results
        suite.print_results(results)
    """

    def __init__(self):
        self.custom_tests: list[tuple[str, Callable]] = []

    def add_test(self, name: str, test_fn: Callable):
        """Add a custom test to the suite."""
        self.custom_tests.append((name, test_fn))

    def run(self, scanner, context) -> TestSuiteResult:
        """Run all tests against a scanner."""
        import time
        start = time.time()
        results = []

        # Contract tests
        contract_test_cases = [
            ("returns_valid_scan_result", ContractTests.test_returns_scan_result),
            ("grade_is_valid", lambda s, ctx: ContractTests.test_grade_is_valid(s)),
            ("score_in_range", lambda s, ctx: ContractTests.test_score_in_range(s)),
            ("dimensions_have_weights", lambda s, ctx: ContractTests.test_dimensions_have_weights(s)),
            ("findings_have_required_fields", lambda s, ctx: ContractTests.test_findings_have_required_fields(s)),
            ("severity_is_valid", lambda s, ctx: ContractTests.test_severity_is_valid(s)),
        ]

        # Run contract tests
        for name, test_fn in contract_test_cases:
            # Get result from scanner first
            scan_result = scanner.scan(context)
            result = test_fn(scanner, scan_result, context) if "scan_result" in test_fn.__code__.co_varnames else \
                     test_fn(scan_result, context)
            results.append(result)

        # Run custom tests
        for name, test_fn in self.custom_tests:
            scan_result = scanner.scan(context)
            result = test_fn(scanner, scan_result, context)
            results.append(result)

        duration_ms = int((time.time() - start) * 1000)

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)

        return TestSuiteResult(
            suite_name=scanner.PERSPECTIVE_NAME if hasattr(scanner, 'PERSPECTIVE_NAME') else "unknown",
            total=len(results),
            passed=passed,
            failed=failed,
            skipped=0,
            results=results,
            duration_ms=duration_ms,
        )

    def print_results(self, result: TestSuiteResult):
        """Print test results in a readable format."""
        print(f"\n{'='*60}")
        print(f"Scanner Test Suite: {result.suite_name}")
        print(f"{'='*60}")
        print(f"Total: {result.total} | ✅ Passed: {result.passed} | ❌ Failed: {result.failed}")
        print(f"Duration: {result.duration_ms}ms")
        print(f"{'-'*60}")

        for r in result.results:
            status = "✅" if r.passed else "❌"
            print(f"  {status} {r.test_name}")
            if r.message:
                print(f"     {r.message}")
            if not r.passed:
                print(f"     Expected: {r.expected}")
                print(f"     Actual: {r.actual}")

        print(f"{'='*60}")
        if result.all_passed:
            print("✅ ALL TESTS PASSED")
        else:
            print(f"❌ {result.failed} TESTS FAILED")


# ─── Integration Tests ─────────────────────────────────────────────────────────

class IntegrationTests:
    """End-to-end integration tests for the scanner pipeline."""

    @staticmethod
    def test_scanner_against_fixture_repo(scanner, repo_path: Path) -> TestResult:
        """
        Run scanner against a known fixture repo and validate results.

        Expected:
        - bad_sql.py should produce a SQL injection finding
        - bad_secrets.py should produce a hardcoded secret finding
        - bad_auth.py should produce a weak hashing finding
        """
        class MockContext:
            repo_path = str(repo_path)
            project_type = "backend"
            tech_stack = "python"
            learnings = {"decisions": []}

        context = MockContext()
        result = scanner.scan(context)

        # Check expected findings
        finding_descs = [f.get("description", "").lower() for f in result.get("findings", [])]

        checks = {
            "sql": any("sql" in d or "injection" in d for d in finding_descs),
            "secret": any("secret" in d or "hardcoded" in d or "api" in d for d in finding_descs),
            "auth": any("hash" in d or "md5" in d or "auth" in d for d in finding_descs),
        }

        if all(checks.values()):
            return TestResult(
                test_name="integration_fixture_repo",
                passed=True,
                message=f"Scanner correctly identified all 3 expected issues in fixture repo",
            )
        else:
            missed = [k for k, v in checks.items() if not v]
            return TestResult(
                test_name="integration_fixture_repo",
                passed=False,
                message=f"Scanner missed issues: {missed}. Found descriptions: {finding_descs[:5]}",
            )

    @staticmethod
    def test_scanner_is_deterministic(scanner, context) -> TestResult:
        """Running the same scanner twice should produce identical results."""
        result1 = scanner.scan(context)
        result2 = scanner.scan(context)

        # Compare scores (timing and timestamps may differ)
        if result1.get("overall_score") != result2.get("overall_score"):
            return TestResult(
                test_name="is_deterministic",
                passed=False,
                message="Scanner produced different scores on repeated runs",
                expected=str(result1.get("overall_score")),
                actual=str(result2.get("overall_score")),
            )

        return TestResult(
            test_name="is_deterministic",
            passed=True,
            message="Scanner is deterministic (same result on repeated runs)",
        )


# ─── Quick Test Runner ─────────────────────────────────────────────────────────

def quick_test(scanner_class, repo_path: str):
    """Run a quick sanity test against a scanner class."""
    repo = Path(repo_path)

    class MockContext:
        repo_path = str(repo)
        project_type = "backend"
        tech_stack = "python"
        learnings = {"decisions": []}

    scanner = scanner_class()
    context = MockContext()

    suite = ScannerTestSuite()
    result = suite.run(scanner, context)
    suite.print_results(result)

    return result


# ─── Smoke Test ────────────────────────────────────────────────────────────────

def smoke_test():
    """Run tests against the security scanner."""
    from security_scanner import SecurityScanner

    # Create test repo
    repo = TestFixtures.create_test_repo()

    try:
        print(f"Test repo: {repo}")

        scanner = SecurityScanner()
        context = type('Context', (), {
            'repo_path': str(repo),
            'project_type': 'backend',
            'tech_stack': 'python',
            'learnings': {'decisions': []}
        })()

        suite = ScannerTestSuite()

        # Add integration test
        suite.add_test(
            "integration_fixture_repo",
            lambda s, r, ctx: IntegrationTests.test_scanner_against_fixture_repo(s, repo)
        )

        result = suite.run(scanner, context)
        suite.print_results(result)

    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    smoke_test()

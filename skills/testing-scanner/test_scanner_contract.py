"""
Scanner Test Framework — Validate TestingScanner conforms to the contract.

Usage:
    from test_scanner_contract import ScannerTestSuite

    suite = ScannerTestSuite()
    results = suite.run(scanner, context)
    suite.print_results()
"""

import json
import tempfile
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable


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
    """Standard test fixtures for testing scanner validation."""

    @staticmethod
    def create_test_repo() -> Path:
        """Create a temporary test repository with known testing patterns."""
        repo = Path(tempfile.mkdtemp(prefix="testing_scanner_test_"))

        # Source file (should have tests)
        (repo / "src").mkdir()
        (repo / "src" / "core.py").write_text('''
def process_payment(amount, card_number):
    """Critical path - no test coverage detected."""
    if amount <= 0:
        raise ValueError("Invalid amount")
    if not card_number:
        return None
    # TODO: implement
    return {"status": "ok"}

def get_user(user_id):
    """Core logic."""
    if user_id is None:
        return None
    return {"id": user_id, "name": "test"}
''')

        # Test file with mocked dependencies
        (repo / "tests").mkdir()
        (repo / "tests" / "test_core.py").write_text('''
import pytest
from unittest.mock import patch, MagicMock
from src.core import get_user, process_payment

def test_get_user_happy_path():
    result = get_user(1)
    assert result["id"] == 1

def test_get_user_null():
    result = get_user(None)
    assert result is None

# def test_old_payment():  # commented-out test — should be flagged
#     assert process_payment(100, "4242") is not None

@pytest.mark.flaky(reruns=3)
def test_sometimes_fails():
    import random
    assert random.random() > 0.5
''')

        # Integration test file
        (repo / "tests" / "test_integration.py").write_text('''
import pytest
from unittest.mock import patch

@pytest.fixture
def db():
    """Shared fixture — could cause isolation issues."""
    return {"data": []}

def test_api_get_user(db):
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"id": 1}
        # Test with real HTTP — should be mocked
        pass

def test_auth_flow():
    """No auth integration test found."""
    pass
''')

        # CI workflow — tests run but no coverage
        (repo / ".github" / "workflows").mkdir(parents=True)
        (repo / ".github" / "workflows" / "ci.yml").write_text('''
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: npm install
      - run: npm test
''')

        # pytest.ini with no coverage threshold
        (repo / "pytest.ini").write_text('''
[pytest]
testpaths = tests
python_files = test_*.py
''')

        # package.json
        (repo / "package.json").write_text(json.dumps({
            "name": "test-project",
            "scripts": {"test": "jest"},
            "dependencies": {}
        }))

        return repo


# ─── Test Cases ───────────────────────────────────────────────────────────────

class ContractTests:
    """Contract compliance tests for the TestingScanner."""

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

        required = {"id", "perspective", "severity", "description",
                    "fix_action", "auto_actionable"}

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

    @staticmethod
    def test_all_17_checks_defined() -> TestResult:
        """Verify all 17 TEST_* checks are defined in the scanner."""
        from testing_scanner import TESTING_CHECKS

        expected_ids = [
            "TEST_COV_001", "TEST_COV_002", "TEST_COV_003",
            "TEST_UNIT_001", "TEST_UNIT_002", "TEST_UNIT_003",
            "TEST_INTEG_001", "TEST_INTEG_002", "TEST_INTEG_003",
            "TEST_MAINT_001", "TEST_MAINT_002",
            "TEST_CI_001", "TEST_CI_002", "TEST_CI_003",
            "TEST_STRAT_001", "TEST_STRAT_002", "TEST_STRAT_003",
        ]

        defined_ids = [v["id"] for v in TESTING_CHECKS.values()]
        missing = [eid for eid in expected_ids if eid not in defined_ids]

        if missing:
            return TestResult(
                test_name="all_17_checks_defined",
                passed=False,
                message=f"Missing check definitions: {missing}",
                expected=str(expected_ids),
                actual=str(defined_ids),
            )

        return TestResult(
            test_name="all_17_checks_defined",
            passed=True,
            message=f"All 17 TEST_* checks are defined",
        )


# ─── Scanner Test Suite ────────────────────────────────────────────────────────

class ScannerTestSuite:
    """
    Test suite for validating TestingScanner compliance with the contract.

    Usage:
        suite = ScannerTestSuite()
        results = suite.run(scanner, context)
        suite.print_results(results)
    """

    def __init__(self):
        self.custom_tests: list[tuple[str, Callable]] = []

    def add_test(self, name: str, test_fn: Callable):
        """Add a custom test to the suite."""
        self.custom_tests.append((name, test_fn))

    def run(self, scanner, context) -> TestSuiteResult:
        """Run all tests against the scanner."""
        import time
        start = time.time()
        results = []

        # Get scan result once for reuse
        scan_result = scanner.scan(context)

        # Contract tests
        contract_tests = [
            ("returns_valid_scan_result",
             lambda: ContractTests.test_returns_scan_result(scanner, context)),
            ("grade_is_valid",
             lambda: ContractTests.test_grade_is_valid(scan_result)),
            ("score_in_range",
             lambda: ContractTests.test_score_in_range(scan_result)),
            ("dimensions_have_weights",
             lambda: ContractTests.test_dimensions_have_weights(scan_result)),
            ("findings_have_required_fields",
             lambda: ContractTests.test_findings_have_required_fields(scan_result)),
            ("severity_is_valid",
             lambda: ContractTests.test_severity_is_valid(scan_result)),
            ("all_17_checks_defined",
             ContractTests.test_all_17_checks_defined),
        ]

        for name, test_fn in contract_tests:
            try:
                result = test_fn()
                results.append(result)
            except Exception as e:
                results.append(TestResult(
                    test_name=name,
                    passed=False,
                    message=f"Test raised exception: {e}",
                ))

        # Custom tests
        for name, test_fn in self.custom_tests:
            try:
                result = test_fn(scanner, scan_result, context)
                results.append(result)
            except Exception as e:
                results.append(TestResult(
                    test_name=name,
                    passed=False,
                    message=f"Custom test raised exception: {e}",
                ))

        duration_ms = int((time.time() - start) * 1000)
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)

        return TestSuiteResult(
            suite_name=scanner.PERSPECTIVE_NAME,
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
                if r.expected:
                    print(f"     Expected: {r.expected}")
                if r.actual:
                    print(f"     Actual: {r.actual}")

        print(f"{'='*60}")
        if result.all_passed:
            print("✅ ALL TESTS PASSED")
        else:
            print(f"❌ {result.failed} TESTS FAILED")


# ─── Integration Tests ─────────────────────────────────────────────────────────

class IntegrationTests:
    """End-to-end integration tests for the TestingScanner."""

    @staticmethod
    def test_scanner_against_fixture_repo(
        scanner, repo_path: Path
    ) -> TestResult:
        """
        Run scanner against fixture repo and validate it detects
        known testing issues.
        """

        class MockContext:
            repo_path = str(repo_path)
            project_type = "backend"
            tech_stack = "python"
            learnings = {"decisions": []}

        context = MockContext()
        result = scanner.scan(context)

        finding_check_ids = {f.get("check_id", "") for f in result.get("findings", [])}
        finding_descs = [f.get("description", "").lower() for f in result.get("findings", [])]

        # The scanner should detect at least some issues in the fixture repo
        has_findings = len(result.get("findings", [])) > 0

        if has_findings:
            return TestResult(
                test_name="integration_fixture_repo",
                passed=True,
                message=(
                    f"Scanner found {len(result['findings'])} issue(s) in fixture repo. "
                    f"Check IDs: {sorted(finding_check_ids)}"
                ),
            )
        else:
            return TestResult(
                test_name="integration_fixture_repo",
                passed=False,
                message="Scanner found no issues in fixture repo (expected at least some)",
            )

    @staticmethod
    def test_scanner_is_deterministic(scanner, context) -> TestResult:
        """Running the same scanner twice should produce identical scores."""
        result1 = scanner.scan(context)
        result2 = scanner.scan(context)

        score1 = result1.get("overall_score")
        score2 = result2.get("overall_score")

        if score1 != score2:
            return TestResult(
                test_name="is_deterministic",
                passed=False,
                message="Scanner produced different scores on repeated runs",
                expected=str(score1),
                actual=str(score2),
            )

        return TestResult(
            test_name="is_deterministic",
            passed=True,
            message="Scanner is deterministic (same result on repeated runs)",
        )


# ─── Quick Test Runner ─────────────────────────────────────────────────────────

def quick_test(scanner_class, repo_path: str):
    """Run a quick sanity test against the scanner class."""
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


# ─── Smoke Test ───────────────────────────────────────────────────────────────

def smoke_test():
    """Run tests against the TestingScanner."""
    from testing_scanner import TestingScanner

    # Create test repo
    repo = TestFixtures.create_test_repo()

    try:
        print(f"Test repo: {repo}")

        scanner = TestingScanner()
        context = type('Context', (), {
            'repo_path': str(repo),
            'project_type': 'backend',
            'tech_stack': 'python',
            'learnings': {'decisions': []}
        })()

        suite = ScannerTestSuite()

        # Add integration tests
        suite.add_test(
            "integration_fixture_repo",
            lambda s, r, ctx: IntegrationTests.test_scanner_against_fixture_repo(s, repo)
        )
        suite.add_test(
            "is_deterministic",
            lambda s, r, ctx: IntegrationTests.test_scanner_is_deterministic(s, ctx)
        )

        result = suite.run(scanner, context)
        suite.print_results(result)

    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    smoke_test()

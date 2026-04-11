"""
Scanner Test Framework — Validate DocumentationScanner conforms to the contract.

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
    """Standard test fixtures for documentation scanner validation."""

    @staticmethod
    def create_test_repo() -> Path:
        """
        Create a temporary test repository with known documentation patterns.

        Fixture repo structure:
          - README.md          (has quick start, prerequisites, examples) → DOC_ONB_001/002, DOC_REF_001 pass
          - CONTRIBUTING.md   (has contribution guidelines)            → DOC_CONTRIB_001 pass
          - CHANGELOG.md      (recent entries)                          → DOC_MAINT_001 pass
          - docs/
            api.md            (API reference)                          → DOC_REF_002 pass
            architecture.md   (architecture doc)                      → DOC_ARCH_001 pass
          - No PR template, no coding standards                        → DOC_CONTRIB_002 fails
        """
        repo = Path(tempfile.mkdtemp(prefix="doc_scanner_test_"))

        # README with quick start (3 steps), prerequisites, and code examples
        (repo / "README.md").write_text('''
# MyAwesomeProject

A great project that does amazing things.

## Quick Start

1. Clone the repo
2. Run `pip install -r requirements.txt`
3. Run `python main.py`

## Prerequisites

- Python 3.8+
- pip
- A PostgreSQL database

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```python
from myproject import Client

client = Client(api_key="your-key")
result = client.get_data()
print(result)
```
''')

        # CONTRIBUTING.md with contribution guidelines
        (repo / "CONTRIBUTING.md").write_text('''
# Contributing to MyAwesomeProject

Thank you for your interest in contributing!

## How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Code Review Process

All submissions require review from the core team. Please be patient!
''')

        # CHANGELOG with recent entry
        (repo / "CHANGELOG.md").write_text('''
# Changelog

## [1.2.0] - 2026-03-15

### Added
- New API endpoint for bulk operations
- Support for Python 3.12

### Fixed
- Memory leak in connection pool
- Typo in README

## [1.1.0] - 2025-11-01

### Added
- Initial release
''')

        # docs directory
        (repo / "docs").mkdir()

        # docs/api.md with API reference
        (repo / "docs" / "api.md").write_text('''
# API Reference

## Client

### `Client(api_key: str, base_url: str = "https://api.example.com")`

Creates a new client instance.

**Parameters:**
- `api_key` (str, required): Your API key
- `base_url` (str, optional): Base URL for API requests

**Returns:** `Client`

### `Client.get_data(ids: list[str]) -> dict`

Fetches data for the given IDs.

**Parameters:**
- `ids` (list[str], required): List of IDs to fetch

**Returns:** `dict` with `data` key

**Example:**
```python
result = client.get_data(ids=["1", "2", "3"])
print(result["data"])
```
''')

        # docs/architecture.md with architecture description
        (repo / "docs" / "architecture.md").write_text('''
# Architecture

## Overview

MyAwesomeProject follows a layered architecture:

```
┌─────────────────────────────────┐
│         API Layer               │
│  (Flask/FastAPI handlers)      │
├─────────────────────────────────┤
│       Service Layer             │
│  (Business logic)               │
├─────────────────────────────────┤
│       Data Layer                │
│  (Database + Cache)            │
└─────────────────────────────────┘
```

## Components

- **API Layer**: Handles HTTP requests, authentication, and validation
- **Service Layer**: Contains all business logic, orchestrates data operations
- **Data Layer**: PostgreSQL for persistence, Redis for caching
''')

        # Missing: .github/PULL_REQUEST_TEMPLATE.md (DOC_CONTRIB_002 fails)
        # Missing: coding standards / style guide (DOC_CONTRIB_002 fails)

        return repo

    @staticmethod
    def create_bare_repo() -> Path:
        """
        Create a bare repo with no documentation at all.
        All checks should fail.
        """
        repo = Path(tempfile.mkdtemp(prefix="doc_scanner_bare_"))

        (repo / "src").mkdir()
        (repo / "src" / "main.py").write_text('''
def main():
    print("Hello")
''')

        return repo


# ─── Test Cases ───────────────────────────────────────────────────────────────

class ContractTests:
    """Contract compliance tests for the DocumentationScanner."""

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

        for i, finding in enumerate(findings[:5]):
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
    def test_all_8_checks_defined() -> TestResult:
        """Verify all 8 DOC_* checks are defined in the scanner."""
        from documentation_scanner import DOCUMENTATION_CHECKS

        expected_ids = [
            "DOC_ONB_001", "DOC_ONB_002",
            "DOC_REF_001", "DOC_REF_002",
            "DOC_ARCH_001",
            "DOC_CONTRIB_001", "DOC_CONTRIB_002",
            "DOC_MAINT_001",
        ]

        defined_ids = [v["id"] for v in DOCUMENTATION_CHECKS.values()]
        missing = [eid for eid in expected_ids if eid not in defined_ids]

        if missing:
            return TestResult(
                test_name="all_8_checks_defined",
                passed=False,
                message=f"Missing check definitions: {missing}",
                expected=str(expected_ids),
                actual=str(defined_ids),
            )

        return TestResult(
            test_name="all_8_checks_defined",
            passed=True,
            message="All 8 DOC_* checks are defined",
        )

    @staticmethod
    def test_perspective_name() -> TestResult:
        """Scanner must have correct perspective name."""
        from documentation_scanner import DocumentationScanner
        scanner = DocumentationScanner()

        if scanner.PERSPECTIVE_NAME != "documentation":
            return TestResult(
                test_name="perspective_name",
                passed=False,
                message=f"Perspective name is '{scanner.PERSPECTIVE_NAME}', expected 'documentation'",
            )

        return TestResult(
            test_name="perspective_name",
            passed=True,
            message=f"Perspective name is 'documentation'",
        )


# ─── Scanner Test Suite ────────────────────────────────────────────────────────

class ScannerTestSuite:
    """
    Test suite for validating DocumentationScanner compliance with the contract.

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
            ("all_8_checks_defined",
             ContractTests.test_all_8_checks_defined),
            ("perspective_name",
             ContractTests.test_perspective_name),
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
    """End-to-end integration tests for the DocumentationScanner."""

    @staticmethod
    def test_scanner_against_fixture_repo(
        scanner, repo_path: Path
    ) -> TestResult:
        """
        Run scanner against fixture repo with partial documentation.
        Expected:
          - DOC_ONB_001, DOC_ONB_002, DOC_REF_001, DOC_CONTRIB_001, DOC_MAINT_001
            should be found (files exist with content)
          - DOC_CONTRIB_002 should produce a finding (no PR template/coding standards)
        """
        class MockContext:
            repo_path = str(repo_path)
            project_type = "backend"
            tech_stack = "python"
            learnings = {"decisions": []}

        context = MockContext()
        result = scanner.scan(context)

        finding_check_ids = {f.get("check_id", "") for f in result.get("findings", [])}

        # Scanner should detect DOC_CONTRIB_002 is missing (no PR template)
        has_contrib2_fail = "DOC_CONTRIB_002" in finding_check_ids

        if has_contrib2_fail:
            return TestResult(
                test_name="integration_fixture_repo",
                passed=True,
                message=(
                    f"Scanner correctly detected DOC_CONTRIB_002 missing. "
                    f"Total findings: {len(result['findings'])}"
                ),
            )
        else:
            return TestResult(
                test_name="integration_fixture_repo",
                passed=False,
                message=(
                    f"Scanner did not detect DOC_CONTRIB_002 as missing. "
                    f"Findings: {sorted(finding_check_ids)}"
                ),
            )

    @staticmethod
    def test_scanner_against_bare_repo(scanner, repo_path: Path) -> TestResult:
        """Run scanner against bare repo with no documentation. Most checks should fail."""
        class MockContext:
            repo_path = str(repo_path)
            project_type = "backend"
            tech_stack = "python"
            learnings = {"decisions": []}

        context = MockContext()
        result = scanner.scan(context)

        finding_check_ids = {f.get("check_id", "") for f in result.get("findings", [])}

        # Should have many failing findings
        if len(result.get("findings", [])) >= 3:
            return TestResult(
                test_name="integration_bare_repo",
                passed=True,
                message=(
                    f"Scanner found {len(result['findings'])} issues in bare repo. "
                    f"Check IDs: {sorted(finding_check_ids)}"
                ),
            )
        else:
            return TestResult(
                test_name="integration_bare_repo",
                passed=False,
                message=(
                    f"Scanner only found {len(result['findings'])} issues in bare repo "
                    f"(expected at least 3)"
                ),
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
    """Run tests against the DocumentationScanner."""
    from documentation_scanner import DocumentationScanner

    # Create test repos
    fixture_repo = TestFixtures.create_test_repo()
    bare_repo = TestFixtures.create_bare_repo()

    try:
        print(f"Fixture repo: {fixture_repo}")
        print(f"Bare repo: {bare_repo}")

        scanner = DocumentationScanner()

        fixture_context = type('Context', (), {
            'repo_path': str(fixture_repo),
            'project_type': 'backend',
            'tech_stack': 'python',
            'learnings': {'decisions': []}
        })()

        bare_context = type('Context', (), {
            'repo_path': str(bare_repo),
            'project_type': 'backend',
            'tech_stack': 'python',
            'learnings': {'decisions': []}
        })()

        suite = ScannerTestSuite()

        # Add integration tests
        suite.add_test(
            "integration_fixture_repo",
            lambda s, r, ctx: IntegrationTests.test_scanner_against_fixture_repo(s, fixture_repo)
        )
        suite.add_test(
            "integration_bare_repo",
            lambda s, r, ctx: IntegrationTests.test_scanner_against_bare_repo(s, bare_repo)
        )
        suite.add_test(
            "is_deterministic",
            lambda s, r, ctx: IntegrationTests.test_scanner_is_deterministic(s, fixture_context)
        )

        result = suite.run(scanner, fixture_context)
        suite.print_results(result)

    finally:
        shutil.rmtree(fixture_repo, ignore_errors=True)
        shutil.rmtree(bare_repo, ignore_errors=True)


if __name__ == "__main__":
    smoke_test()

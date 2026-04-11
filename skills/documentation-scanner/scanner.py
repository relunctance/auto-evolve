"""
Documentation Perspective Scanner — auto-evolve

This scanner evaluates a repository's documentation quality across 5 dimensions:
  - Onboarding:    README quick start, prerequisites
  - Reference:      API reference completeness and examples
  - Architecture:  Architecture document existence and quality
  - Contributing:   CONTRIBUTING.md guidelines and PR template
  - Maintenance:   Changelog maintenance

Usage:
    from documentation_scanner import DocumentationScanner
    scanner = DocumentationScanner()
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

DOCUMENTATION_CHECKS = {
    # ── Onboarding ─────────────────────────────────────────────────────────────
    "onb_quick_start": {
        "id": "DOC_ONB_001",
        "check_id": "DOC_ONB_001",
        "description": "Quick start guide completes in ≤5 steps",
        "severity": "medium",
        "auto_actionable": False,
        "fix_action": "add_quickstart_guide",
        "patterns": [
            r"#+\s*(quick\s*start|getting\s*started|installation)",
            r"#+\s*(setup|prerequisites|requirements?)",
        ],
        "file_types": ["README.md", "README.rst", "README.txt"],
        "dimension": "onboarding",
        "llm_prompt_template": (
            "Evaluate whether the README contains a quick start section that "
            "can be completed in 5 or fewer steps. Check for numbered steps, "
            "a minimal install process, and a 'your first run' example."
        ),
    },
    "onb_prerequisites": {
        "id": "DOC_ONB_002",
        "check_id": "DOC_ONB_002",
        "description": "Prerequisites are clearly stated",
        "severity": "medium",
        "auto_actionable": False,
        "fix_action": "document_prerequisites",
        "patterns": [
            r"(prerequisit|requirement|needed|before\s+you\s+start)",
            r"(node|python|java|go|docker)\s+\d+[\.\d]*",
            r"(install|setup|configure|environment)",
        ],
        "file_types": ["README.md", "README.rst", "README.txt", "INSTALL.md",
                       "SETUP.md", "docs/installation.md"],
        "dimension": "onboarding",
        "llm_prompt_template": (
            "Check if the project clearly states all prerequisites: required "
            "runtime versions, external services, environment variables, and "
            "any accounts or keys needed before setup."
        ),
    },
    # ── Reference ───────────────────────────────────────────────────────────────
    "ref_readme_examples": {
        "id": "DOC_REF_001",
        "check_id": "DOC_REF_001",
        "description": "README has working code examples",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "add_code_examples",
        "patterns": [
            r"```[\w\+\-#]+.*?```",   # fenced code blocks
            r"`[^`\n]+`",              # inline code
            r"(example|usage|try|run|hands?[- ]?on)",
        ],
        "file_types": ["README.md", "README.rst", "README.txt"],
        "dimension": "reference",
        "llm_prompt_template": (
            "Check if the README contains working code examples that demonstrate "
            "how to use the library/CLI/service. Examples should be runnable "
            "and cover at least one primary use case."
        ),
    },
    "ref_api_complete": {
        "id": "DOC_REF_002",
        "check_id": "DOC_REF_002",
        "description": "API reference is complete and up-to-date",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "document_api_reference",
        "patterns": [
            r"(api|reference|endpoints?|methods?|functions?)",
            r"(/api/|openapi|swagger|postman)",
            r"##?\s*(api|reference|endpoints?)",
        ],
        "file_types": ["docs/api.md", "docs/reference.md", "API.md", "REFERENCE.md",
                       "api.md", "reference.md", "docs/"],
        "dimension": "reference",
        "llm_prompt_template": (
            "Check if the API reference is complete: all endpoints/methods "
            "are documented with request/response examples, parameter tables, "
            "and error code descriptions."
        ),
    },
    # ── Architecture ───────────────────────────────────────────────────────────
    "arch_document": {
        "id": "DOC_ARCH_001",
        "check_id": "DOC_ARCH_001",
        "description": "Architecture document exists and describes system design",
        "severity": "medium",
        "auto_actionable": False,
        "fix_action": "write_architecture_doc",
        "patterns": [
            r"(architecture|system\s*design|design\s*overview)",
            r"(component|module|service|layer)",
            r"(diagram|flow|sequence)",
        ],
        "file_types": ["ARCHITECTURE.md", "ARCH.md", "DESIGN.md",
                       "docs/architecture.md", "docs/design.md"],
        "dimension": "architecture",
        "llm_prompt_template": (
            "Check if the project has an architecture or design document that "
            "describes the high-level system components, their responsibilities, "
            "and how data flows between them. Diagrams are a plus."
        ),
    },
    # ── Contributing ──────────────────────────────────────────────────────────
    "contrib_guidelines": {
        "id": "DOC_CONTRIB_001",
        "check_id": "DOC_CONTRIB_001",
        "description": "CONTRIBUTING.md exists with contribution guidelines",
        "severity": "high",
        "auto_actionable": False,
        "fix_action": "add_contributing_guide",
        "patterns": [
            r"(contributing|contribution|submit|pull\s*request|patch)",
            r"(fork|clone|branch|merge|commit)",
        ],
        "file_types": ["CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING.txt",
                       ".github/CONTRIBUTING.md"],
        "dimension": "contributing",
        "llm_prompt_template": (
            "Check if a CONTRIBUTING.md file exists and contains clear guidelines "
            "on how to submit changes, what the review process looks like, "
            "and any coding or commit conventions."
        ),
    },
    "contrib_standards": {
        "id": "DOC_CONTRIB_002",
        "check_id": "DOC_CONTRIB_002",
        "description": "Coding standards and PR template provided",
        "severity": "medium",
        "auto_actionable": False,
        "fix_action": "add_pr_template",
        "patterns": [
            r"(coding\s*standard|code\s*style|convention|lint|format)",
            r"(PR|pull\s*request)\s*template",
            r"(\.github/PULL_REQUEST_TEMPLATE|PR_TEMPLATE)",
        ],
        "file_types": ["CONTRIBUTING.md", ".github/", "docs/"],
        "dimension": "contributing",
        "llm_prompt_template": (
            "Check if the project provides coding standards (style guide, linter "
            "config) and a PR template that helps contributors describe their "
            "changes, link issues, and explain testing done."
        ),
    },
    # ── Maintenance ───────────────────────────────────────────────────────────
    "maint_changelog": {
        "id": "DOC_MAINT_001",
        "check_id": "DOC_MAINT_001",
        "description": "Changelog maintained with recent entries",
        "severity": "low",
        "auto_actionable": False,
        "fix_action": "maintain_changelog",
        "patterns": [
            r"(changelog|history|changes|release\s*notes)",
            r"\d+\.\d+\.\d+",   # version numbers like 1.2.3
            r"##?\s*\[?\d+\.",
        ],
        "file_types": ["CHANGELOG.md", "CHANGELOG.rst", "HISTORY.md",
                       "RELEASES.md", "CHANGELOG.txt"],
        "dimension": "maintenance",
        "llm_prompt_template": (
            "Check if a CHANGELOG exists and has been updated recently (within "
            "the last 6 months). Entries should describe what changed, not just "
            "list version numbers."
        ),
    },
}


# ─── Dimension Definitions ────────────────────────────────────────────────────

DOCUMENTATION_DIMENSIONS = [
    {
        "name": "onboarding",
        "weight": 0.20,
        "checks": ["DOC_ONB_001", "DOC_ONB_002"],
    },
    {
        "name": "reference",
        "weight": 0.25,
        "checks": ["DOC_REF_001", "DOC_REF_002"],
    },
    {
        "name": "architecture",
        "weight": 0.15,
        "checks": ["DOC_ARCH_001"],
    },
    {
        "name": "contributing",
        "weight": 0.25,
        "checks": ["DOC_CONTRIB_001", "DOC_CONTRIB_002"],
    },
    {
        "name": "maintenance",
        "weight": 0.15,
        "checks": ["DOC_MAINT_001"],
    },
]


# ─── Finding Data Class ────────────────────────────────────────────────────────

@dataclass
class DocumentationFinding:
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


# ─── Documentation Scanner ───────────────────────────────────────────────────

class DocumentationScanner:
    """
    Documentation perspective scanner implementation.

    This scanner:
    1. Fast pass: regex + directory-based checks for file existence and content
    2. Deep pass: LLM-based evaluation for nuanced documentation quality
    3. Aggregates results into a ScanResult dict
    """

    PERSPECTIVE_NAME = "documentation"
    PERSPECTIVE_VERSION = "1.0"
    SCANNER_VERSION = "1.0.0"

    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self.evaluator = LLMEvaluator(llm_config or LLMConfig.from_env())
        self.findings: list[DocumentationFinding] = []
        self.dimension_results: dict = {}

    def scan(self, context) -> dict:
        """
        Execute the documentation perspective scan.

        Args:
            context: ScanContext with repo_path, project_type, tech_stack, etc.

        Returns:
            ScanResult dict matching scoring-algorithm.md schema
        """
        start_time = time.time()
        repo_path = Path(context.repo_path)
        all_findings: list[DocumentationFinding] = []

        # 1. Fast scan: regex + directory checks
        fast_findings = self._fast_scan(repo_path)
        all_findings.extend(fast_findings)

        # 2. Deep scan: LLM-based evaluation for nuanced checks
        deep_findings = self._deep_scan(repo_path, context)
        all_findings.extend(deep_findings)

        # 3. Compute dimension scores
        dimension_scores = self._compute_dimension_scores(all_findings)

        # 4. Compute overall score
        overall_score = sum(
            score * next(d["weight"] for d in DOCUMENTATION_DIMENSIONS if d["name"] == dim_name)
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
                    "weight": next(d["weight"] for d in DOCUMENTATION_DIMENSIONS if d["name"] == dim_name),
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
                "total_checks": len(DOCUMENTATION_CHECKS),
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

    # ─── Fast Scan (regex + directory-based) ─────────────────────────────────

    def _fast_scan(self, repo_path: Path) -> list[DocumentationFinding]:
        """
        Fast scan using regex patterns and directory structure checks.
        Returns findings for missing or clearly-deficient documentation.
        """
        findings = []

        for check_key, check_def in DOCUMENTATION_CHECKS.items():
            for file_type in check_def["file_types"]:
                # Special handling for directories (docs/)
                if file_type.endswith("/"):
                    dir_path = repo_path / file_type.rstrip("/")
                    if dir_path.exists() and dir_path.is_dir():
                        # Directory exists — check if it has content
                        files = list(dir_path.rglob("*"))
                        if files:
                            findings.append(self._make_passing_finding(check_def, file_type, repo_path))
                        else:
                            findings.append(self._make_failing_finding(
                                check_def, file_type, repo_path,
                                evidence=f"Directory {file_type} exists but is empty"
                            ))
                    else:
                        findings.append(self._make_failing_finding(
                            check_def, file_type, repo_path,
                            evidence=f"Directory {file_type} does not exist"
                        ))
                else:
                    # Single file check
                    file_path = repo_path / file_type
                    if file_path.exists():
                        # File exists — run regex patterns against it
                        file_findings = self._check_file_patterns(
                            file_path, check_def, repo_path
                        )
                        findings.extend(file_findings)
                    else:
                        findings.append(self._make_failing_finding(
                            check_def, file_type, repo_path,
                            evidence=f"File {file_type} not found"
                        ))

        return findings

    def _check_file_patterns(
        self, file_path: Path, check_def: dict, repo_path: Path
    ) -> list[DocumentationFinding]:
        """Check a documentation file against its patterns."""
        findings = []
        if self._should_skip(file_path):
            return findings

        try:
            content = file_path.read_text(errors="ignore", encoding="utf-8")
        except Exception:
            return findings

        patterns = check_def.get("patterns", [])
        dimension = check_def["dimension"]

        if not patterns:
            # No patterns → existence is enough (already handled above)
            return []

        # Check for quick start step count (DOC_ONB_001)
        if check_def["id"] == "DOC_ONB_001":
            step_count = self._count_quickstart_steps(content)
            if step_count > 5:
                findings.append(DocumentationFinding(
                    check_id=check_def["id"],
                    dimension=dimension,
                    description=check_def["description"],
                    severity=check_def["severity"],
                    file_path=str(file_path.relative_to(repo_path)),
                    line=0,
                    matched_text=f"Quick start has {step_count} steps (expected ≤5)",
                    fix_action=check_def.get("fix_action", ""),
                    auto_actionable=check_def.get("auto_actionable", False),
                    confidence=0.90,
                    is_llm=False,
                ))
            elif step_count > 0:
                # Steps found, within limit — this check passes
                pass
            else:
                # No clear steps found
                findings.append(DocumentationFinding(
                    check_id=check_def["id"],
                    dimension=dimension,
                    description=check_def["description"],
                    severity=check_def["severity"],
                    file_path=str(file_path.relative_to(repo_path)),
                    line=0,
                    matched_text="No numbered quick start steps found",
                    fix_action=check_def.get("fix_action", ""),
                    auto_actionable=check_def.get("auto_actionable", False),
                    confidence=0.60,
                    is_llm=False,
                ))

        # Check for changelog recency (DOC_MAINT_001)
        elif check_def["id"] == "DOC_MAINT_001":
            is_recent, last_date = self._check_changelog_recent(content)
            if not is_recent:
                findings.append(DocumentationFinding(
                    check_id=check_def["id"],
                    dimension=dimension,
                    description=check_def["description"],
                    severity=check_def["severity"],
                    file_path=str(file_path.relative_to(repo_path)),
                    line=0,
                    matched_text=f"Changelog last updated: {last_date or 'unknown'} (may be stale)",
                    fix_action=check_def.get("fix_action", ""),
                    auto_actionable=check_def.get("auto_actionable", False),
                    confidence=0.70,
                    is_llm=False,
                ))

        # Generic pattern matching for other checks
        else:
            any_match = False
            for pattern in patterns:
                matches = list(re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE))
                if matches:
                    any_match = True
                    break

            if not any_match:
                findings.append(DocumentationFinding(
                    check_id=check_def["id"],
                    dimension=dimension,
                    description=check_def["description"],
                    severity=check_def["severity"],
                    file_path=str(file_path.relative_to(repo_path)),
                    line=0,
                    matched_text=f"No documentation matching patterns for {check_def['id']}",
                    fix_action=check_def.get("fix_action", ""),
                    auto_actionable=check_def.get("auto_actionable", False),
                    confidence=0.80,
                    is_llm=False,
                ))

        return findings

    def _count_quickstart_steps(self, content: str) -> int:
        """Count numbered steps in a quick start section."""
        # Match lines that start with a number and a period (1. 2. 3. ...)
        steps = re.findall(r'(?m)^\s*\d+\.\s+\S', content)
        return len(steps)

    def _check_changelog_recent(self, content: str) -> tuple[bool, Optional[str]]:
        """
        Check if changelog has been updated recently (within 6 months).
        Returns (is_recent, last_date_string).
        """
        import datetime, re

        # Try to find a date in ISO format or common formats
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',
            r'\d{4}/\d{2}/\d{2}',
            r'\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}',
        ]

        last_date = None
        for pattern in date_patterns:
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            if matches:
                # Use the first (most recent in well-formatted changelogs)
                last_date = matches[0].group()

        if not last_date:
            return True, None  # Can't determine, assume OK

        # Parse date if possible
        try:
            for fmt in ['%Y-%m-%d', '%Y/%m/%d']:
                try:
                    parsed = datetime.datetime.strptime(last_date, fmt)
                    age = (datetime.datetime.now() - parsed).days
                    return age < 180, last_date  # 6 months
                except ValueError:
                    continue
        except Exception:
            pass

        return True, last_date

    def _make_failing_finding(
        self, check_def: dict, file_type: str, repo_path: Path, evidence: str
    ) -> DocumentationFinding:
        return DocumentationFinding(
            check_id=check_def["id"],
            dimension=check_def["dimension"],
            description=check_def["description"],
            severity=check_def["severity"],
            file_path=file_type,
            line=0,
            matched_text=evidence,
            fix_action=check_def.get("fix_action", ""),
            auto_actionable=check_def.get("auto_actionable", False),
            confidence=0.95,
            is_llm=False,
        )

    def _make_passing_finding(
        self, check_def: dict, file_type: str, repo_path: Path
    ) -> DocumentationFinding:
        """Return a neutral finding indicating the doc exists (for directory checks)."""
        return DocumentationFinding(
            check_id=check_def["id"],
            dimension=check_def["dimension"],
            description=check_def["description"],
            severity=check_def["severity"],
            file_path=file_type,
            line=0,
            matched_text=f"{file_type} exists",
            fix_action="",
            auto_actionable=False,
            confidence=0.90,
            is_llm=False,
        )

    # ─── Deep Scan (LLM-based) ───────────────────────────────────────────────

    def _deep_scan(self, repo_path: Path, context) -> list[DocumentationFinding]:
        """
        LLM-based evaluation for nuanced documentation quality checks
        that require reading and understanding full content.
        """
        findings = []

        # LLM-based checks: DOC_REF_001 (README examples), DOC_REF_002 (API completeness),
        # DOC_ARCH_001 (architecture quality), DOC_CONTRIB_001/002 (contribution quality)
        llm_checks = [
            "DOC_REF_001",   # README working examples (needs LLM to judge quality)
            "DOC_REF_002",   # API reference completeness
            "DOC_ARCH_001",  # Architecture quality
            "DOC_CONTRIB_001",  # Contribution guidelines quality
            "DOC_CONTRIB_002",  # Coding standards + PR template quality
        ]

        # Find doc files to evaluate
        doc_files = self._find_doc_files(repo_path)

        for check_key, check_def in DOCUMENTATION_CHECKS.items():
            if check_def["id"] not in llm_checks:
                continue

            for file_path, content in doc_files.items():
                eval_context = EvaluationContext(
                    perspective=self.PERSPECTIVE_NAME,
                    dimension=check_def["dimension"],
                    check_id=check_def["id"],
                    file_path=file_path,
                    code_snippet=content[:3000],  # limit to first 3000 chars
                    perspective_doc=self._get_perspective_doc(),
                    project_type=getattr(context, "project_type", "generic"),
                    tech_stack=getattr(context, "tech_stack", "python"),
                    previous_decisions=getattr(
                        context, "learnings", {}
                    ).get("decisions", []),
                )

                result = self.evaluator.evaluate(eval_context)

                if result.status in ("fail", "warning"):
                    findings.append(DocumentationFinding(
                        check_id=check_def["id"],
                        dimension=result.dimension or check_def["dimension"],
                        description=check_def["description"],
                        severity=check_def["severity"],
                        file_path=file_path,
                        line=0,
                        matched_text="",
                        fix_action=result.fix_action or check_def.get("fix_action", ""),
                        auto_actionable=check_def.get("auto_actionable", False),
                        confidence=result.confidence,
                        is_llm=True,
                        reasoning=result.reasoning,
                    ))

        return findings

    def _find_doc_files(self, repo_path: Path) -> dict:
        """Find all relevant documentation files and return {rel_path: content}."""
        doc_files = {}
        doc_patterns = [
            "README.md", "README.rst", "README.txt",
            "CONTRIBUTING.md", "CONTRIBUTING.rst",
            "CHANGELOG.md", "HISTORY.md", "RELEASES.md",
            "ARCHITECTURE.md", "ARCH.md", "DESIGN.md",
            "API.md", "REFERENCE.md",
            "docs/api.md", "docs/reference.md", "docs/architecture.md",
            "INSTALL.md", "SETUP.md", "docs/installation.md",
        ]

        for pattern in doc_patterns:
            file_path = repo_path / pattern
            if file_path.exists() and file_path.is_file():
                try:
                    content = file_path.read_text(errors="ignore", encoding="utf-8")
                    rel_path = str(file_path.relative_to(repo_path))
                    doc_files[rel_path] = content
                except Exception:
                    pass

        # Also scan docs/ directory for additional files
        docs_dir = repo_path / "docs"
        if docs_dir.exists() and docs_dir.is_dir():
            for md_file in docs_dir.rglob("*.md"):
                try:
                    content = md_file.read_text(errors="ignore", encoding="utf-8")
                    rel_path = str(md_file.relative_to(repo_path))
                    if rel_path not in doc_files:
                        doc_files[rel_path] = content
                except Exception:
                    pass

        return doc_files

    # ─── Score Computation ───────────────────────────────────────────────────

    def _compute_dimension_scores(
        self, findings: list[DocumentationFinding]
    ) -> dict:
        """Compute score per dimension. Documentation is scored positively: more/better docs = higher score."""
        dim_docs_found: dict = {d["name"]: [] for d in DOCUMENTATION_DIMENSIONS}
        dim_required: dict = {d["name"]: len(d["checks"]) for d in DOCUMENTATION_DIMENSIONS}

        for f in findings:
            if f.is_llm:
                # LLM findings are higher confidence
                dim_docs_found[f.dimension].append((f.check_id, f.confidence))
            else:
                dim_docs_found[f.dimension].append((f.check_id, f.confidence))

        scores = {}
        for dim in DOCUMENTATION_DIMENSIONS:
            dim_name = dim["name"]
            total_required = dim_required[dim_name]
            checks_found = dim_docs_found.get(dim_name, [])

            # Compute pass rate based on checks with confidence weighting
            if total_required == 0:
                scores[dim_name] = 100.0
                continue

            # For documentation, we score based on whether docs exist (not whether they fail)
            # If a finding says "file not found", that's a fail (0)
            # If a finding says "examples found", that's a pass (100)
            # We invert: failing findings lower score, passing findings don't
            severity_map = {"critical": 0.0, "high": 25.0, "medium": 50.0, "low": 75.0}

            total_deduction = 0.0
            for check_id, conf in checks_found:
                check_def = next(
                    (v for v in DOCUMENTATION_CHECKS.values() if v["id"] == check_id), {}
                )
                if not check_def:
                    continue
                # If file is missing, that's a complete fail
                evidence_text = ""
                for f in findings:
                    if f.check_id == check_id:
                        evidence_text = " ".join(f.matched_text for f in findings if f.check_id == check_id)
                        break

                if "not found" in evidence_text.lower() or "does not exist" in evidence_text.lower():
                    deduction = severity_map.get(check_def.get("severity", "medium"), 50.0)
                elif "exists" in evidence_text.lower():
                    deduction = 0.0  # doc exists, no deduction
                else:
                    # Pattern match failure — partial deduction
                    deduction = severity_map.get(check_def.get("severity", "medium"), 50.0) * (1.0 - conf)

                total_deduction += deduction

            scores[dim_name] = max(0.0, 100.0 - total_deduction)

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
        self, dim_name: str, findings: list[DocumentationFinding]
    ) -> list[dict]:
        check_ids = next(
            (d["checks"] for d in DOCUMENTATION_DIMENSIONS if d["name"] == dim_name), []
        )
        dim_findings = [f for f in findings if f.check_id in check_ids]
        return [
            {
                "id": f.check_id,
                "status": "fail" if f.matched_text and ("not found" in f.matched_text.lower() or "missing" in f.matched_text.lower()) else "pass",
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
            ".parcel-cache", ".cache",
        }
        return any(part in path.parts for part in skip_dirs)

    def _get_perspective_doc(self) -> str:
        """
        Return the documentation perspective standard text for LLM context.
        """
        possible_paths = [
            Path("/tmp/auto-evolve/references/documentation/documentation-perspective.md"),
            Path(__file__).parent.parent.parent / "references" / "documentation" / "documentation-perspective.md",
        ]

        for p in possible_paths:
            if p.exists():
                try:
                    return p.read_text(encoding="utf-8")
                except Exception:
                    pass

        # Fallback embedded perspective doc
        return """Documentation Perspective Standard:

DOC_ONB_001: Quick start guide completes in ≤5 steps (Medium, No)
  → README should have a numbered quick start section achievable in ≤5 steps
DOC_ONB_002: Prerequisites are clearly stated (Medium, No)
  → Required runtime versions, external services, env vars, and accounts must be listed
DOC_REF_001: README has working code examples (High, No)
  → At least one runnable example demonstrating primary use case
DOC_REF_002: API reference is complete and up-to-date (High, No)
  → All endpoints/methods documented with request/response examples
DOC_ARCH_001: Architecture document exists and describes system design (Medium, No)
  → System components, responsibilities, and data flow described
DOC_CONTRIB_001: CONTRIBUTING.md exists with contribution guidelines (High, No)
  → How to submit changes, review process, conventions
DOC_CONTRIB_002: Coding standards and PR template provided (Medium, No)
  → Style guide / linter config + PR template
DOC_MAINT_001: Changelog maintained with recent entries (Low, No)
  → CHANGELOG updated within last 6 months
"""

    def _iso_now(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def get_dimensions(self) -> list:
        """Return dimension definitions."""
        return DOCUMENTATION_DIMENSIONS


# ─── Smoke Test ───────────────────────────────────────────────────────────────

def smoke_test():
    """Test the DocumentationScanner initialization."""
    import os

    config = LLMConfig(
        model=os.environ.get("LLM_MODEL", "gpt-4"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )

    scanner = DocumentationScanner(llm_config=config)

    class MockContext:
        repo_path = "/tmp/test-repo"
        project_type = "backend"
        tech_stack = "python"
        learnings = {"decisions": []}

    print("DocumentationScanner initialized. Ready to scan.")
    print(f"Perspective: {scanner.PERSPECTIVE_NAME}")
    print(f"Checks: {len(DOCUMENTATION_CHECKS)}")
    print(f"Dimensions: {len(DOCUMENTATION_DIMENSIONS)}")


if __name__ == "__main__":
    smoke_test()

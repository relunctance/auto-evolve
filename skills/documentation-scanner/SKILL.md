# Documentation Scanner Skill

## Purpose
Documentation perspective scanner implementation for auto-evolve.

Evaluates a repository's documentation quality across 5 dimensions:
- **Onboarding** (20%): Quick start guide + prerequisites
- **Reference** (25%): API reference completeness + code examples
- **Architecture** (15%): Architecture document existence + quality
- **Contributing** (25%): CONTRIBUTING guidelines + PR template + coding standards
- **Maintenance** (15%): Changelog recency

## Checks Implemented (8 total)

| Check ID | Description | Severity | Auto-Actionable |
|---|---|---|---|
| DOC_ONB_001 | Quick start guide completes in ≤5 steps | Medium | No |
| DOC_ONB_002 | Prerequisites are clearly stated | Medium | No |
| DOC_REF_001 | README has working code examples | High | No |
| DOC_REF_002 | API reference is complete and up-to-date | High | No |
| DOC_ARCH_001 | Architecture document exists and describes system design | Medium | No |
| DOC_CONTRIB_001 | CONTRIBUTING.md exists with contribution guidelines | High | No |
| DOC_CONTRIB_002 | Coding standards and PR template provided | Medium | No |
| DOC_MAINT_001 | Changelog maintained with recent entries | Low | No |

## Structure
```
documentation-scanner/
├── scanner.py              ← Main DocumentationScanner class
├── test_scanner.py         ← Contract + integration tests
└── SKILL.md
```

## Usage
```python
from documentation_scanner import DocumentationScanner
scanner = DocumentationScanner()
result = scanner.scan(context)
```

## Fast Scan Approach
- Check if `README.md` exists → DOC_ONB_001/002, DOC_REF_001
- Check for `docs/`, `docs/api.md`, `docs/reference.md` → DOC_REF_002
- Check for `ARCHITECTURE.md` or `docs/architecture.md` → DOC_ARCH_001
- Check for `CONTRIBUTING.md` → DOC_CONTRIB_001/002
- Check for `CHANGELOG.md` and recent entries → DOC_MAINT_001

## Deep Scan (LLM)
- DOC_REF_001: Evaluates README code example quality
- DOC_REF_002: Evaluates API reference completeness
- DOC_ARCH_001: Evaluates architecture document quality
- DOC_CONTRIB_001: Evaluates contribution guideline quality
- DOC_CONTRIB_002: Evaluates PR template and coding standards presence

## Depends On
- `scanner-contract/llm_evaluator.py` for LLM-powered evaluation
- `references/documentation/documentation-perspective.md` for perspective standard

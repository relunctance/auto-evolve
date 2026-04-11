# Report Generator Skill

## Purpose
Multi-format report generation for scan results.

## Structure
```
report-generator/
├── report_generator.py  ← ReportGenerator class
├── __init__.py
└── SKILL.md
```

## Usage
```python
from report_generator import ReportGenerator, Format
generator = ReportGenerator()
report = generator.generate(results, score, meta, Format.MARKDOWN)
```

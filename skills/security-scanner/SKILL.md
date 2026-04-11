# Security Scanner Skill

## Purpose
Security perspective scanner implementation for auto-evolve.

## Structure
```
security-scanner/
├── scanner.py       ← Main SecurityScanner class
├── checks.py       ← Security check definitions
├── test_scanner.py ← Contract tests
└── SKILL.md
```

## Usage
```python
from security_scanner import SecurityScanner
scanner = SecurityScanner()
result = scanner.scan(context)
```

## Depends On
- `scanner-contract/llm_evaluator.py` for LLM-powered evaluation

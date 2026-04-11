# Scanner Contract Skill

## Purpose
Shared scanner infrastructure: LLM evaluator, base classes, interfaces.

## Structure
```
scanner-contract/
├── llm_evaluator.py  ← LLM API client + EvaluationEngine
├── __init__.py
└── SKILL.md
```

## Usage
```python
from scanner_contract import LLMEvaluator, EvaluationContext
```

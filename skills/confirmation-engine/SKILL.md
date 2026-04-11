# Confirmation Engine Skill

## Purpose
Handles user interaction and decision storage for auto-evolve.

## What It Does

1. **Config Loading** — Reads `perspective-config.yaml` to determine which perspectives are active
2. **Tier Classification** — Determines which findings need user confirmation
3. **Decision Replay** — Applies stored decisions for similar past findings
4. **User Interaction** — Asks users for confirmation via Feishu/terminal
5. **Learnings Storage** — Records decisions for future pattern replay

## Interaction Tiers

| Tier | Condition | Behavior |
|------|-----------|---------|
| 1 | Critical severity or not auto-actionable | 🚫 Must ask |
| 2 | High severity or confidence < 70% | ⚠️ Ask if ambiguous |
| 3 | Other | ℹ️ Inform only |

## Quick Reply Mapping

```
1 = confirmed (执行)
2 = modified (修改后执行)
3 = skipped (跳过)
4 = ignored (永久忽略)
5 = escalated (升级讨论)
```

## Usage

```python
from confirmation_engine import ConfirmationEngine

engine = ConfirmationEngine(repo_path)

# Get active perspectives
active = engine.get_active_perspectives()

# Filter findings needing confirmation
pending = engine.filter_findings_requiring_confirmation(all_findings)

# Group similar findings for batch confirmation
groups = engine.group_by_pattern(pending)

# Process user response
decision = engine.process_user_response(finding, "1")  # Confirm
```

## Files

```
confirmation-engine/
├── confirmation_engine.py  ← Main engine
├── __init__.py
└── SKILL.md
```

## Depends On

- Feishu API (for sending confirmation cards)
- `.auto-evolve/learnings/` directory (for storing decisions)

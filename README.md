# Auto-Evolve

**Self-improvement engine for AI agents — continuously asks from the master's perspective: "what's missing, what can be optimized, and how's the user experience?" then acts.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://img.shields.io/badge/Python-3.10+-blue.svg)

> Auto-Evolve v3.5 asks from the **master's perspective**, leverages LLM intelligence with **persona-aware memory context**, and evolves your tools with or without human oversight.

**中文文档**: [README.zh-CN.md](README.zh-CN.md)

---

## The Core Shift

**Old version asked:** "Does this code have duplicates? Is this function over 100 lines?"
**v3.5 asks:** "What's missing? What can be optimized? How's the user experience?"

This is not a code quality scanner — it's a **continuous improvement partner from the master's perspective**.

---

## Key Features

### 🎯 Asks from Master's Perspective

Every scan carries this context:

- **Master's context**: SOUL.md, USER.md, IDENTITY.md — values, preferences, project role
- **Master's preferences**: recalled from OpenClaw SQLite memory + hawk-bridge LanceDB
- **Learning history**: previously rejected/approved changes to avoid repeating mistakes

```
"What's missing, what can be optimized, how's the user experience?"

Master's context: pursues automation, prefers concise and direct...
Master's preferences: master dislikes auto-generating test files...
Learning history: master rejected missing_test changes 3 times...
```

### 🧠 Persona-Aware Memory System

| Source | Priority | Description |
|--------|----------|-------------|
| OpenClaw SQLite | Primary | `memory/{persona}.sqlite`, structured, reliable |
| hawk-bridge LanceDB | Supplement | Vector semantic search, persona-isolated |

```bash
# Default: scan with current agent persona
python3 scripts/auto-evolve.py scan --dry-run

# Tang Sanzang recalls master's memories
python3 scripts/auto-evolve.py scan --dry-run --recall-persona master

# Force OpenClaw SQLite only
python3 scripts/auto-evolve.py scan --dry-run --memory-source openclaw

# Merge both sources
python3 scripts/auto-evolve.py scan --dry-run --memory-source both
```

### 📊 Real Product Insights (Not Just Code Problems)

Example output:
```
🎯 Product Evolution Insights (from 4 finding(s)):

  1. 🚫 [STOP_DOING]
     missing_test optimization rejected by master 3 times
     Impact: ████████░░ 0.8
     → Stop auto-generating test files
     ⏱ Every generation was rejected, wasting LLM calls
     File: auto-evolve config

  2. 😤 [USER_COMPLAINT]
     This feature is too cumbersome, master has to do 3 steps manually
     Impact: █████░░░░░ 0.5
     → Automate this workflow
     File: soul-force/scripts/soulforge.py
```

### ⚡ Real Quality Gates

Not just `py_compile` syntax check:
- Python: `pytest --cov` runs actual tests
- JavaScript/TypeScript: `jest` runs actual tests
- Failure triggers automatic rollback

### 🔍 Cross-File Structural Duplicate Detection

Not just identical strings — detects **structurally similar** functions:
- Similar functions across different files
- Repeated if/else blocks, try/catch patterns
- LLM proposes specific deduplication plans

---

## Quick Start

### Install

```bash
# Via ClawHub (recommended)
clawhub install auto-evolve

# Via Git
git clone https://github.com/relunctance/auto-evolve.git \
  ~/.openclaw/workspace/skills/auto-evolve
```

### Configure

```bash
# Add repository to scan
python3 scripts/auto-evolve.py repo-add ~/.openclaw/workspace/skills/soul-force \
  --type skill --monitor

# Set to full-auto mode
python3 scripts/auto-evolve.py set-mode full-auto

# Scan every 10 minutes
python3 scripts/auto-evolve.py schedule --every 10
```

### Run

```bash
# Scan + preview (no execution)
python3 scripts/auto-evolve.py scan --dry-run

# Scan + execute (in full-auto mode)
python3 scripts/auto-evolve.py scan

# Scan with master's memory recall
python3 scripts/auto-evolve.py scan --dry-run \
  --recall-persona master --memory-source both
```

---

## Architecture

```
Scan Triggered
    │
    ▼
┌──────────────────────────────────────────────┐
│  Step 1: Detect current persona              │
│  detect_persona() → main/tseng/wukong/...     │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│  Step 2: Determine workspace path            │
│  main → ~/.openclaw/workspace/                │
│  tseng → ~/.openclaw/workspace-tseng/        │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│  Step 3: Load master's context files         │
│  SOUL.md / USER.md / IDENTITY.md / MEMORY   │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│  Step 4: Recall memories (by persona)          │
│  OpenClaw SQLite (primary)                  │
│  + hawk-bridge LanceDB (supplement)         │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│  Step 5: LLM product-level analysis          │
│  "What's missing? What can be optimized?    │
│   How's the user experience?"               │
└──────────────────────────────────────────────┘
```

---

## Commands

| Command | Description |
|---------|-------------|
| `scan` | Scan (add `--dry-run` for preview) |
| `scan --recall-persona master` | Scan with master's memory |
| `scan --memory-source openclaw` | Specify memory source |
| `confirm` | Confirm and execute pending changes |
| `approve / reject` | Approve/reject with reason logged |
| `set-mode full-auto` | Full automation mode |
| `set-rules --low true` | Configure auto-execute rules |
| `schedule --every 60` | Set scan interval |
| `learnings` | View learning history |
| `rollback` | Rollback to previous version |
| `repo-add / repo-list` | Manage scan repositories |

---

## CLI Args

```
scan:
  --dry-run              Preview, no execution
  --recall-persona       Whose memory to recall (main/tseng/wukong/bajie/bailong/master)
  --memory-source        Memory source (auto/openclaw/hawkbridge/both)
```

---

## Safety

- **Quality gates**: Python `py_compile` + pytest; JS/TS jest
- **Rollback**: Every execution logs a git revert; one-command rollback
- **Privacy**: Closed repo code is redacted from reports
- **Learnings filter**: Changes rejected in learnings are not retried

---

## Related Projects

- [SoulForce](https://github.com/relunctance/soul-force) — AI agent memory evolution system
- [hawk-bridge](https://github.com/relunctance/hawk-bridge) — Context memory integration for OpenClaw

---

## License

MIT

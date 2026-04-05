# Auto-Evolve

**Self-improvement engine for AI agents — continuously scans projects and asks from the master's perspective: "what's missing, what can be optimized, and how's the user experience?" then acts.**

> Make your projects better — automatically. Auto-Evolve v3.5 asks from the **master's perspective**, leverages **persona-aware memory context**, and evolves your tools with or without human oversight.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://img.shields.io/badge/Python-3.10+-blue.svg)

**中文文档**: [README.zh-CN.md](README.zh-CN.md)

---

## What Is It?

Auto-Evolve is an **automated scanning engine running on OpenClaw**.

Every N minutes, it:
1. Scans configured projects (skills, norms, or projects)
2. Asks from the **master's perspective**: "what's missing, what can be optimized, how's the user experience?"
3. Combines master's context, preferences, and learning history to surface **real product improvement insights**
4. In `full-auto` mode: autonomously executes low-risk changes; in `semi-auto` mode: waits for confirmation

It is **not** a code quality scanner — it's a **continuous improvement partner** for your projects.

---

## Key Features

### 🎯 Asks from Master's Perspective

Not "does this code have issues?" — but with master's full context:

```
Master's context: pursues automation, dislikes manual steps...
Master's preferences: rejected auto-generating tests 3 times...
Learning history: approved TODO deletions 5 times...

"What's missing, what can be optimized, how's the user experience?"
```

### 🧠 Persona-Aware Memory

Recalls memories by persona (main/tseng/wukong/bajie/bailong):
- OpenClaw SQLite (`memory/{persona}.sqlite`)
- hawk-bridge LanceDB vector store
- `learnings/` decision history

### 📊 Product Insights + Code Optimizations

**Product insights** (LLM, master's perspective):
```
🎯 Product Evolution Insights:
  🚫 [STOP_DOING] missing_test rejected 3x → stop generating
  😤 [USER_COMPLAINT] workflow requires 3 manual steps
  📊 [COMPETITIVE_GAP] competitors have this feature we don't
```

**Code optimizations** (scanner):
```
🔧 Code Optimizations:
  🟢 duplicate_code: scripts/lua_def_file.py (3 occurrences)
  🟡 long_function: soulforge.py:127 lines > 100
  🟡 missing_test: 5 modules lack test coverage
```

### ⚡ Execution Modes

| Mode | Behavior |
|------|----------|
| `full-auto` | Low-risk → auto-execute; medium-risk → open PR; high-risk → skip |
| `semi-auto` | All changes wait for human confirmation |

### 🔒 Safety

- **Quality gates**: syntax check + pytest/jest actual tests
- **git revert rollback**: one-command rollback
- **Learnings filter**: rejected changes not retried
- **Privacy**: closed repo code is redacted

---

## Quick Start

```bash
# Install
clawhub install auto-evolve

# Add project to scan
python3 scripts/auto-evolve.py repo-add ~/.openclaw/workspace/skills/soul-force --type skill --monitor

# Full-auto scan
python3 scripts/auto-evolve.py scan

# Preview mode (no execution)
python3 scripts/auto-evolve.py scan --dry-run

# Scan with master's memory recall
python3 scripts/auto-evolve.py scan --dry-run --recall-persona master --memory-source both

# Auto-scan every 10 minutes
python3 scripts/auto-evolve.py schedule --every 10
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                 Auto-Evolve Scanning Engine                   │
│                                                              │
│  Cron trigger (every N minutes)                             │
│        │                                                     │
│        ▼                                                     │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Persona Detection + Workspace Resolution            │   │
│  └────────────────────┬───────────────────────────────┘   │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Memory Recall (by persona)                         │   │
│  │  OpenClaw SQLite (primary)                        │   │
│  │  + hawk-bridge LanceDB (supplement)                │   │
│  │  + learnings history                               │   │
│  └────────────────────┬───────────────────────────────┘   │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐   │
│  │  LLM Product-Level Analysis (master's perspective)  │   │
│  │  "What's missing? What can be optimized?          │   │
│  │   How's the user experience?"                       │   │
│  └────────────────────┬───────────────────────────────┘   │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Code Scanning (parallel)                           │   │
│  │  Duplicates / Long Functions / TODOs / Tests        │   │
│  └────────────────────┬───────────────────────────────┘   │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Priority + Quality Gates                           │   │
│  │  full-auto: low-risk → auto-execute               │   │
│  │  full-auto: medium-risk → open PR                  │   │
│  │  semi-auto: all → wait for confirmation            │   │
│  └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## Commands

| Command | Description |
|---------|-------------|
| `scan` | Scan projects |
| `scan --dry-run` | Preview, no execution |
| `scan --recall-persona master` | Scan with master's memory |
| `scan --memory-source openclaw` | Specify memory source |
| `confirm` | Confirm and execute pending changes |
| `approve / reject` | Approve/reject with reason logged |
| `set-mode full-auto` | Full automation mode |
| `set-rules --low true` | Configure auto-execute rules |
| `schedule --every 10` | Scan every 10 minutes |
| `learnings` | View learning history |
| `rollback` | Rollback to previous version |

---

## Current Capabilities

**Can auto-execute (low-risk):**
- ✅ Delete empty TODO/FIXME comments
- ✅ Eliminate simple string duplicates
- ✅ Convert pinned versions to semver ranges
- ✅ Fix minor formatting issues

**Needs confirmation (medium-risk):**
- ⚠️ Refactor function structure
- ⚠️ Cross-file changes
- ⚠️ Modify business logic

**Cannot yet do:**
- ❌ Complex multi-file refactoring
- ❌ Business-semantics-aware changes
- ❌ Changes without test coverage

---

## Improvement Roadmap

| Priority | Item | Description |
|----------|------|-------------|
| 🔴 Highest | LLM code generation reliability | Currently ~40% returns prose instead of code; needs prompt engineering fix |
| 🔴 Highest | Learnings data accumulation | learnings is always empty; needs real iteration runs to accumulate data |
| 🟡 High | Metric trend tracking | Record per-iteration metrics (TODOs, duplication rate, test coverage) and draw trend charts |
| 🟡 High | GitHub Issue proactive creation | Auto-open Issue when product-level problem is found |
| 🟡 High | Proactive notifications | Push scan results to Feishu/email instead of waiting for Cron |
| 🟢 Medium | Dynamic Cron adjustment | Adjust scan frequency based on project activity |
| 🟢 Medium | Multi-agent team support | Each agent (Tang Sanzang/Wukong/etc.) scans their own projects |

---

## Related Projects

- [SoulForce](https://github.com/relunctance/soul-force) — AI agent memory evolution system
- [hawk-bridge](https://github.com/relunctance/hawk-bridge) — Context memory integration for OpenClaw

---

## License

MIT

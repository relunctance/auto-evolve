# Auto-Evolve

**Self-improvement engine for AI agents — continuously ask "can I be better?", then act.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/relunctance/auto-evolve)](https://github.com/relunctance/auto-evolve/stargazers)

> Your skills get smarter — automatically. Auto-Evolve scans your code, leverages LLM intelligence to suggest improvements, and evolves your tools with or without human oversight.

**中文文档**：[README.zh-CN.md](README.zh-CN.md)

---

## Why Auto-Evolve?

**The core problem: AI agents never ask themselves "can I be better?"**

Current AI agents:
- Execute tasks but don't reflect on their own shortcomings
- Make the same mistakes repeatedly
- Never主动发现自己的可优化之处
- Stay static after deployment

**Auto-Evolve is the self-improvement engine for AI agents.**

It gives AI the ability to:
- **Self-question**: "Is there anything I could do better?"
- **Self-discover**: Find optimization opportunities in code, docs, patterns
- **Self-improve**: Execute improvements autonomously or semi-autonomously
- **Self-learn**: Remember what was approved/rejected and get smarter

The result: AI that gets genuinely smarter over time, not just longer-lived.

---

## Features

### 🔍 Intelligent Scanning
- Detects TODO/FIXME/HACK/XXX annotations
- Finds duplicate code patterns
- Identifies overly long functions
- Checks for missing test coverage
- **LLM-powered analysis** for context-aware suggestions

### 🎯 Smart Prioritization
- Calculates priority score: `P = (value × 0.5) / (risk × cost)`
- Shows dependency impact before making changes
- Ranks suggestions by benefit-to-effort ratio

### ⚡ Two Operation Modes
- **Semi-auto**: Scans, suggests, waits for your confirmation
- **Full-auto**: Executes low-risk changes automatically per rules

### 🔒 Full Audit Trail
- Every iteration logged with manifest
- Before/after metrics comparison
- Rollback to any previous state
- Learning from your approvals and rejections

### 🌐 Branch + PR Workflow
- High-risk changes get their own branch
- GitHub PR with full context
- Auto-resolves conflicts when possible
- Batch similar changes into one PR

### 📊 Effect Tracking
- Measures: todos resolved, lint errors fixed, coverage delta
- Compares metrics between iterations
- Tracks auto vs. manual contribution ratio

---

## Quick Start

### Installation

**Option 1: Via ClawHub (recommended)**
```bash
# Install globally for all agents
clawhub install auto-evolve

# Or install to specific directory
clawhub install auto-evolve --dir ~/.openclaw/workspace/skills
```

**Option 2: Via Git**
```bash
# Clone the repo
git clone https://github.com/relunctance/auto-evolve.git ~/.openclaw/workspace/skills/auto-evolve

# Navigate to the skill directory
cd ~/.openclaw/workspace/skills/auto-evolve
```

**Option 3: Via GitHub releases**
```bash
# Download latest release from GitHub
# https://github.com/relunctance/auto-evolve/releases
```

### Post-Installation Setup

```bash
# Add repositories to monitor
python3 scripts/auto-evolve.py repo-add /path/to/your/project --type skill --monitor

# Set operation mode
python3 scripts/auto-evolve.py set-mode full-auto  # Full-auto mode
python3 scripts/auto-evolve.py set-mode semi-auto  # Semi-auto mode (confirm first)

# Set auto-execute rules (for full-auto mode)
python3 scripts/auto-evolve.py set-rules --low true --medium true

# Schedule periodic scans
python3 scripts/auto-evolve.py schedule --every 60  # Every 60 minutes
python3 scripts/auto-evolve.py schedule --every 720  # Every 12 hours
```

### Basic Usage

```bash
# Scan all configured repositories
python3 scripts/auto-evolve.py scan

# Preview without executing
python3 scripts/auto-evolve.py scan --dry-run

# In semi-auto mode: confirm pending changes
python3 scripts/auto-evolve.py confirm

# View iteration history
python3 scripts/auto-evolve.py log

# Rollback to a previous iteration
python3 scripts/auto-evolve.py rollback --to VERSION
```

---

## Configuration

Auto-Evolve uses `~/.auto-evolverc.json`:

```json
{
  "mode": "semi-auto",
  "repositories": [
    {
      "path": "~/.openclaw/workspace/skills/soul-force",
      "type": "skill",
      "visibility": "public",
      "auto_monitor": true
    },
    {
      "path": "~/projects/closed-project",
      "type": "project",
      "visibility": "closed",
      "auto_monitor": true,
      "risk_override": {
        "code_changes": "medium"
      }
    }
  ],
  "full_auto_rules": {
    "execute_low_risk": true,
    "execute_medium_risk": false,
    "execute_high_risk": false
  },
  "schedule_interval_hours": 168
}
```

### Adding Repositories

```bash
# Add a skill repository
python3 scripts/auto-evolve.py repo-add ~/my-skill --type skill --monitor

# Add a norms repository
python3 scripts/auto-evolve.py repo-add ~/team-norms --type norms --monitor

# List configured repositories
python3 scripts/auto-evolve.py repo-list
```

---

## Repository Types

| Type | Description | Default Risk |
|------|-------------|-------------|
| `skill` | OpenClaw skill | Low |
| `norms` | Team standards repository | Low |
| `project` | Open source project | Medium |
| `closed` | Private/closed project | Medium |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Auto-Evolve                          │
├─────────────────────────────────────────────────────────┤
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐  │
│  │  Scanner │──▶│ Analyzer │──▶│  Prioritizer     │  │
│  │  (git +  │   │ (LLM +   │   │  (P = v/r×c)   │  │
│  │   regex) │   │ patterns)│   │                  │  │
│  └──────────┘   └──────────┘   └──────────────────┘  │
│         │              │                  │            │
│         ▼              ▼                  ▼            │
│  ┌─────────────────────────────────────────────────┐  │
│  │              Executor                          │  │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────┐ │  │
│  │  │ Low Risk   │  │ Medium/    │  │ High Risk │ │  │
│  │  │ (direct)   │  │ High       │  │ (PR)     │ │  │
│  │  └────────────┘  └────────────┘  └──────────┘ │  │
│  └─────────────────────────────────────────────────┘  │
│                          │                            │
│                          ▼                            │
│  ┌─────────────────────────────────────────────────┐ │
│  │              Audit Trail                         │ │
│  │   catalog.json │ manifest.json │ metrics.json    │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Command Reference

| Command | Description |
|---------|-------------|
| `scan` | Scan and analyze repositories |
| `confirm` | Confirm and execute pending changes |
| `approve` | Approve specific change (with `--reason`) |
| `reject` | Reject a change with reason |
| `set-mode` | Switch semi-auto / full-auto |
| `set-rules` | Configure full-auto execution rules |
| `schedule` | Set up periodic scanning |
| `learnings` | View approval/rejection history |
| `rollback` | Revert to previous iteration |
| `repo-add` | Add repository to monitor |
| `repo-list` | List all repositories |
| `release` | Create GitHub release (v3+) |

Full command reference: [SKILL.md](SKILL.md)

---

## Privacy & Safety

### Privacy Levels

Repositories marked `visibility: "closed"` receive special treatment:
- Code content redacted in reports
- File paths replaced with content hashes
- No raw code in notifications

### Quality Gates

Every auto-executed change passes:
1. **Syntax check** — Python files must compile
2. **Git status** — No untracked sensitive files
3. **Documentation sync** — SKILL.md updated when needed

### Rollback

Every iteration is tracked. Rollback is a single command:

```bash
auto-evolve rollback --to v2.2.0
# or cherry-pick a single change
auto-evolve rollback --to v2.2.0 --item 3
```

---

## Contributing

Contributions are welcome! Please read our guidelines before submitting PRs.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes with clear messages
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## Related Projects

- [SoulForce](https://github.com/relunctance/soul-force) — AI agent memory evolution system
- [hawk-bridge](https://github.com/relunctance/hawk-bridge) — Context memory integration for OpenClaw

---

## License

MIT License — see [LICENSE](LICENSE) for details.

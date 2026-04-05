# Auto-Evolve v2

**Automated skill iteration manager with full audit trail.**

> Make your skills continuously better — automatically.

---

## Overview

Auto-Evolve v2 is a complete rewrite with multi-repository support, branch+PR workflows for high-risk changes, and proactive optimization discovery.

```
Scheduled Scan → Risk Classification → Auto-Execute (low) → Push
                                           ↓
                    Branch+PR (high) / Pending Review (medium)
                                           ↓
                              User approves via CLI
```

---

## Commands

### scan

Scans all configured repositories for changes and optimization opportunities.

```bash
# Full scan — auto-execute low-risk, flag medium/high
python3 auto-evolve.py scan

# Preview — show what would happen without committing
python3 auto-evolve.py scan --dry-run
```

**What it scans:**
- Git changes (added, modified, removed, untracked files)
- TODO/FIXME/XXX annotations
- Duplicate string patterns (3+ occurrences)
- Long functions (>100 lines)
- Missing test coverage
- Pinned/outdated dependencies

---

### approve

Approve and execute pending changes from the last scan (or a specific iteration).

```bash
# Approve all pending items
python3 auto-evolve.py approve --all

# Approve specific items by ID
python3 auto-evolve.py approve 1,3

# Approve items from a specific iteration
python3 auto-evolve.py approve --iteration 20260405-120000
```

---

### repo-add

Add a repository to the monitoring list.

```bash
python3 auto-evolve.py repo-add ~/.openclaw/workspace/skills/hawk-bridge --type skill
```

**Repository types:**
- `skill` — A skill directory (default)
- `norms` — Team norms/rules repository
- `project` — General project repository
- `closed` — Private/closed project (code changes default to medium risk)

---

### repo-list

List all configured repositories.

```bash
python3 auto-evolve.py repo-list
```

---

### rollback

Rollback changes from a previous iteration using `git revert`.

```bash
# Rollback with reason
python3 auto-evolve.py rollback --to 20260405-120000 --reason "broke feature X"

# Rollback (prompts for reason)
python3 auto-evolve.py rollback --to 20260405-120000
```

---

### log

View iteration history.

```bash
python3 auto-evolve.py log --limit 5
```

---

## Risk Classification

| Level | Trigger | Action |
|-------|---------|--------|
| 🟢 Low | Docs, README, comments, typo fixes, lint | **Auto-execute + push** |
| 🟡 Medium | New features, non-breaking additions, optimizations | **Flag for review** |
| 🔴 High | Breaking changes, deletions, architecture | **Branch + PR** |

### Per-Type Defaults

- `norms` repo: doc changes → low risk
- `closed` repo: code changes → medium risk
- `project` repo: test changes → medium risk

---

## Proactive Optimizations

Auto-Evolve v2 actively scans for improvement opportunities:

| Type | What it finds | Risk |
|------|---------------|------|
| `todo_fixme` | Unresolved TODO/FIXME/XXX/HACK/NOTE | Low |
| `duplicate_code` | Repeated string patterns (3x+) | Low |
| `long_function` | Functions >100 lines | Medium |
| `missing_test` | Modules without test coverage | Medium |
| `outdated_dep` | Pinned dependency versions | Low |

---

## Approval Workflow

1. Run `scan` → medium/high risk items → saved to `.iterations/{id}/pending-review.json`
2. Review the file directly, or run `approve --all` / `approve 1,2,3`
3. High-risk changes get their own branch + PR via `gh` CLI
4. Medium/low changes get committed directly and pushed

---

## Branch + PR Flow

For **high-risk** changes:
1. Creates branch: `auto-evolve/{description}`
2. Commits the change
3. Creates GitHub PR with change description and approval instructions
4. User merges PR manually after reviewing

For **low/medium** changes: direct commit to main + auto-push.

---

## Configuration

File: `~/.auto-evolverc.json`

```json
{
  "schedule_interval_hours": 168,
  "auto_execute_risk": ["low"],
  "notify_risk": ["medium", "high"],
  "repositories": [
    {
      "path": "~/.openclaw/workspace/skills/soul-force",
      "type": "skill",
      "visibility": "public",
      "auto_monitor": true
    }
  ],
  "notification": {
    "mode": "log",
    "log_file": "~/.auto-evolve-notifications.log"
  },
  "git": {
    "remote": "origin",
    "branch": "main",
    "pr_branch_prefix": "auto-evolve"
  }
}
```

### Per-Repository Options

```json
{
  "path": "~/path/to/repo",
  "type": "skill|norms|project|closed",
  "visibility": "public|closed",
  "auto_monitor": true,
  "risk_override": "low|medium|high"
}
```

---

## Iteration Record Format

```
.auto-evolve/
└── .iterations/
    └── {id}/
        ├── manifest.json        # Metadata + pending items
        ├── plan.md              # Plan with all changes
        ├── pending-review.json  # Items awaiting approval
        └── report.md            # Execution results
```

---

## Project Structure

```
auto-evolve/
├── SKILL.md
├── README.md
├── CHANGELOG.md
├── scripts/
│   └── auto-evolve.py     # Main CLI
└── references/
    ├── RISK-CLASSIFICATION.md
    ├── QUALITY-GATES.md
    └── NOTIFICATION-TEMPLATE.md
```

---

## Requirements

- Python 3.10+
- Git
- `gh` CLI (for PR creation)

---

## License

MIT

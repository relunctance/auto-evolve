# Auto-Evolve v2.1

**Automated skill iteration manager with full audit trail.**

> Make your skills continuously better — automatically.

---

## Overview

Auto-Evolve v2.1 is a complete rewrite with multi-repository support, branch+PR workflows for high-risk changes, proactive optimization discovery, and two operation modes (semi-auto and full-auto).

```
Scheduled Scan → Risk Classification → Learning Check → Mode Decision
                                                            │
                    ┌──────────────┴──────────────┐
                 Semi-Auto                      Full-Auto
                 (default)                       (per rules)
                    │                               │
              confirm to exec              execute_low_risk: true
              pending review               execute_medium_risk: false
              learnings track               execute_high_risk: false
```

---

## Operation Modes

### Semi-Auto (Default)

- Scan generates `pending-review.json`
- Auto low-risk changes are **held** until you run `confirm`
- No changes are pushed until confirmed
- Rejections are recorded in `.learnings/rejections.json`

### Full-Auto

- Low/medium/high risk executed **automatically** per rules
- No waiting for confirmation
- Still shows execution preview before running
- Learning history still tracks approvals

```
# Switch modes
auto-evolve.py set-mode semi-auto
auto-evolve.py set-mode full-auto

# Configure full-auto rules
auto-evolve.py set-rules --low true --medium false --high false
```

---

## Commands

### scan

Scans all configured repositories for changes and optimization opportunities.

```bash
# Full scan — respects current mode (semi-auto by default)
python3 auto-evolve.py scan

# Preview — show what would happen without committing
python3 auto-evolve.py scan --dry-run
```

**What it scans:**
- Git changes (added, modified, removed, untracked files)
- TODO/FIXME/XXX/HACK/NOTE annotations
- Duplicate string patterns (3+ occurrences)
- Long functions (>100 lines)
- Missing test coverage
- Pinned/outdated dependencies

**Output:**
- Iteration saved to `.iterations/{id}/`
- `pending-review.json` — pending items (sanitized for closed repos)
- `alert.json` — generated if quality gates fail

---

### confirm

Confirm and execute pending changes in semi-auto mode.

```bash
# Confirm all pending from most recent iteration
python3 auto-evolve.py confirm

# Confirm from specific iteration
python3 auto-evolve.py confirm --iteration 20260405-120000
```

---

### reject

Reject a pending change and record in learning history.

```bash
# Reject item 2
auto-evolve.py reject 2 --reason "too risky"

# Reject from specific iteration
auto-evolve.py reject 3 --reason "not needed" --iteration 20260405-120000
```

Rejections are stored in `.learnings/rejections.json` and prevent the same change from being re-recommended.

---

### approve

Approve and execute pending changes (direct execution, bypasses confirm workflow).

```bash
# Approve all pending items
auto-evolve.py approve --all

# Approve specific items by ID
auto-evolve.py approve 1,3

# Approve from a specific iteration
auto-evolve.py approve --all --iteration 20260405-120000
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
- `closed` — Private/closed project (code changes default to medium risk, content sanitized)

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
auto-evolve.py rollback --to 20260405-120000 --reason "broke feature X"
```

---

### schedule

Manage cron scheduling (outputs OpenClaw cron commands).

```bash
# Set scan interval (hours)
auto-evolve.py schedule --every 168   # every 168 hours (1 week)

# Show current setup
auto-evolve.py schedule --show

# Show removal instructions
auto-evolve.py schedule --remove
```

**Setup example:**
```bash
openclaw cron add --name auto-evolve-scan \
  --command 'python3 ~/.openclaw/workspace/skills/auto-evolve/scripts/auto-evolve.py scan' \
  --interval 168h
```

---

### learnings

View learning history (rejections and approvals).

```bash
# Show all learnings
auto-evolve.py learnings

# Show only rejections
auto-evolve.py learnings --type rejections

# Show only approvals
auto-evolve.py learnings --type approvals

# Limit output
auto-evolve.py learnings --limit 10
```

---

### log

View iteration history.

```bash
auto-evolve.py log --limit 5
```

---

## Risk Classification

| Level | Trigger | Action |
|-------|---------|--------|
| 🟢 Low | Docs, README, comments, typo fixes, lint | Auto-executable |
| 🟡 Medium | New features, non-breaking additions, optimizations | Pending review |
| 🔴 High | Breaking changes, deletions, architecture | Branch + PR |

### Per-Type Defaults

- `norms` repo: doc changes → low risk
- `closed` repo: code changes → medium risk (content redacted)
- `project` repo: test changes → medium risk

---

## Proactive Optimizations

| Type | What it finds | Risk |
|------|---------------|------|
| `todo_fixme` | Unresolved TODO/FIXME/XXX/HACK/NOTE | Low |
| `duplicate_code` | Repeated string patterns (3x+) | Low |
| `long_function` | Functions >100 lines | Medium |
| `missing_test` | Modules without test coverage | Medium |
| `outdated_dep` | Pinned dependency versions | Low |

---

## Learning History

Auto-Evolve tracks what you've approved and rejected:

```
.learnings/
├── rejections.json    # Changes you've rejected
└── approvals.json    # Changes you've approved
```

When scanning, rejected changes are skipped automatically. This prevents the same low-value or rejected optimization from being re-recommended.

---

## Closed Repository Privacy

For `visibility: "closed"` repositories:
- `pending-review.json` contains no file paths or code content
- File paths are replaced with `[REDACTED]`
- Content hash references used instead
- Log files do not contain change details

---

## Execution Preview

Before executing (even in full-auto mode), a preview is shown:

```
⚠️  Full-Auto Mode: About to execute 3 changes:
  [1] 🟢 LOW: todo-fix: Remove TODO in soulforge/analyzer.py (line 45)
  [2] 🟢 LOW: lint-fix: Format soulforge/evolver.py
  [3] 🟡 MEDIUM: add-test: Add test for new ask() function
```

---

## Quality Gates & Alerts

Quality gates check Python syntax before committing. If gates fail:
- An `alert.json` is generated in the iteration directory
- The iteration is flagged with `has_alert: true`
- The scan continues but reports the failure

```
.iterations/{id}/
├── manifest.json
├── alert.json     # Alert content (if quality gate failed)
├── plan.md
├── pending-review.json
└── report.md
```

---

## Configuration

File: `~/.auto-evolverc.json`

```json
{
  "mode": "semi-auto",
  "full_auto_rules": {
    "execute_low_risk": true,
    "execute_medium_risk": false,
    "execute_high_risk": false
  },
  "semi_auto_rules": {
    "notify_on_each_scan": true,
    "require_confirm_before_execute": true
  },
  "schedule_interval_hours": 168,
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

## Branch + PR Flow

For **high-risk** changes:
1. Creates branch: `auto-evolve/{description}`
2. Commits the change
3. Creates GitHub PR with `gh` CLI
4. User merges PR manually after reviewing

---

## Iteration Record Format

```
.auto-evolve/
└── .iterations/
    └── {id}/
        ├── manifest.json        # Metadata + pending items
        ├── plan.md              # Plan with all changes
        ├── pending-review.json  # Items awaiting review (sanitized for closed repos)
        ├── report.md            # Execution results
        └── alert.json           # Quality gate alert (if any)
```

---

## Requirements

- Python 3.10+
- Git
- `gh` CLI (for PR creation)

---

## License

MIT

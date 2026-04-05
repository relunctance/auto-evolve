# Auto-Evolve v3.0

**LLM-driven automated skill iteration manager with full audit trail.**

> Make your skills continuously better — automatically.

---

## Overview

Auto-Evolve v3.0 is a major upgrade with LLM-powered code analysis, dependency awareness, and multi-language support.

```
Scheduled Scan → LLM Analysis → Risk Classification → Learning Check → Mode Decision
                     ↓                                                      ↓
              🤖 LLM suggests              Semi-Auto                    Full-Auto
              optimizations &             (confirm to exec)             (execute per rules)
              refactoring hints
```

### v3.0 New Features

- **LLM-driven code analysis** — uses OpenClaw's configured LLM to analyze pending changes and suggest optimizations
- **Dependency awareness** — tracks which files import/depend on changed files before applying
- **Test comparison** — before/after test coverage delta when running tests at two git refs
- **Cherry-pick rollback** — `rollback --to VERSION --item ID` reverts only a specific item
- **Multi-language support** — Python, JavaScript, TypeScript, Go, Shell, Java
- **Release management** — `release --version 2.3.0` creates git tag + GitHub release via gh CLI
- **Contributor tracking** — shows auto-evolve vs manual commit ratio in `log` output

---

## Operation Modes

### Semi-Auto (Default)

- Scan generates `pending-review.json`
- Auto low-risk changes are **held** until you run `confirm`
- LLM analysis runs on top 5 pending items
- No changes are pushed until confirmed

### Full-Auto

- Low/medium/high risk executed **automatically** per rules
- Learning history tracks approvals

---

## Commands

### scan

Scans all configured repositories for changes and optimization opportunities.

```bash
# Full scan — respects current mode
python3 auto-evolve.py scan

# Preview — show what would happen without committing
python3 auto-evolve.py scan --dry-run
```

**v3.0: Language Detection**
Automatically detects repository languages and uses appropriate TODO patterns.

**v3.0: Dependency Analysis**
Before applying changes, scans import statements to report which files depend on changed files:
```
⚠️  Dependency Alert:
  Changing: soulforge/analyzer.py
  May affect: soulforge/evolver.py (imports analyzer)
```

**v3.0: LLM Analysis**
Top 5 pending items are analyzed by the configured LLM. Results show:
- LLM suggestion for each change
- Risk level adjustment if LLM disagrees
- Implementation hints

Output includes `🤖 LLM:` prefix for analyzed items.

**What it scans:**
- Git changes (added, modified, removed, untracked)
- TODO/FIXME/XXX/HACK/NOTE (multi-language patterns)
- Duplicate string patterns (3+ occurrences)
- Long functions (>100 lines) — Python, JS, TS, Go
- Missing test coverage
- Pinned/outdated dependencies

---

### confirm

Confirm and execute pending changes in semi-auto mode.

```bash
python3 auto-evolve.py confirm
python3 auto-evolve.py confirm --iteration 20260405-120000
```

---

### reject

Reject a pending change and record in learning history.

```bash
auto-evolve.py reject 2 --reason "too risky"
```

---

### approve

Approve and execute pending changes.

```bash
# Approve all with reason
auto-evolve.py approve --all --reason "valuable improvement"

# Approve specific items
auto-evolve.py approve 1,3

# From specific iteration
auto-evolve.py approve --all --iteration 20260405-120000
```

**v3.0: Dependency and LLM badges in approve prompt:**
```
  [1] 🟢 P=0.85 MEDIUM: add-test: Add test for ask() ⚠️2deps 🤖
```
Shows `⚠️Ndeps` when item affects N dependent files, `🤖` when LLM analyzed.

---

### repo-add

Add a repository to the monitoring list.

```bash
python3 auto-evolve.py repo-add ~/.openclaw/workspace/skills/hawk-bridge --type skill
```

**Repository types:** `skill` | `norms` | `project` | `closed`

---

### repo-list

List all configured repositories. v3.0 shows detected languages.

```bash
python3 auto-evolve.py repo-list
```

---

### rollback

**v3.0: Cherry-pick rollback — revert specific items without full revert.**

```bash
# Full rollback of an iteration
auto-evolve.py rollback --to 20260405-120000 --reason "broke feature X"

# Cherry-pick: only rollback item #3
auto-evolve.py rollback --to 20260405-120000 --item 3
```

Cherry-pick mode finds and reverts only the commit matching the specified item ID.

---

### release (v3.0)

Create a GitHub release with git tag + gh CLI.

```bash
# Basic release
auto-evolve.py release --version 2.3.0

# With changelog
auto-evolve.py release --version 2.3.0 --changelog "## What's New\n- Feature A\n- Feature B"
```

Flow:
1. Creates `v{version}` git tag
2. Pushes tag to `origin`
3. Creates GitHub release via `gh release create`
4. Uses auto-evolve release notes template

---

### schedule

```bash
# Set scan interval (creates cron automatically)
auto-evolve.py schedule --every 168   # every 168 hours (1 week)

# Show current schedule
auto-evolve.py schedule --show

# Remove cron job
auto-evolve.py schedule --remove
```

---

### learnings

View learning history.

```bash
auto-evolve.py learnings
auto-evolve.py learnings --type rejections
auto-evolve.py learnings --type approvals --limit 10
```

---

### log

**v3.0: Shows contributor stats and test coverage delta.**

```bash
auto-evolve.py log --limit 5
```

Example output:
```
📚 Iteration Log
═══════════════════════════════════════════════════════════

✅ 20260405-120000 📊 👥 8A/15M
   Date: 2026-04-05T12:00:00+08:00
   Status: completed
   Auto: 3 | Approved: 5
```

`👥 8A/15M` = 8 auto-evolve commits / 15 manual commits

---

## Priority Scoring

Changes ranked by **P = (value × 0.5) / (risk × cost)**

| Factor | Range | Meaning |
|--------|-------|---------|
| Value | 1-10 | Bug fix=10, test=7, docs=4 |
| Risk | 1-10 | Low=2, Medium=5, High=9 |
| Cost | 1-10 | 5min=1, 1h=7, 2h+=10 |

---

## LLM Integration (v3.0)

Auto-Evolve v3.0 uses OpenClaw's configured LLM — no separate API key needed.

### How it works

1. After scanning, top 5 pending (non-auto-exec) items sorted by priority
2. For each item, reads the file and sends to LLM with context
3. LLM returns: suggestion, risk_level, implementation_hint
4. If LLM suggests different risk level, priority is recalculated
5. LLM results stored in pending-review.json

### Config Priority

1. Environment variables: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
2. Fallback: `MINIMAX_API_KEY`, `MINIMAX_BASE_URL`
3. `openclaw config get llm` as last resort

### Example LLM output

```
🤖 LLM: This function could be simplified by extracting the validation logic
```

---

## Dependency Analysis (v3.0)

When git changes are detected, auto-evolve:
1. Scans all files for `import`/`require`/`from` statements
2. Builds a dependency map
3. For each changed file, finds files that import it
4. Shows warnings before applying changes that affect dependents

### Supported Languages

| Language | Import Syntax |
|----------|---------------|
| Python | `import X`, `from X import Y` |
| JavaScript/TypeScript | `require('X')`, `import from 'X'` |
| Go | `import "X"` |
| Java | `import X.Y.Z;` |

---

## Multi-Language TODO Patterns (v3.0)

| Extension | Patterns |
|-----------|----------|
| `.py` | `# TODO`, `# FIXME`, `# XXX`, `# HACK`, `# NOTE` |
| `.js` / `.ts` | `// TODO`, `// FIXME`, `// XXX`, `// HACK`, `/* TODO */` |
| `.go` | `// TODO`, `// FIXME`, `// XXX` |
| `.sh` | `# TODO`, `# FIXME`, `# XXX` |
| `.java` | `// TODO`, `// FIXME`, `// XXX`, `/* TODO */` |
| `.md` | `<!-- TODO -->`, `[TODO]`, `- [ ]` |

---

## Test Comparison (v3.0)

Run tests at two git refs and compare coverage:

```python
result = run_test_comparison(repo, before_hash, after_hash)
# Returns:
# {
#   "before_coverage": 72.5,
#   "after_coverage": 74.2,
#   "delta": +1.7,
#   "tests_passed": True
# }
```

Results stored in `metrics.json` as `test_coverage_delta`.

Requires: `pytest` and `coverage` plugin.

---

## Release Management (v3.0)

```bash
auto-evolve.py release --version 2.3.0 [--changelog "..."]
```

Creates:
1. Git tag `v2.3.0` with message
2. Pushes tag to `origin`
3. Creates GitHub release via `gh release create`

Release notes template:
```markdown
# Release v2.3.0

## What changed
[changelog content]

## auto-evolve
This release was managed by auto-evolve.
```

---

## Contributor Tracking (v3.0)

`track_contributors()` scans git log and distinguishes:
- **auto commits**: messages starting with `auto:` or `auto-evolve:`
- **manual commits**: everything else

Stats shown in `log` output and stored in iteration manifest:
```
👥 {auto_commits}A/{manual_commits}M  ({auto_percentage}% auto)
```

---

## Iteration Record Format

```
.auto-evolve/
└── .iterations/
    └── {id}/
        ├── manifest.json        # Metadata + pending items (v3.0: contributors, test_delta)
        ├── plan.md              # Plan with all changes
        ├── pending-review.json   # Items awaiting review (v3.0: llm_analysis, affected_files)
        ├── report.md            # Execution results
        ├── metrics.json         # Iteration metrics (v3.0: test_coverage_delta)
        └── alert.json           # Quality gate alert (if any)
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
  "schedule_interval_hours": 168,
  "schedule_cron_id": null,
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

---

## Requirements

- Python 3.10+
- Git
- `gh` CLI (for PR creation and releases)
- `openclaw` CLI (for cron integration and LLM config)
- `pytest` + `coverage` (optional, for test comparison)

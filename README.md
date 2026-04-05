# Auto-Evolve v2

**Automated skill iteration manager with full audit trail.**

> Make your skills continuously better — automatically.

---

## Quick Start

```bash
# Scan and evolve (auto-execute low-risk)
python3 ~/.openclaw/workspace/skills/auto-evolve/scripts/auto-evolve.py scan

# Preview what would happen
python3 ~/.openclaw/workspace/skills/auto-evolve/scripts/auto-evolve.py scan --dry-run

# Approve pending changes
python3 ~/.openclaw/workspace/skills/auto-evolve/scripts/auto-evolve.py approve --all

# View history
python3 ~/.openclaw/workspace/skills/auto-evolve/scripts/auto-evolve.py log

# Add a repository
python3 ~/.openclaw/workspace/skills/auto-evolve/scripts/auto-evolve.py repo-add ~/path/to/repo --type skill

# List repositories
python3 ~/.openclaw/workspace/skills/auto-evolve/scripts/auto-evolve.py repo-list

# Rollback
python3 ~/.openclaw/workspace/skills/auto-evolve/scripts/auto-evolve.py rollback --to VERSION --reason "..."
```

---

## What It Does

1. **Scans** repositories for git changes and optimization opportunities
2. **Classifies** by risk (low/medium/high)
3. **Auto-executes** low-risk changes (commit + push)
4. **Flags** medium/high risk for approval via `pending-review.json`
5. **High-risk** changes get their own branch + GitHub PR

---

## Key Features

- **Multi-type repos:** skill, norms, project, closed
- **Branch + PR flow** for high-risk changes
- **Proactive scanner:** TODO/FIXME, duplicate code, long functions, missing tests
- **File-based approval:** No external messaging systems
- **Full rollback** via git revert with manifest tracking

---

## Documentation

- [SKILL.md](SKILL.md) — Full documentation
- [CHANGELOG.md](CHANGELOG.md) — Version history
- [references/RISK-CLASSIFICATION.md](references/RISK-CLASSIFICATION.md) — Risk levels
- [references/QUALITY-GATES.md](references/QUALITY-GATES.md) — Quality checks
- [references/NOTIFICATION-TEMPLATE.md](references/NOTIFICATION-TEMPLATE.md) — Templates

---

## Requirements

- Python 3.10+
- Git
- `gh` CLI (for PR creation)

---

## License

MIT

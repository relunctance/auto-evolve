# Changelog

All notable changes to auto-evolve are documented here.

## [2.0.0] — 2026-04-05

### Breaking Changes

- **Config file restructured:** `skills_to_monitor` replaced by `repositories[]` with full repository objects
- **No Feishu integration:** All notification templates now CLI/file-based only
- **Risk defaults changed:** `closed` visibility repos default code changes to medium (not high)

### New Features

- **Multi-type repositories:** Support for `skill`, `norms`, `project`, `closed` repository types
- **Branch + PR workflow:** High-risk changes create `auto-evolve/{desc}` branch and GitHub PR via `gh` CLI
- **Proactive optimization scanner:**
  - TODO/FIXME/XXX/HACK/NOTE annotation detection
  - Duplicate string pattern detection (3x+ occurrences)
  - Long function detection (>100 lines)
  - Missing test coverage detection
  - Pinned/outdated dependency detection
- **`approve` command:** `approve --all` or `approve 1,2,3` for flexible approval
- **`repo-add` command:** Add repositories with `--type` flag
- **`repo-list` command:** List all configured repositories with status
- **True rollback:** `rollback --to VERSION` executes `git revert` with manifest tracking
- **Per-repository risk_override:** Override default risk per repo
- **Pending-review.json:** Human-readable pending items file

### Changed

- **Low-risk changes:** Direct commit + push (no PR) instead of flagging
- **Iteration format:** `items_pending_approval` in manifest.json replaces separate approval tracking
- **Quality gates:** Simplified, removed Feishu-specific gates

### Removed

- **`--interact` flag:** Interactive approval replaced by file-based review + CLI approve
- **`--catalog` command:** Merged into `log`
- **Feishu notification mode:** Only `log` mode supported
- **`schedule` subcommands:** Scheduling handled by OpenClaw cron externally

### Internal

- Full dataclass-based data models (Repository, ChangeItem, IterationManifest, etc.)
- Type annotations complete throughout
- English-only comments (per CODE-STYLE.md v2)
- Python 3.10+ required

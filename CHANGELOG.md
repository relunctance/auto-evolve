# Changelog

All notable changes to auto-evolve are documented here.

## [2.1.0] — 2026-04-05

### New Features

- **Two operation modes:**
  - `semi-auto` (default): auto changes held until `confirm`, rejections tracked
  - `full-auto`: execute per rules without waiting
  - `set-mode` and `set-rules` commands to configure

- **`confirm` command:** Execute held changes in semi-auto mode after reviewing

- **`reject` command:** Reject a pending item with reason, recorded in learnings

- **`learnings` command:** View rejection and approval history

- **`schedule` command:** Output OpenClaw cron setup commands (no direct cron management)

- **`set-mode` and `set-rules` commands:** CLI for mode and rule configuration

- **Learning history (`.learnings/`):**
  - `rejections.json` — rejected changes with reasons
  - `approvals.json` — approved changes
  - Rejected changes are skipped in future scans

- **Closed-repo privacy sanitization:**
  - `pending-review.json` redacts file paths and content for closed repos
  - Uses content hashes instead of file paths
  - Logs don't contain sensitive change details

- **Execution preview:** Shows what will be executed before applying (both modes)

- **Alert generation:** `alert.json` created in iteration dir when quality gates fail

- **`has_alert` flag** in catalog and manifest for iterations with quality gate failures

### Changed

- **Config format updated:** `mode`, `full_auto_rules`, `semi_auto_rules` keys added
- **Semi-auto behavior:** low-risk auto changes are now **held** (not auto-committed) until `confirm`
- **Iteration status values:** `full-auto-completed` added for full-auto scans
- **Repo list display:** Shows 🔒 for closed repos

### Internal

- `AlertEntry` dataclass for structured alerts
- `LearningEntry` dataclass for learning records
- `OperationMode` enum
- `sanitize_pending_item()` for closed-repo content redaction
- `sanitize_change_for_log()` for closed-repo log sanitization
- `is_rejected()` checks learning history before recommending changes
- `add_learning()` records approvals and rejections
- Full type annotations throughout

---

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

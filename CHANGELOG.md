# Changelog

All notable changes to auto-evolve are documented here.

## [2.2.0] — 2026-04-05

### New Features

- **True OpenClaw cron integration:** `schedule --every` now calls `openclaw cron add` directly when the CLI is available. Falls back to printing manual commands otherwise. Cron ID tracked in config (`schedule_cron_id`). `schedule --remove` calls `openclaw cron remove`.

- **Value-based priority scoring:** Items are now scored on three dimensions (value, risk, cost) and ranked by `P = (value × 0.5) / (risk × cost)`. Priority queue displayed in scan output. Pending items sorted by priority. Priority shown in approve prompt.

- **Iteration metrics tracking:** Every scan now generates `.iterations/{id}/metrics.json` containing: `todos_resolved`, `lint_errors_fixed`, `test_coverage_delta`, `files_changed`, `lines_added`, `lines_removed`, `quality_gate_passed`.

- **PR batch merging:** `should_merge_prs()` detects when 3+ similar changes across ≤5 files should be merged. `group_similar_changes()` groups by type and file scope. `build_merged_pr_body()` creates combined PR description.

- **Git conflict auto-resolution:** `handle_pr_conflict()` fetches `origin/main`, rebases, and auto-resolves if conflicts affect ≤2 files. Returns `clean`, `auto_resolved`, or `manual_required`. Applied before PR creation for high-risk changes.

- **Approval reasons:** `approve --reason "text"` records the reason in `approvals.json` under the `reason` field, plus `approved_by: "user"`. Learnings display shows approval reasons.

### Changed

- **Priority display:** `approve` command now shows priority score (P=) for each pending item.
- **Log command:** Shows 📊 indicator when iteration has metrics.
- **Schedule command:** No longer just prints commands — actually creates/removes cron jobs.
- **Scan quality gate output:** Now prints ✅ when gates pass.

### Internal

- `PRIORITY_WEIGHTS`, `DEFAULT_VALUE_SCORES`, `DEFAULT_COST_SCORES` constants added
- `calculate_priority()`, `infer_value_score()`, `infer_risk_score()`, `infer_cost_score()` functions
- `enrich_change_with_priority()`, `sort_by_priority()`, `priority_color()` functions
- `IterationMetrics` dataclass
- `save_metrics()`, `generate_metrics()`, `compute_todos_resolved()` functions
- `setup_cron()`, `remove_cron()` functions
- `should_merge_prs()`, `group_similar_changes()`, `build_merged_pr_body()` functions
- `get_conflict_files()`, `resolve_conflicts_simple()`, `handle_pr_conflict()` functions
- `git_staged_diff()`, `git_diff_lines_added_removed()` helper functions
- `approved_by` field in learning entries
- `ChangeItem` extended with `value_score`, `risk_score`, `cost_score`, `priority` fields
- `IterationManifest` extended with `metrics_id` field
- Config extended with `schedule_cron_id`

---

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

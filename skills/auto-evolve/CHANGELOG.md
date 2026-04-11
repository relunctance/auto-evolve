# Changelog

All notable changes to auto-evolve are documented here.

## [4.4.0] -- 2026-04-11

### New Features

- **Learnings Enhancement:** `learnings list` shows `scenario` + `suggested_direction`. `learnings --all-clear` shows all 4 perspectives (USER/PRODUCT/PROJECT/TECH).

- **GitHub Issue Deduplication:** Checks for existing open issues with similar titles before creating new ones. Updates existing issue instead of duplicating.

- **Workflow Auto-Label:** GitHub Actions workflow auto-creates label if missing.

- **`--repo` reads `GITHUB_REPO_PATH`:** Repo can be specified via `GITHUB_REPO_PATH` env var.

### Bug Fixes

- Fix workflow YAML syntax
- Fix `cmd_trends` syntax and history parsing

---

## [4.3.0] -- 2026-04-05

### New Features

- **Learnings Rewrite:** Single `learnings list|add|remove` subcommand structure with scenario and suggested_direction.

- **All Clear GitHub Issue:** Creates GitHub issue when all learnings are resolved.

- **Trend Tracking:** `trends` command shows metric changes over iterations (lint errors, TODO count, code lines).

- **Scan History Persistence:** Results persisted to `catalog.json` between runs.

- **GitHub Actions Docs:** Setup documentation with `GH_TOKEN` secret configuration.

---

## [4.2.0] -- 2026-04-05

### New Features

- **Weights in Prompts:** Configurable weights for each evaluation perspective in LLM prompts.

- **Scan History Persistence:** Results saved to `catalog.json`.

- **GitHub Integration:** `gh issue list/create` for issue management.

- **`DEFAULT_REF_DOCS`:** Standalone fallback when `project-standard` not installed.

---

## [4.1.0] -- 2026-04-05

### New Features

- **Richer Learnings:** Each learning tracks scenario, code location, and suggested_direction.

- **LLM-Driven TECH Scan:** Security and performance analysis driven by LLM, adapts to project type.

---

## [4.0.0] -- 2026-04-05

### New Features

- **Project-Standard Integration:** Uses `project-standard` reference documents for 12+ project types.

- **Updated READMEs:** English and Chinese versions rewritten.

---

## [3.5.0] -- 2026-04-05

### New Features

- **Per-Persona Learnings:** Learnings tracked per persona (USER/PRODUCT/PROJECT/TECH).

- **LLM Reliability Tracking:** Tracks LLM call success/failure rates.

- **Metrics Tracking:** EffectTracker + CostTracker for measuring improvement over iterations.

- **FileAnalysisCache:** 30-minute TTL cache, batch processing reduces LLM calls 5x.

### Bug Fixes

- Fix `record_learning` NameError (import at module level)
- Fix `learnings_dir` per-persona path

---

## [3.1.0] -- 2026-04-05

### New Features

- **EffectTracker:** Compares before/after snapshots of code quality metrics.

- **CostTracker:** Records LLM calls with token counts and USD cost.

- **IssueLinker:** Finds and auto-closes related issues after commit.

- **SmartScheduler:** Activity-based scan interval recommendations.

- **`effects` / `costs` commands:** Display tracking reports.

- **`schedule --suggest/--auto`:** Smart scheduling subcommands.

### Internal

- `LLM_PRICING` constant with per-model pricing
- `EffectTracker`, `CostTracker`, `IssueLinker`, `SmartScheduler` classes

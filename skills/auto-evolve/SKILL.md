# Auto-Evolve Skill

## Purpose

Automated skill inspection and self-improvement engine. Runs multi-perspective scans on skills, generates findings, requests user confirmation for fixes, and applies improvements.

## Architecture

```
Auto-Evolve (orchestration)
    │
    ├── confirmation-engine/     ← User interaction + decision storage
    │   └── Reads: perspective-config.yaml
    │
    ├── security-scanner/        ← Security perspective implementation
    │   └── Depends on: scanner-contract/
    │
    ├── scanner-contract/        ← Shared LLM evaluator + base classes
    │   └── llm_evaluator.py
    │
    ├── report-generator/        ← Multi-format report generation
    │   └── report_generator.py
    │
    └── project-standard/        ← Read-only knowledge base
        └── (standards, schemas)
```

## Skill Integration

### confirmation-engine

**Role:** Handles user interaction protocol

**Reads:**
- `perspective-config.yaml` — which perspectives are active
- `.auto-evolve/learnings/decisions.json` — past decisions
- `.auto-evolve/learnings/patterns.json` — pattern-based auto-reply
- `.auto-evolve/learnings/ignored.json` — permanently ignored findings

**Key Classes:**
- `ConfirmationEngine` — main orchestrator
- `ConfigLoader` — loads perspective config
- `LearningsStore` — stores and replays decisions
- `TierClassifier` — determines if confirmation is required
- `FeishuNotifier` — sends confirmation cards to Feishu

**Interaction Tiers:**
```
Tier 1: Always ask  → Critical severity OR not auto-actionable
Tier 2: Ask if low confidence  → High severity OR confidence < 70%
Tier 3: Inform only  → Other
```

### security-scanner

**Role:** Security perspective implementation

**Key Classes:**
- `SecurityScanner` — main scanner
- `SecurityFinding` — finding data class
- Checks: SQL injection, command injection, hardcoded secrets, weak auth, XSS, TLS

**Depends on:** `scanner-contract/llm_evaluator.py`

### scanner-contract

**Role:** Shared infrastructure for all scanners

**Key Classes:**
- `LLMEvaluator` — LLM API client + evaluation engine
- `EvaluationContext` / `EvaluationResult` — data classes
- `CodeExtractor` — extract relevant code snippets

### report-generator

**Role:** Generate scan reports in multiple formats

**Formats:**
- Markdown (human-readable)
- HTML (web viewing)
- JSON (machine-readable)
- Feishu Card (interactive notification)

## Usage

```bash
# Run a scan
auto-evolve scan --repo /path/to/repo

# Confirm pending fixes
auto-evolve confirm --all

# View learnings
auto-evolve learnings

# Set scan mode
auto-evolve set-mode full-auto
```

## Configuration

Create `perspective-config.yaml` in the repo root:

```yaml
scan_mode: full  # or "quick"
project:
  business_form: backend
  tech_stack: python
perspectives:
  optional:
    market_influence: true
```

## Learnings Storage

Decisions are stored in `.auto-evolve/learnings/`:

```
.learnings/
├── decisions.json   # All individual decisions
├── patterns.json   # Pattern-based auto-reply rules
└── ignored.json    # Permanently ignored findings
```

## Relationship with project-standard

- **project-standard** is a **read-only knowledge base**
- Auto-evolve reads perspective definitions from project-standard
- Auto-evolve implements the interaction protocol defined in project-standard
- Auto-evolve does NOT modify project-standard

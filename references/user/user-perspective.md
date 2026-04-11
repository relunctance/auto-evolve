# 用户视角 — User Perspective

## Evaluation Criteria

### 1. CLI / Interaction Design
- Flag names are intuitive (--dry-run not --simulate-mode)
- Reasonable defaults (don't require all flags to run)
- --help is clear, explains usage not just lists flags
- Subcommand structure is logical (git clone not git --clone)
- No unnecessary interactive prompts

### 2. Learning Curve
- README has "Quick Start" — up in 3 steps
- Has example input/output
- No dependency黑洞 (no circular install requirements)
- Error messages suggest fixes

### 3. Error Messages
- Error explains WHAT went wrong, not just "Error occurred"
- Has fix suggestions ("You may need to: ...")
- Distinguishes: config error vs runtime error vs data error
- Log levels are clear (ERROR/WARNING/INFO)

### 4. Fault Tolerance
- Operations are atomic — no half-baked state on failure
- Has backup/rollback mechanism
- Failures give clear error + recovery guide
- Idempotent: running twice has no side effects

### 5. Workflow Efficiency
- Core operations complete in <=3 steps
- Config files preferred over repeated flag passing
- Supports pipeline/chain for automation
- Has batch mode

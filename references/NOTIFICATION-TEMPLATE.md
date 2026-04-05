# Notification Templates v2

> Note: v2 uses file-based notifications only. No external messaging (Feishu, Slack, etc.).
> Check `pending-review.json` for pending items, or run `auto-evolve.py log`.

---

## Iteration Log Entry

```
## Iteration {version}

Date: {date} UTC
Status: {status}
Risk Level: {risk_level}

Changes detected: {n}
Optimizations found: {n}
Auto-executed: {n}
Pending approval: {n}
Duration: {duration}s
```

---

## Pending Approval Notice

```
📋 Pending Approval — Iteration {version}

{count} items need approval:

[1] {risk} {description}
    File: {file_path}
    Category: {category}

[2] {risk} {description}
    ...

---
Approve with:
  auto-evolve.py approve --all
  # or
  auto-evolve.py approve 1,3
```

---

## Approval Confirmation

```
✅ Approved {count} items from iteration {version}

Committed and pushed.
```

---

## Rollback Confirmation

```
🔄 Rollback Complete — {rollback_version}

Rolled back: {target_version}
Reason: {reason}
Reverted items: {count}

---
To undo this rollback, run:
  git revert {new_commit_hash}
```

---

## Scan Complete (Dry Run)

```
🔍 Scan Complete (dry-run)

Changes found: {n}
Optimizations: {n}
Low risk: {n}
Medium risk: {n}
High risk: {n}

No changes committed.
Run without --dry-run to apply.
```

---

## Error Notification

```
❌ Auto-Evolve Error

Command: {command}
Error: {error_message}

Iteration {version} logged.
Manual intervention may be required.
```

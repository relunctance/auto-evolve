# GitHub Actions Setup

## Required Secrets

Configure these in **GitHub repo → Settings → Secrets and variables → Actions**:

| Secret Name | Where to Get | Required |
|------------|-------------|---------|
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys | ✅ Yes |
| `GITHUB_TOKEN` | Auto-provided by GitHub Actions | ✅ Auto (no setup) |

## Setup Steps

1. Go to your repository on GitHub
2. **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
3. Add:
   - **Name**: `OPENAI_API_KEY`
   - **Secret**: Your key from https://platform.openai.com/api-keys

## Workflow Triggers

| Event | Trigger |
|-------|---------|
| PR opened/updated | Full scan + GitHub issue + PR comment |
| Push to `master`/`main` | Full scan + GitHub issue |
| Manual | Workflow dispatch |

## How Results Are Posted

- Scan results are posted as a **GitHub Issue** (labeled `auto-evolve`)
- For PR events: also posts as **PR comment**
- **v4.3**: Issues are auto-closed when all findings are resolved

## If Scan Finds Nothing

When a scan finds no issues, an "All Clear" issue is still created so you have a record of when the project was verified clean:

```markdown
## ✅ Auto-Evolve Scan — All Clear

No issues found. Project passed all four perspectives.
```

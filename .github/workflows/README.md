# GitHub Actions Setup

## Required Secrets

Configure these in **GitHub repo → Settings → Secrets and variables → Actions**:

| Secret Name | Where to Get | Required |
|------------|-------------|---------|
| `OPENAI_API_KEY` | platform.openai.com | ✅ Yes |
| `GITHUB_TOKEN` | Auto-provided by GitHub Actions | ✅ Auto |

## Optional: Add as Repository Secret

1. Go to your repository on GitHub
2. **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
3. Add:
   - **Name**: `OPENAI_API_KEY`
   - **Secret**: Your OpenAI API key from https://platform.openai.com/api-keys

## Workflow Triggers

The workflow runs automatically on:

| Event | Trigger |
|-------|---------|
| PR opened/updated | Full scan + results posted as GitHub issue + PR comment |
| Push to `master`/`main` | Full scan + results posted as GitHub issue |
| Manual trigger | Workflow dispatch with custom repo target |

## How It Works

1. Workflow triggers on PR or push
2. Installs dependencies (`openai`, `requests`)
3. Runs `auto-evolve scan --repo . --github-event <event>`
4. Scan results are posted as a GitHub issue (auto-labeled `auto-evolve`)
5. For PR events: also posts as PR comment
6. **v4.3**: Automatically closes issues where all findings are resolved

## Notes

- The workflow uses your `GITHUB_TOKEN` automatically — no extra setup needed
- `OPENAI_API_KEY` is required for LLM-powered scanning
- Results are posted as issues (not just comments) so they're trackable over time
- Resolved findings automatically close their tracking issues

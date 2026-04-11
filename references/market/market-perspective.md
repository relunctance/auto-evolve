# Market Perspective Inspection Standards

> **Core Question: Does this project have market presence and competitive advantage?**

Market perspective focuses on **external visibility and competitiveness** — a technically excellent project that nobody uses is a failed project. This perspective complements the four internal inspection lenses (User / Product / Project / Tech) with an outward-looking view.

---

## Inspection Dimensions

### 1. Community Engagement

**Is the project gaining traction?**

- [ ] Stars growth trend: ≥10% MoM growth is healthy for active projects
- [ ] Forks ratio: forks/stars > 0.1 indicates community interest (people clone to experiment)
- [ ] Contributors: ≥3 active contributors signals sustainable maintenance
- [ ] Issue response time: maintainer responds within 7 days (urgent: 48h)
- [ ] Recent activity: commits in last 30 days confirms active maintenance
- [ ] Release frequency: at least 1 release per quarter for mature projects

**Typical Problems:**
- Project abandoned but stars keep growing (misleading metric)
- High stars but no active contributors (single point of failure)
- Stars plateau after initial launch (not gaining organic traction)

### 2. Adoption & Ecosystem

**Is the project being used by others?**

- [ ] Listed in dependency managers (npm/pypi/crates.io) with download stats
- [ ] Has dependents: other projects explicitly depend on it
- [ ] Forked by organizations beyond individual developers
- [ ] Integrated into other products/tools (plugins, themes, extensions)
- [ ] Mentioned in blog posts, tutorials, or case studies
- [ ] Cross-referenced by comparable tools in comparison articles

**Typical Problems:**
- Heavy reliance on personal network for adoption
- Downloads only from CI bots (not real users)
- No integration examples in other major projects

### 3. Competitive Positioning

**How does this project compare to alternatives?**

- [ ] Has clear differentiation: "Why use this instead of X?"
- [ ] Benchmarks or performance comparisons available
- [ ] Known limitations are documented honestly
- [ ] Pricing model (if any) is transparent and justified
- [ ] Has unique features that competitors lack
- [ ] Tracks competitor feature parity actively

**Typical Problems:**
- README claims superiority without evidence
- "Better than X" with no benchmarks
- Features identical to competitors with no differentiation
- No clear target user / use case

### 4. Content & Documentation Quality

**Can potential users discover and evaluate the project?**

- [ ] Has a landing page or well-structured README
- [ ] Documented use cases with real-world examples
- [ ] Changelog / release notes are detailed
- [ ] Has logo, badges, screenshots / demo (if applicable)
- [ ] SEO-friendly: searchable by relevant keywords
- [ ] Has CONTRIBUTING.md / governance model

**Typical Problems:**
- README is a wall of text with no visual structure
- No screenshots for visual products
- Broken links, outdated examples
- No indication of when last updated

### 5. Brand & Reputation

**What do people say about the project?**

- [ ] Positive sentiment in issues / discussions (not just complaints)
- [ ] Mentions by influencers, podcasts, or newsletters
- [ ] Conference talks or meetup presentations
- [ ] Awards or featured listings (GitHub Explore, Awesome lists)
- [ ] No viral negative incidents (security failures, license controversies)
- [ ] Security audit results published (if handling sensitive data)

**Typical Problems:**
- Only negative feedback in issue tracker
- Known security incidents without post-mortem
- License changes that burn community trust
- Plagiarism or IP disputes

---

## Data Sources

Market perspective relies on **external API data** rather than code inspection:

| Metric | Data Source |
|--------|-------------|
| Stars / Forks / Contributors | GitHub API |
| Downloads | npm registry / PyPI / crates.io |
| Dependent repos | GitHub dependency graph / npm dependents |
| Issue response time | GitHub API (issue events) |
| Recent activity | GitHub API (commit history) |
| Competitive comparisons | Manual research / benchmarks |
| Content mentions | Google, social search, aggregator sites |

---

## Output Template

```markdown
## 📊 Market Perspective Results

### Overall Rating: [ Excellent / Good / Acceptable / Poor ]

### Community Engagement
| Metric | Value | Assessment |
|--------|-------|------------|
| Stars (30d growth) | X (+Y%) | 🟢 Healthy / 🟡 Slow / 🔴 Stagnant |
| Contributors | N | 🟢 Active / 🟡 Limited / 🔴 Solo |
| Last commit | date | 🟢 Active / 🟡 Stale / 🔴 Abandoned |
| Issue response | X days avg | 🟢 Responsive / 🟡 Slow / 🔴 Ignored |

### Adoption & Ecosystem
| Metric | Value | Assessment |
|--------|-------|------------|
| Downloads (30d) | X | 🟢 Popular / 🟡 Moderate / 🔴 Low |
| Dependents | N repos | 🟢 Ecosystem / 🟡 Some / 🔴 Isolated |
| Integrations | N tools | 🟢 Rich / 🟡 Limited / 🔴 None |

### Competitive Position
| Dimension | Assessment |
|-----------|------------|
| Differentiation | Clear / Vague / None |
| Unique features | ... |
| Honest limitations | ... |
| Benchmark evidence | Available / Missing |

### Brand & Reputation
- Positive mentions: X
- Featured listings: X
- Security audits: ✅ Passed / ❌ Not available / ⚠️ Issues found

### Priority Actions
1. [Most urgent market gap]
2. [Next priority]
...
```

---

## Evaluation Criteria

| Grade | Score | Description |
|-------|-------|-------------|
| Excellent | 90-100 | Strong market presence, active ecosystem, clear competitive edge |
| Good | 75-89 | Healthy growth, some adoption, no critical gaps |
| Acceptable | 60-74 | Limited traction, needs more outreach or differentiation |
| Poor | <60 | Low visibility, no clear market fit, risk of abandonment |

---

## Perspective Weights by Project Type

Market perspective weight varies by project type:

| Business Form | Market Weight | Rationale |
|--------------|---------------|-----------|
| **Frontend** | 15% | UI/UX matters more than market hype |
| **Backend** | 15% | Technical merit drives adoption |
| **AI/Agent** | 20% | Ecosystem and model access matter |
| **Infrastructure** | 15% | Reliability trumps marketing |
| **Content/Docs** | 30% | Visibility IS the product |
| **Generic** | 15% | Default baseline |

---

## Relationship with Other Perspectives

```
Market Perspective (External)
        │
        ├── Compensates for Product perspective's internal bias
        │   (Product says "great features" but market disagrees)
        │
        ├── Validates Project perspective's health metrics
        │   (Active maintenance + community = trust signal)
        │
        └── Complements Tech perspective's code quality
            (Great code + zero adoption = failed project)
```

---

## 🔌 Scanner Adapter Contract

> This section defines the **fixed interface standard** that all market data adapters must conform to. Any data source — GitHub API, enterprise internal systems, personal private domains — can be plugged in as long as it outputs the standardized data contract below.

### Design Principles

1. **Data contract over implementation** — adapters only need to produce the standard output format; how they fetch data is irrelevant
2. **Field names are fixed** — consumer code reads fixed field names, not source-specific keys
3. **Null tolerance** — if a data source doesn't have a field, return `null`; do not omit the key
4. **Assessment is computed by consumer** — adapters only collect and normalize raw data; scoring logic lives in the scanner engine

### Standard Output Schema

```json
{
  "source": "github | npm | pypi | internal | custom",
  "source_name": "GitHub / npm registry / enterprise system name / ...",
  "fetched_at": "2026-04-11T11:27:00+08:00",
  "project": {
    "name": "owner/repo or package name",
    "url": "homepage or repo URL"
  },
  "community": {
    "stars": { "total": 1200, "growth_30d": 85, "growth_unit": "absolute" },
    "forks": { "total": 120 },
    "contributors": { "total": 8, "active_30d": 3 },
    "subscribers": { "total": null },
    "watchers": { "total": null }
  },
  "adoption": {
    "downloads": { "total_30d": 45000, "source": "npm" },
    "dependents": { "direct": 23, "total": null },
    "integrations": { "count": 5, "details": [] },
    "citations": { "count": null }
  },
  "activity": {
    "last_commit_at": "2026-04-09T14:22:00+08:00",
    "last_release_at": "2026-03-15T00:00:00+08:00",
    "open_issues": 12,
    "closed_issues_30d": 8,
    "avg_issue_response_days": 2.3,
    "commit_frequency_30d": 15
  },
  "content": {
    "readme_exists": true,
    "changelog_exists": true,
    "contributing_exists": true,
    "license": "MIT",
    "has_landing_page": false,
    "has_logo": true
  },
  "brand": {
    "featured_listings": ["GitHub Explore"],
    "conference_talks": 0,
    "blog_mentions_30d": 2,
    "security_audit_available": false,
    "sentiment_score": null
  },
  "competitive": {
    "has_benchmarks": false,
    "has_differentiation": true,
    "differentiation_text": "Self-evolving project inspection with learnings memory",
    "known_limitations": ["No Windows support yet", "Single-user learning model"],
    "unique_features": ["Learnings memory", "Four-perspective engine"]
  },
  "raw": {}
}
```

### Field Definitions

| Field Path | Type | Required | Description |
|------------|------|----------|-------------|
| `source` | string | ✅ | Data source type: `github`, `npm`, `pypi`, `internal`, `custom` |
| `source_name` | string | ✅ | Human-readable source identifier |
| `fetched_at` | ISO8601 | ✅ | When this data was collected |
| `project.name` | string | ✅ | Project identifier (owner/repo or package name) |
| `project.url` | string | ✅ | Canonical project URL |
| `community.stars.total` | int | ✅ | Total star count |
| `community.stars.growth_30d` | int | ✅ | Stars gained in last 30 days |
| `community.stars.growth_unit` | string | ✅ | `"absolute"` or `"percentage"` |
| `community.forks.total` | int | ✅ | Total fork count |
| `community.contributors.total` | int | ✅ | Total contributor count |
| `community.contributors.active_30d` | int | ✅ | Active contributors in last 30 days |
| `adoption.downloads.total_30d` | int | ✅ | Downloads in last 30 days |
| `adoption.downloads.source` | string | ✅ | Download count source: `npm`, `pypi`, `crates.io`, etc. |
| `adoption.dependents.direct` | int | ✅ | Direct dependent repos/packages |
| `adoption.integrations.count` | int | ✅ | Number of known integrations |
| `activity.last_commit_at` | ISO8601 | ✅ | Date of last commit |
| `activity.last_release_at` | ISO8601 | ✅ | Date of last release |
| `activity.open_issues` | int | ✅ | Currently open issues |
| `activity.closed_issues_30d` | int | ✅ | Issues closed in last 30 days |
| `activity.avg_issue_response_days` | float | ✅ | Average days to first maintainer response |
| `activity.commit_frequency_30d` | int | ✅ | Commits in last 30 days |
| `content.readme_exists` | bool | ✅ | README file present |
| `content.contributing_exists` | bool | ✅ | CONTRIBUTING file present |
| `content.license` | string | ✅ | License identifier (e.g. `MIT`, `Apache-2.0`) |
| `brand.featured_listings` | string[] | ✅ | Lists/features the project appears in |
| `brand.security_audit_available` | bool | ✅ | Security audit published |
| `competitive.has_benchmarks` | bool | ✅ | Performance benchmarks published |
| `competitive.has_differentiation` | bool | ✅ | Clear unique value proposition |
| `competitive.differentiation_text` | string | ✅ | One-sentence differentiation |
| `competitive.known_limitations` | string[] | ✅ | Honestly documented gaps |
| `competitive.unique_features` | string[] | ✅ | Features competitors lack |
| `raw` | object | ✅ | Source-specific raw data for debugging; adapters may attach additional fields here |

> **Note:** All fields marked ✅ are **required** — return the field even if value is `null`. This ensures consumer code always knows the field exists regardless of data source.

### Adapter Implementation Example

```python
class GitHubMarketAdapter:
    """Adapter for GitHub API data source."""

    def fetch(self, repo: str) -> dict:
        # 1. Fetch raw data from GitHub API
        raw = self._github_api.get_repo(repo)
        commits = self._github_api.get_commits(repo, since=datetime.now() - timedelta(days=30))
        issues = self._github_api.get_issues(repo, state='all', since=datetime.now() - timedelta(days=30))

        # 2. Normalize to standard contract
        return {
            "source": "github",
            "source_name": "GitHub API",
            "fetched_at": datetime.now().isoformat(),
            "project": {
                "name": raw["full_name"],
                "url": raw["html_url"]
            },
            "community": {
                "stars": {
                    "total": raw["stargazers_count"],
                    "growth_30d": self._compute_stars_growth(repo, 30),
                    "growth_unit": "absolute"
                },
                "forks": {"total": raw["forks_count"]},
                "contributors": {
                    "total": raw.get("subscribers_count", 0),
                    "active_30d": self._unique_contributors(commits)
                },
                "subscribers": {"total": raw.get("subscribers_count")},
                "watchers": {"total": raw.get("watchers_count")}
            },
            "adoption": {
                "downloads": {"total_30d": None, "source": None},  # Not available from GitHub
                "dependents": {"direct": raw.get("network_count", 0), "total": None},
                "integrations": {"count": self._count_integrations(repo), "details": []},
                "citations": {"count": None}
            },
            "activity": {
                "last_commit_at": raw["pushed_at"],
                "last_release_at": self._get_last_release_date(repo),
                "open_issues": raw["open_issues_count"],
                "closed_issues_30d": self._count_closed_issues(issues, 30),
                "avg_issue_response_days": self._compute_avg_response_time(issues),
                "commit_frequency_30d": len(commits)
            },
            "content": {
                "readme_exists": raw.get("has_readme", False),
                "changelog_exists": raw.get("has_changelog", False),
                "contributing_exists": raw.get("has_contributing", False),
                "license": raw.get("license", {}).get("spdx_id"),
                "has_landing_page": raw.get("homepage") is not None,
                "has_logo": raw.get("has_logo", False)
            },
            "brand": {
                "featured_listings": self._get_featured_listings(repo),
                "conference_talks": 0,
                "blog_mentions_30d": None,
                "security_audit_available": self._has_security_audit(repo),
                "sentiment_score": None
            },
            "competitive": {
                "has_benchmarks": False,
                "has_differentiation": True,
                "differentiation_text": self._extract_differentiation(raw.get("description", "")),
                "known_limitations": [],
                "unique_features": []
            },
            "raw": raw  # Full API response for debugging
        }
```

### Extensibility: Adding New Data Sources

To add a new data source (e.g., enterprise internal data):

1. Implement a new adapter class with `fetch(project_identifier) -> dict` method
2. Ensure output conforms 100% to the **Standard Output Schema** above
3. Register adapter in the scanner engine's adapter registry:

```python
# scanner_engine.py
ADAPTER_REGISTRY = {
    "github": GitHubMarketAdapter(),
    "npm": NpmMarketAdapter(),
    "internal": EnterpriseInternalAdapter(),   # ← New enterprise adapter
    "custom": CustomPrivateDomainAdapter(),       # ← New私域 adapter
}

def scan_market(repo_url: str) -> dict:
    adapter = detect_adapter(repo_url)  # Select adapter by URL pattern
    raw_data = adapter.fetch(normalize_identifier(repo_url))
    return normalize_to_output(raw_data)  # Always returns standard schema
```

### Key Extensibility Points

| Extension Point | How to Extend |
|----------------|---------------|
| New data source | Implement new adapter class → register in `ADAPTER_REGISTRY` |
| New metrics | Add field to `raw` object → consumer code reads from `raw` if standard field is `null` |
| New scoring logic | Scanner engine reads standard fields → scoring is source-agnostic |
| Source-specific normalization | Each adapter handles its own API quirks → outputs identical schema |

> **Golden Rule:** The scanner engine **never knows which data source is behind the data**. It always reads the same field names. If a field is `null`, that means the data source doesn't provide it — not an error.

# Auto-Evolve Skill

## Purpose

Automated skill inspection and self-improvement engine. Runs 19-perspective scans on skills, generates findings, requests user confirmation for fixes, and applies improvements.

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
        └── references/{perspective}/  ← 19 perspective standards
```

## The 19 Perspectives (v4.0)

Perspectives are organized into **4 execution levels** (run in order: 0 → 1 → 2 → 3):

### Level 0 — Core Foundations (run first, in parallel)
| Perspective | Icon | Focus |
|-------------|------|-------|
| USER (用户视角) | 👤 | CLI设计、错误提示、上手门槛、容错性、操作流程度 |
| PRODUCT (产品视角) | 📦 | README承诺兑现、文档与代码一致性、功能完整性、缺失功能 |
| PROJECT (项目视角) | 🏗 | learnings闭环、巡检节奏、配置合理性、依赖健康度、Git实践 |
| TECH (技术视角) | ⚙️ | 代码质量(重复/长函数)、安全漏洞、性能问题、异常处理 |

### Level 1 — Quality Gates (depends on Level 0)
| Perspective | Icon | Focus |
|-------------|------|-------|
| SECURITY (安全视角) | 🔒 | 硬编码密码/Token、SQL注入、XSS/CSRF、弱鉴权 |
| TESTING (测试视角) | 🧪 | 测试覆盖率、测试质量、边界条件、冒烟测试 |
| COMPATIBILITY (兼容性视角) | 🔄 | 多Python版本、多Node版本、API版本兼容性 |

### Level 2 — Operational Excellence
| Perspective | Icon | Focus |
|-------------|------|-------|
| INTEGRATION (集成视角) | 🔗 | 外部API集成、第三方SDK、webhook可靠性、消息队列 |
| OBSERVABILITY (可观测性视角) | 📊 | 日志完备性、指标覆盖、链路追踪、告警阈值 |
| RELIABILITY (可靠性视角) | 🛡 | 熔断降级、重试机制、超时配置、幂等性 |
| COST_EFFICIENCY (成本效率视角) | 💰 | API调用成本、云资源浪费、缓存策略、LLM调用频率 |
| MARKET_INFLUENCE (市场影响视角) | 📈 | 竞品对比、功能差异化、发布节奏、社区活跃度 |
| BUSINESS_SUSTAINABILITY (商业可持续性视角) | 🌱 | 商业模式一致性、用户留存、成本结构、扩展性 |
| INDUSTRY_VERTICAL (行业垂直视角) | 🏭 | 行业合规、特定行业协议、数据主权、监管要求 |
| BUSINESS_COMPLIANCE (商业合规视角) | ⚖️ | 许可证合规、数据隐私(GDPR/CCPA)、知识产权 |

### Level 3 — Delivery Quality (run last)
| Perspective | Icon | Focus |
|-------------|------|-------|
| DOCUMENTATION (文档视角) | 📚 | README完整性、API文档、示例代码、CHANGELOG |
| I18N (国际化视角) | 🌍 | 硬编码字符串、多语言覆盖、日期/货币格式、RTL支持 |
| ACCESSIBILITY (可访问性视角) | ♿ | ARIA标签、键盘导航、颜色对比度、屏幕阅读器支持 |

## Skill Integration

### confirmation-engine

**Role:** Handles user interaction protocol

**Reads:**
- `perspective-config.yaml` — which perspectives are active (data-driven config)
- `.auto-evolve/learnings/decisions.json` — past decisions
- `.auto-evolve/learnings/patterns.json` — pattern-based auto-reply
- `.auto-evolve/learnings/ignored.json` — permanently ignored findings

**Key Classes:**
- `ConfirmationEngine` — main orchestrator
- `PerspectiveConfig` — loads perspective-config.yaml (with 4-perspective fallback)
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

**Role:** Security perspective implementation (maps to SECURITY perspective in Level 1)

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
- Markdown (human-readable) — one section per perspective
- HTML (web viewing)
- JSON (machine-readable)
- Feishu Card (interactive notification)

## Usage

```bash
# Run a full 19-perspective scan
auto-evolve scan --repo /path/to/repo

# Confirm pending fixes
auto-evolve confirm --all

# View learnings
auto-evolve learnings

# Set scan mode
auto-evolve set-mode full-auto
```

## Configuration

### perspective-config.yaml

The scan is driven by `perspective-config.yaml` in the skill directory.
Each perspective defines:
- `display_name`, `icon`, `color` — display metadata
- `execution_level` (0-3) — when to run
- `priority` — order within a level
- `scanner_type` ("llm" | "static" | "hybrid")
- `doc_path` — path to the perspective's reference doc in project-standard
- `llm_focus` — what the LLM should focus on
- `categories` — finding categories this perspective produces
- `default_weight` — default weight for this perspective
- `enabled` — whether to run this perspective

**Backward compatibility:** If `perspective-config.yaml` is absent, the system falls back to the original 4-perspective behavior (USER, PRODUCT, PROJECT, TECH).

### Enabling/disabling perspectives

In `perspective-config.yaml`, set `enabled: false` to skip a perspective:

```yaml
perspectives:
  MARKET_INFLUENCE:
    enabled: false  # skip this perspective
  SECURITY:
    enabled: true   # explicitly enabled
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
- Auto-evolve reads perspective definitions from `project-standard/references/{perspective}/`
- Auto-evolve implements the interaction protocol defined in project-standard
- Auto-evolve does NOT modify project-standard

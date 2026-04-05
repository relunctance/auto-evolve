# Auto-Evolve

**AI Agent 驱动项目持续进化的自动巡检引擎。**

> 让项目越用越好——通过持续追问"还有什么不足, 有哪些地方可以优化, 使用体验如何？"，然后自主或半自主地执行改进。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://img.shields.io/badge/Python-3.10+-blue.svg)

**English**: [README.md](README.md)

---

## 它是什么？

Auto-Evolve 是一个**运行在 OpenClaw 上的自动巡检引擎**。

每 N 分钟，它会：
1. 扫描指定的项目（skill、norms 或 project）
2. 从**主人视角**问："还有什么不足, 有哪些地方可以优化, 使用体验如何？"
3. 结合主人的背景、偏好、历史学习，给出**真正的产品改进建议**
4. 在 `full-auto` 模式下自主执行低风险改动，在 `semi-auto` 模式下等待确认

**不是**代码质量扫描器——它是项目的**持续改进伙伴**。

---

## 核心功能

### 🎯 从主人视角追问

不是问"代码有没有问题"，而是带着主人的背景来问：

```
主人背景：主人追求自动化，讨厌手动操作...
主人偏好：主人之前拒绝了 3 次自动生成 test 的改动...
历史：主人批准过删除 TODO 的改动...

"还有什么不足, 有哪些地方可以优化, 使用体验如何？"
```

### 🧠 Persona 感知记忆系统

支持按 persona（main/tseng/wukong/bajie/bailong）召回对应的：
- OpenClaw SQLite 记忆库（`memory/{persona}.sqlite`）
- hawk-bridge 向量记忆（`lancedb/`）
- `learnings/` 中的历史决策

### 📊 产品洞察 + 代码优化

巡检输出两类结果：

**产品洞察**（来自 LLM 主人视角分析）：
```
🎯 Product Evolution Insights:
  🚫 [STOP_DOING] missing_test 被拒绝 3 次了 → 停止
  😤 [USER_COMPLAINT] 这流程太麻烦，主人得手动做 3 步
  📊 [COMPETITIVE_GAP] 竞品有这个功能我们没有
```

**代码优化**（来自扫描器）：
```
🔧 Code Optimizations:
  🟢 duplicate_code: scripts/lua_def_file.py (3处重复)
  🟡 long_function: soulforge.py:127行 > 100行
  🟡 missing_test: 5个模块缺少测试覆盖
```

### ⚡ 执行模式

| 模式 | 说明 |
|------|------|
| `full-auto` | 低风险改动自动执行；中风险开 PR；高风险跳过 |
| `semi-auto` | 所有改动等待确认后执行 |

### 🔒 安全机制

- **质量门槛**：语法检查 + pytest/jest 真实测试
- **git revert 回滚**：一键回滚到上一版本
- **learnings 过滤**：被拒绝的改动不再重复尝试
- **Privacy**：closed 仓库代码不外泄

---

## 快速开始

```bash
# 安装
clawhub install auto-evolve

# 添加巡检项目
python3 scripts/auto-evolve.py repo-add ~/.openclaw/workspace/skills/soul-force --type skill --monitor

# 全自动化巡检
python3 scripts/auto-evolve.py scan

# 预览模式（不执行）
python3 scripts/auto-evolve.py scan --dry-run

# 以主人视角召回记忆巡检
python3 scripts/auto-evolve.py scan --dry-run --recall-persona master --memory-source both

# 每 10 分钟自动巡检
python3 scripts/auto-evolve.py schedule --every 10
```

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Auto-Evolve 巡检引擎                      │
│                                                         │
│  Cron 触发（每 N 分钟）                                    │
│       │                                                  │
│       ▼                                                  │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Persona 检测 + Workspace 定位                    │    │
│  │  detect_persona() → main/tseng/wukong/...        │    │
│  └─────────────────────┬───────────────────────────┘    │
│                        ▼                                 │
│  ┌─────────────────────────────────────────────────┐    │
│  │  记忆召回（按 persona）                         │    │
│  │  OpenClaw SQLite (primary)                    │    │
│  │  + hawk-bridge LanceDB (supplement)           │    │
│  │  + learnings history                           │    │
│  └─────────────────────┬───────────────────────────┘    │
│                        ▼                                 │
│  ┌─────────────────────────────────────────────────┐    │
│  │  LLM 产品级分析（主人视角）                      │    │
│  │  "还有什么不足, 有哪些地方可以优化,              │    │
│  │   使用体验如何？"                                │    │
│  └─────────────────────┬───────────────────────────┘    │
│                        ▼                                 │
│  ┌─────────────────────────────────────────────────┐    │
│  │  代码扫描（并行）                                │    │
│  │  重复代码 / 长函数 / TODO / 测试覆盖            │    │
│  └─────────────────────┬───────────────────────────┘    │
│                        ▼                                 │
│  ┌─────────────────────────────────────────────────┐    │
│  │  优先级排序 + 质量门槛                          │    │
│  │  full-auto: 低风险 → 自动执行                   │    │
│  │  full-auto: 中风险 → 开 PR                     │    │
│  │  semi-auto: 全部 → 等待确认                    │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 命令

| 命令 | 说明 |
|------|------|
| `scan` | 巡检项目 |
| `scan --dry-run` | 预览，不执行 |
| `scan --recall-persona master` | 召回主人记忆巡检 |
| `scan --memory-source openclaw` | 指定记忆源 |
| `confirm` | 确认执行待处理改动 |
| `approve / reject` | 批准/拒绝并记录原因 |
| `set-mode full-auto` | 全自动化模式 |
| `set-rules --low true` | 设置自动执行规则 |
| `schedule --every 10` | 每 10 分钟巡检 |
| `learnings` | 查看学习历史 |
| `rollback` | 回滚 |

---

## 当前能力边界

**能自动做的（低风险）：**
- ✅ 删除空的 TODO/FIXME 注释
- ✅ 消除简单的字符串重复
- ✅ 更新依赖版本号为 semver 范围
- ✅ 修复轻微的格式化问题

**需要确认的（中风险）：**
- ⚠️ 重构函数结构
- ⚠️ 跨文件改动
- ⚠️ 修改业务逻辑

**还做不到的：**
- ❌ 复杂的多文件重构
- ❌ 需要理解业务语义的改动
- ❌ 没有测试保障的改动

---

## 改进路线图

| 优先级 | 改进点 | 说明 |
|--------|--------|------|
| 🔴 最高 | LLM 代码生成可靠性 | 当前 ~40% 返回 prose 而非代码，需改进 prompt engineering |
| 🔴 最高 | learnings 数据积累 | learnings 一直是空的，需要真正跑起来积累数据 |
| 🟡 次高 | 指标趋势跟踪 | 记录每次迭代的 metrics（TODO 数、重复率、测试覆盖率），画出趋势图 |
| 🟡 次高 | GitHub Issue 主动开单 | 发现产品问题后自动在 GitHub 开 Issue |
| 🟡 次高 | 主动通知 | 巡检结果主动推送到飞书/邮件，而不是等 Cron |
| 🟢 优化 | Cron 动态调整 | 根据项目活跃度动态调整巡检频率 |
| 🟢 优化 | 团队多人集成 | 支持唐僧/悟空等多个 agent 各自巡检各自的项目 |

---

## 相关项目

- [SoulForce](https://github.com/relunctance/soul-force) — AI Agent 记忆进化系统
- [hawk-bridge](https://github.com/relunctance/hawk-bridge) — OpenClaw 上下文记忆集成

---

## License

MIT

# Auto-Evolve v4.0

**四视角自动化巡检与迭代管理器**

> Make your skills continuously better -- automatically.

---

## 核心理念

**auto-evolve 不只是一个代码扫描工具，而是一个"像人一样思考"的巡检伙伴。**

每次巡检时，auto-evolve 模拟收到了一条飞书消息：

> "你觉得这个项目还有什么可以改进的？有什么不足？"

然后它会从四个视角逐一审视，形成真实的观点，而不是机械地报问题。

---

## 巡检工作流（v4.0）

```
auto-evolve 扫描项目
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Step 1: project-standard 项目类型判断               │
│  判断项目类型（Skill / CLI / Python库 / Web / 通用）  │
│  确定该类型适用的巡检标准 + 视角权重                 │
└─────────────────────┬───────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────┐
│  Step 2: 四视角巡检                                 │
│                                                     │
│  👤 USER    → user/user-perspective.md（标准）     │
│  📦 PRODUCT → product-requirements.md（标准）     │
│  🏗 PROJECT → project-inspection.md（标准）         │
│  ⚙️ TECH   → code-standards.md（标准）            │
└─────────────────────┬───────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────┐
│  Step 3: project-standard reference docs            │
│  作为评判标准，输出巡检报告                          │
└─────────────────────────────────────────────────────┘
```

### 与 project-standard 的关系

| 组件 | 职责 |
|------|------|
| **project-standard** | 提供项目分类标准 + 四视角框架 + reference docs（评判标准） |
| **auto-evolve** | 读取标准、执行巡检、记录 learnings、落地改进 |

---

## 四视角巡检框架

```
┌─────────────────────────────────────────────────────┐
│              auto-evolve 巡检框架 v4.0               │
├──────────────┬──────────────────┬───────────────────┤
│   用户视角     │     产品视角       │     项目视角        │    技术视角        │
│  "好用吗？"   │  "解决问题了吗？"   │   "运作得好吗？"    │   "代码健康吗？"   │
├──────────────┼──────────────────┼───────────────────┼──────────────────┤
│ CLI 设计      │ 功能完整性        │ learnings 闭环     │ 代码质量          │
│ 学习门槛      │ 承诺兑现度        │ 巡检历史          │ 架构设计          │
│ 错误提示      │ 痛点解决度        │ 配置合理性         │ 测试覆盖          │
│ 容错性        │ 用户反馈闭环       │ 迭代节奏          │ 依赖管理          │
│ 操作流程度    │ 文档与实际一致     │ 团队协作          │ 性能              │
│ ⬆️ 评判标准: user/user-perspective.md              │
└──────────────┴──────────────────┴───────────────────┴──────────────────┘
```

### 优先级：用户 > 产品 > 项目 > 技术

**为什么这样排序？**
- 用户体验是项目存在的根本
- 产品视角确保"说到做到"
- 项目视角确保"持续改进有闭环"
- 技术视角是基础，但不应该是主角

---

## 四视角详解

### 👤 用户视角（User Perspective）

**核心问题：这个工具用起来顺手吗？**

| 问什么 | 发现什么 |
|--------|---------|
| CLI 参数设计 | 参数名不直观、缺少默认值 |
| 学习门槛 | 新人上手要多久？文档够吗？ |
| 错误提示 | 报错是说人话还是说机器话？ |
| 容错性 | 某个环节失败了会怎样？ |
| 操作流程度 | 完成一个操作要几步？能否更简单？ |

**输出示例**：
> `[USER] Impact 0.7` — `--dry-run` 在 `review` 子命令下不可用，用户以为可以dry-run结果直接写了文件

### 📦 产品视角（Product Perspective）

**核心问题：这个项目声称解决什么，实际做到了吗？**

| 问什么 | 发现什么 |
|--------|---------|
| README 承诺 | README 里写的功能，实际做到了吗？ |
| 痛点解决度 | 文档里标记的 ❌ 痛点，哪些还没解决？ |
| 功能完整性 | 声称的 feature 是完整实现还是半成品？ |
| 文档一致性 | 文档和代码说的是同一件事吗？ |

**输出示例**：
> `[PRODUCT] Impact 0.8` — README 声称"LLM fallback 机制"，但代码里没有 fallback，一旦 API 失败整个工具直接失效

### 🏗 项目视角（Project Perspective）

**核心问题：这个项目的运作方式健康吗？**

| 问什么 | 发现什么 |
|--------|---------|
| learnings 闭环 | 上次发现的问题追踪了吗？learnings 有积累吗？ |
| 巡检历史 | 巡检了多少次？有形成迭代节奏吗？ |
| 配置合理性 | 配置项是否合理？有无过度配置？ |
| 依赖管理 | 依赖是否过多、过旧、有安全风险？ |

**输出示例**：
> `[PROJECT] Impact 0.5` — 上次巡检发现的问题（3个）在本次巡检时没有任何标记或追踪

### ⚙️ 技术视角（Tech Perspective）

**核心问题：代码本身健康吗？**

| 问什么 | 发现什么 |
|--------|---------|
| 代码质量 | 重复代码、长函数、坏味道 |
| 架构设计 | 模块间耦合是否合理？ |
| 测试覆盖 | 核心逻辑有测试吗？ |
| 性能 | 有无明显的性能问题？ |

**注意**：技术视角优先级最低，是"锦上添花"而不是"主角"。

---

## 巡检流程

```
收到消息："这个项目还有什么可以改进的？"

    ↓
┌──────────────────────────────────────┐
│  Step 1: project-standard 项目类型判断  │
│  · 判断项目类型（Skill / CLI / 库 / Web）│
│  · 确定视角权重（不同类型权重不同）       │
└──────────────────────────────────────┘
    ↓
┌──────────────────────────────────────┐
│  Step 2: 四视角巡检（并发）             │
│  · USER    → 参考 user-perspective.md │
│  · PRODUCT → 参考 product-requirements.md│
│  · PROJECT → 参考 project-inspection.md│
│  · TECH   → 参考 code-standards.md    │
└──────────────────────────────────────┘
    ↓
┌──────────────────────────────────────┐
│  Step 3: 优先级排序 + 报告             │
│  · 按视角分组                          │
│  · 按 Impact 排序                      │
│  · 引用 project-standard 标准做评判     │
└──────────────────────────────────────┘
```

---

## 巡检报告格式

```
📋 auto-evolve 巡检报告 — soul-force
生成时间: 2026-04-05 22:30

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 用户视角 ★★★★★
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. 🚨 Impact 0.7
     review 命令不支持 --dry-run，用户以为不会写文件
     结果直接修改了 SOUL.md
     → 建议：review 也支持 --dry-run，或在文档中明确说明

  2. ⚠️  Impact 0.5
     错误提示只有 "Error: something went wrong"
     用户无法判断是什么问题
     → 建议：分层错误提示，分清"配置错误"和"运行时错误"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 产品视角 ★★★★
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. 🚨 Impact 0.8
     README 承诺 "LLM fallback"，实际代码没有 fallback
     API 失败时工具直接失效
     → 建议：实现基于关键词的简单规则引擎作为 fallback

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏗 项目视角 ★★★
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. ⚠️  Impact 0.6
     learnings 历史没有被用于指导巡检优先级
     重复被拒绝的问题仍然反复出现
     → 建议：learnings 应影响巡检的发现排序

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️ 技术视角 ★★
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [opt] 🟡 duplicate_code: SoulForgeConfig 初始化重复 15 次
  [opt] 🟡 long_function: main() 154 行

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 行动建议
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  【立即处理】产品视角：实现 LLM fallback（影响最大）
  【本周处理】用户视角：review 支持 --dry-run
  【可选】    技术视角：提取公共初始化函数
```

---

## 命令

### scan

```bash
# 扫描所有配置的仓库
python3 auto-evolve.py scan

# 单仓库扫描
python3 auto-evolve.py scan --repo /path/to/repo

# 预览模式（不执行）
python3 auto-evolve.py scan --dry-run

# 指定回忆的记忆 persona
python3 auto-evolve.py scan --recall-persona master
```

---

### confirm / reject / approve

在 semi-auto 模式下确认或拒绝巡检发现。

```bash
python3 auto-evolve.py confirm
python3 auto-evolve.py reject 2 --reason "too risky"
python3 auto-evolve.py approve 1,3
```

---

### repo-add / repo-list

```bash
python3 auto-evolve.py repo-add ~/.openclaw/workspace/skills/hawk-bridge --type skill
python3 auto-evolve.py repo-list
```

---

### schedule

```bash
# 设置扫描间隔
python3 auto-evolve.py schedule --every 168

# 查看智能调度建议
python3 auto-evolve.py schedule --suggest
```

---

### learnings

查看学习历史（被拒绝/批准过的决策）。

```bash
python3 auto-evolve.py learnings
python3 auto-evolve.py learnings --type rejections
```

---

## 配置

`~/.auto-evolverc.json`

```json
{
  "mode": "semi-auto",
  "full_auto_rules": {
    "execute_low_risk": true,
    "execute_medium_risk": false,
    "execute_high_risk": false
  },
  "schedule_interval_hours": 168,
  "repositories": [
    {
      "path": "/path/to/repo",
      "type": "skill",
      "visibility": "public",
      "auto_monitor": true
    }
  ]
}
```

---

## LLM 集成

auto-evolve 使用 OpenClaw 配置的 LLM，无需单独 API key。

配置优先级：
1. 环境变量 `OPENAI_API_KEY` / `MINIMAX_API_KEY`
2. `openclaw config get llm`

---

## 迭代记录格式

```
.auto-evolve/
  .iterations/
    {id}/
      manifest.json       -- 元数据 + 发现列表
      plan.md            -- 执行计划
      pending-review.json -- 待审查项目
      report.md          -- 执行报告
      metrics.json       -- 迭代指标
```

# Auto-Evolve

**AI Agent 自我进化引擎 — 从"主人视角"持续追问"还有什么不足, 有哪些地方可以优化, 使用体验如何？", 然后行动。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://img.shields.io/badge/Python-3.10+-blue.svg)

> Your skills get smarter — automatically. Auto-Evolve v3.5 asks from the **master's perspective**, leverages LLM intelligence with **persona-aware memory context**, and evolves your tools with or without human oversight.

**English**: [README.md](README.md)

---

## 核心转变

**旧版本问：** "这段代码有重复吗？这个函数超过100行了吗？"
**v3.5 问：** "还有什么不足, 有哪些地方可以优化, 使用体验如何？"

这不是代码质量扫描器——这是**从主人视角出发的持续改进伙伴**。

---

## 核心功能

### 🎯 从主人视角追问

每次巡检，Auto-Evolve 都会带着以下上下文来问问题：

- **主人背景**：从 `SOUL.md`、`USER.md`、`IDENTITY.md` 读取主人的价值观、偏好、项目定位
- **主人偏好**：从 OpenClaw SQLite 记忆 + hawk-bridge LanceDB 召回主人曾经表达过的好恶
- **历史学习**：从 `learnings/` 读取之前拒绝/批准过的改动，避免重复踩坑

```
"还有什么不足, 有哪些地方可以优化, 使用体验如何？"

主人背景：主人追求自动化，喜欢简洁直接...
主人偏好：主人不喜欢生成 test 文件...
学习历史：主人拒绝了 3 次 missing_test 类型的改动...
```

### 🧠 Persona 感知记忆系统

| 记忆源 | 优先级 | 说明 |
|--------|--------|------|
| OpenClaw SQLite | 优先 | `memory/{persona}.sqlite`，结构化，可信 |
| hawk-bridge LanceDB | 补充 | 向量语义搜索，按 persona 隔离 |

```bash
# 默认：以当前 agent persona 巡检
python3 scripts/auto-evolve.py scan --dry-run

# 唐僧召回主人的全部记忆
python3 scripts/auto-evolve.py scan --dry-run --recall-persona master

# 只用 OpenClaw SQLite
python3 scripts/auto-evolve.py scan --dry-run --memory-source openclaw

# 两个都读，合并结果
python3 scripts/auto-evolve.py scan --dry-run --memory-source both
```

### 📊 真正的产品洞察（而非代码问题列表）

输出示例：
```
🎯 Product Evolution Insights (from 4 finding(s)):

  1. 🚫 [STOP_DOING]
     missing_test 优化被主人拒绝了 3 次
     Impact: ████████░░ 0.8
     → 停止自动生成 test 文件
     ⏱ 每次生成都被拒，白白浪费 LLM 调用
     File: auto-evolve config

  2. 😤 [USER_COMPLAINT]
     这个功能使用起来太麻烦了，主人得手动做3步
     Impact: █████░░░░░ 0.5
     → 把这个流程自动化
     File: soul-force/scripts/soulforge.py
```

### ⚡ 真实质量门槛

不只是 `py_compile` 语法检查：
- Python：`pytest --cov` 实际运行测试
- JavaScript/TypeScript：`jest` 实际运行测试
- 失败则自动回滚

### 🔍 跨文件结构重复检测

不只是检测完全相同的字符串——检测**结构相似**的函数：
- 不同文件中相似的函数签名
- 重复的 if/else 块、try/catch 块
- 用 LLM 分析消除重复的具体方案

---

## 快速开始

### 安装

```bash
# Via ClawHub（推荐）
clawhub install auto-evolve

# Via Git
git clone https://github.com/relunctance/auto-evolve.git \
  ~/.openclaw/workspace/skills/auto-evolve
```

### 配置

```bash
# 添加要巡检的仓库
python3 scripts/auto-evolve.py repo-add ~/.openclaw/workspace/skills/soul-force \
  --type skill --monitor

# 设置为全自动化模式
python3 scripts/auto-evolve.py set-mode full-auto

# 每 10 分钟巡检一次
python3 scripts/auto-evolve.py schedule --every 10
```

### 运行

```bash
# 巡检 + 预览（不执行）
python3 scripts/auto-evolve.py scan --dry-run

# 巡检 + 执行（full-auto 模式下）
python3 scripts/auto-evolve.py scan

# 以主人视角召回记忆巡检
python3 scripts/auto-evolve.py scan --dry-run \
  --recall-persona master --memory-source both
```

---

## 架构

```
巡检触发
    │
    ▼
┌─────────────────────────────────────────────┐
│  Step 1: 检测当前 persona                  │
│  detect_persona() → main/tseng/wukong/...   │
└────────────────────┬──────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Step 2: 确定 workspace 路径                │
│  main → ~/.openclaw/workspace/            │
│  tseng → ~/.openclaw/workspace-tseng/     │
└────────────────────┬──────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Step 3: 读取主人上下文                   │
│  SOUL.md / USER.md / IDENTITY.md / MEMORY │
└────────────────────┬──────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Step 4: 召回记忆（按 persona）            │
│  OpenClaw SQLite (primary)                │
│  + hawk-bridge LanceDB (supplement)      │
└────────────────────┬──────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Step 5: LLM 产品级分析                   │
│  "还有什么不足, 有哪些地方可以优化,        │
│   使用体验如何？"                          │
└─────────────────────────────────────────────┘
```

---

## 命令

| 命令 | 说明 |
|------|------|
| `scan` | 巡检（加 `--dry-run` 预览） |
| `scan --recall-persona master` | 以主人记忆巡检 |
| `scan --memory-source openclaw` | 指定记忆源 |
| `confirm` | 确认并执行待处理变更 |
| `approve / reject` | 批准/拒绝变更并记录原因 |
| `set-mode full-auto` | 全自动化模式 |
| `set-rules --low true` | 设置自动执行规则 |
| `schedule --every 60` | 设置巡检周期 |
| `learnings` | 查看学习历史 |
| `rollback` | 回滚到上一版本 |
| `repo-add / repo-list` | 管理巡检仓库 |

---

## CLI 参数

```
scan:
  --dry-run              预览，不执行
  --recall-persona       召回谁的记忆（main/tseng/wukong/bajie/bailong/master）
  --memory-source        记忆源（auto/openclaw/hawkbridge/both）
```

---

## 安全机制

- **语法门槛**：Python `py_compile` + pytest；JS/TS jest
- **回滚**：每次执行后记录 git revert，一键回滚
- **Privacy**：closed 仓库代码不外泄
- **Learnings 过滤**：learnings 中被拒绝的改动不再重复尝试

---

## 相关项目

- [SoulForce](https://github.com/relunctance/soul-force) — AI Agent 记忆进化系统
- [hawk-bridge](https://github.com/relunctance/hawk-bridge) — OpenClaw 上下文记忆集成

---

## License

MIT

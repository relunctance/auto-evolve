# Auto-Evolve

**LLM 驱动的自动化技能迭代管理器。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/relunctance/auto-evolve)](https://github.com/relunctance/auto-evolve/stargazers)

> 让你的技能越来越聪明——自动化迭代。Auto-Evolve 扫描你的代码，利用 LLM 智能生成改进建议，在有人值守或无人值守的情况下都能进化你的工具。

**English Documentation**: [README.md](README.md)

---

## 为什么需要 Auto-Evolve？

大多数工具会随着时间退化。代码变得混乱、文档脱节、TODO 堆积、测试被忽视。你知道需要修复，但：

- 手动去做太繁琐
- 无法判断优先级
- 没有记录谁改了什么、为什么改

**Auto-Evolve 解决了这些问题。** 它持续监控、建议、执行改进——全程透明、可控。

---

## 核心功能

### 🔍 智能扫描
- 检测 TODO/FIXME/HACK/XXX 注释
- 查找重复代码模式
- 识别过长函数
- 检查测试覆盖率
- **LLM 驱动分析**，理解上下文，给出真正有价值的建议

### 🎯 智能优先级
- 计算优先级分：`P = (价值 × 0.5) / (风险 × 成本)`
- 改动前显示依赖影响
- 按收益/努力比排序建议

### ⚡ 两种运行模式
- **半自动**：扫描、建议、等待确认
- **全自动**：按规则自动执行低风险改动

### 🔒 完整审计跟踪
- 每次迭代都有记录
- 前后指标对比
- 可回滚到任意历史状态
- 学习你的批准和拒绝习惯

### 🌐 分支 + PR 工作流
- 高风险改动走独立分支
- GitHub PR 附带完整上下文
- 尽可能自动解决冲突
- 相似小改动合并为一个 PR

### 📊 效果追踪
- 测量：已解决 TODO、已修复 lint 错误、覆盖率变化
- 对比历次迭代的指标
- 追踪自动 vs 人工贡献比例

---

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/relunctance/auto-evolve.git ~/.openclaw/workspace/skills/auto-evolve

# 进入目录
cd ~/.openclaw/workspace/skills/auto-evolve
```

### 基本使用

```bash
# 扫描所有已配置的仓库
python3 scripts/auto-evolve.py scan

# 预览（不执行）
python3 scripts/auto-evolve.py scan --dry-run

# 半自动模式：确认并执行待处理变更
python3 scripts/auto-evolve.py confirm

# 查看迭代历史
python3 scripts/auto-evolve.py log

# 回滚到某个版本
python3 scripts/auto-evolve.py rollback --to VERSION
```

---

## 配置

Auto-Evolve 使用 `~/.auto-evolverc.json` 配置文件：

```json
{
  "mode": "semi-auto",
  "repositories": [
    {
      "path": "~/.openclaw/workspace/skills/soul-force",
      "type": "skill",
      "visibility": "public",
      "auto_monitor": true
    },
    {
      "path": "~/projects/closed-project",
      "type": "project",
      "visibility": "closed",
      "auto_monitor": true,
      "risk_override": {
        "code_changes": "medium"
      }
    }
  ],
  "full_auto_rules": {
    "execute_low_risk": true,
    "execute_medium_risk": false,
    "execute_high_risk": false
  },
  "schedule_interval_hours": 168
}
```

### 添加仓库

```bash
# 添加技能仓库
python3 scripts/auto-evolve.py repo-add ~/my-skill --type skill --monitor

# 添加规范仓库
python3 scripts/auto-evolve.py repo-add ~/team-norms --type norms --monitor

# 列出已配置的仓库
python3 scripts/auto-evolve.py repo-list
```

---

## 仓库类型

| 类型 | 说明 | 默认风险 |
|------|------|---------|
| `skill` | OpenClaw 技能 | 低 |
| `norms` | 团队规范仓库 | 低 |
| `project` | 开源项目 | 中 |
| `closed` | 私有/闭源项目 | 中 |

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    Auto-Evolve                           │
├─────────────────────────────────────────────────────────┤
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐   │
│  │  Scanner │──▶│ Analyzer │──▶│  Prioritizer     │   │
│  │  (git + │   │ (LLM +   │   │  (P = v/r×c)    │   │
│  │   regex)│   │ patterns)│   │                   │   │
│  └──────────┘   └──────────┘   └──────────────────┘   │
│         │              │                  │              │
│         ▼              ▼                  ▼              │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Executor                            │    │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────┐ │    │
│  │  │ Low Risk  │  │ Medium/   │  │ High Risk│ │    │
│  │  │ (direct)  │  │ High      │  │ (PR)    │ │    │
│  │  └────────────┘  └────────────┘  └──────────┘ │    │
│  └─────────────────────────────────────────────────┘    │
│                          │                              │
│                          ▼                              │
│  ┌─────────────────────────────────────────────────┐  │
│  │              Audit Trail                          │  │
│  │   catalog.json │ manifest.json │ metrics.json       │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 命令参考

| 命令 | 说明 |
|------|------|
| `scan` | 扫描并分析仓库 |
| `confirm` | 确认并执行待处理变更 |
| `approve` | 批准特定变更（支持 `--reason`） |
| `reject` | 拒绝变更并记录原因 |
| `set-mode` | 切换半自动 / 全自动模式 |
| `set-rules` | 配置全自动执行规则 |
| `schedule` | 设置定期扫描 |
| `learnings` | 查看批准/拒绝历史 |
| `rollback` | 回滚到历史迭代 |
| `repo-add` | 添加要监控的仓库 |
| `repo-list` | 列出所有仓库 |
| `release` | 创建 GitHub Release（v3+） |

完整命令参考：[SKILL.md](SKILL.md)

---

## 隐私与安全

### 隐私级别

标记为 `visibility: "closed"` 的仓库享有特殊处理：
- 报告中代码内容脱敏
- 文件路径替换为内容哈希
- 通知中不包含原始代码

### 质量门槛

每个自动执行的变更必须通过：
1. **语法检查** — Python 文件必须能编译
2. **Git 状态** — 无未跟踪的敏感文件
3. **文档同步** — 需要时更新 SKILL.md

### 回滚

每次迭代都有记录。回滚只需一条命令：

```bash
auto-evolve rollback --to v2.2.0
# 或 cherry-pick 单个变更
auto-evolve rollback --to v2.2.0 --item 3
```

---

## 相关项目

- [SoulForce](https://github.com/relunctance/soul-force) — AI 智能体记忆进化系统
- [hawk-bridge](https://github.com/relunctance/hawk-bridge) — OpenClaw 上下文记忆集成

---

## 贡献指南

贡献是受欢迎的！请在提交 PR 前阅读我们的指南。

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改并附上清晰信息
4. 推送到分支：`git push origin feature/amazing-feature`
5. 发起 Pull Request

---

## 许可证

MIT 许可证 — 参见 [LICENSE](LICENSE)

---

## English Version

For English documentation, see [README.md](README.md)

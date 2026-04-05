# Auto-Evolve

**让项目自己学会进化——主人安装后，项目会越用越好。**

> 你安装一次，它在后台运行。项目自动变好——不需要你反复手动介入。

**English**: [README.md](README.md)

---

## 一句话定位

**Auto-Evolve 让项目自己学会进化。** 主人安装一次，之后项目会自己发现问题、自己改进、自己积累经验——不需要主人反复手动介入。

---

## 它解决了什么问题？

**没有 Auto-Evolve 时：**
- 项目代码随着时间腐烂（TODO 堆积、重复代码扩散、测试覆盖率下降）
- 每次功能迭代都要主人花时间做代码审查
- 团队成员各自为政，没有统一的改进节奏
- 好的实践无法持续积累

**有了 Auto-Evolve 后：**
- 项目每 N 分钟自动扫描一次，发现问题立刻处理
- 改动自动记录到 `learnings/`（项目的记忆，不会重复犯同一个错）
- 版本控制——每次改动都有 git 历史，可回滚
- 主人只需要关注真正需要判断的高风险决策

---

## 核心特性

### 🚀 安装即用，无需人工干预

```bash
# 安装
clawhub install auto-evolve

# 配置要巡检的项目
python3 scripts/auto-evolve.py repo-add ~/.openclaw/workspace/skills/soul-force \
  --type skill --monitor

# 启动全自动化
python3 scripts/auto-evolve.py set-mode full-auto
python3 scripts/auto-evolve.py schedule --every 10
```

之后项目会自动进化，主人只需要：
- 偶尔收到飞书推送："这个改动被拒绝了，因为..."
- 真正重要的高风险决策才会来问你

### 📈 版本控制的进化历史

每次改动都有 git commit：
```
commit a3f8b12
auto: [auto-evolve] 消除 duplicate_code in scripts/lua_def_file.py

commit b2c9d34
auto: 删除 3 个空的 TODO 注释

commit c7e1f88
auto: 消除 duplicate_code in build/ci/test-configs.py
```

- 所有改动可审计、可回滚
- 进化历史清晰可见
- 不满意？`auto-evolve rollback` 一键回退

### 🧠 learnings——项目的记忆

Auto-Evolve 把每次执行结果记录到 `learnings/` 目录：

```
.learnings/
├── approvals.json    # 成功执行过的改动
├── rejections.json   # 被拒绝/失败的改动及原因
└── metrics/          # 每次迭代的指标趋势
```

**learnings 的价值：**
- 同一个错误不会犯两次
- 知道什么改动主人喜欢，什么改动主人讨厌
- 随着时间积累，Auto-Evolve 越来越懂这个项目

**依赖 soul-force 才能开启完整 learnings 功能：**
```bash
# 安装 soul-force（提供 learnings 分析 + 每日记忆总结）
clawhub install soul-force
```

### 🧬 依赖的 Skills

Auto-Evolve 本身只做巡检和执行。完整能力需要配合以下 skills：

| Skill | 作用 | 是否必需 |
|--------|-------|---------|
| **soul-force** | 提供 learnings 分析、每日记忆总结 | 推荐安装 |
| **hawk-bridge** | 提供向量语义记忆，按 persona 隔离召回主人偏好 | 可选 |
| **auto-evolve** | 巡检引擎 + 执行器 | 必需 |

### 🌐 Persona 感知的团队巡检

不同 agent 可以巡检不同的项目：

```bash
# 悟空巡检自己的后端项目
python3 scripts/auto-evolve.py scan --recall-persona wukong --dry-run

# 唐僧巡检 soul-force
python3 scripts/auto-evolve.py scan --recall-persona tseng --dry-run

# 八戒巡检前端项目
python3 scripts/auto-evolve.py scan --recall-persona bajie --dry-run
```

每个 agent 的 workspace 隔离，learnings 互不影响。

---

## 工作原理

```
主人安装 auto-evolve
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  每 N 分钟，cron 触发 scan                              │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │  1. 读取项目当前状态                              │   │
│  │     - 代码中有多少 TODO？                       │   │
│  │     - 有多少重复代码？                          │   │
│  │     - 测试覆盖率是多少？                        │   │
│  └─────────────────────┬──────────────────────────────┘   │
│                        ▼                                 │
│  ┌────────────────────────────────────────────────┐   │
│  │  2. 读取 learnings（项目记忆）                  │   │
│  │     - 之前哪些改动成功了？                      │   │
│  │     - 哪些改动被拒绝了？原因是什么？            │   │
│  │     - 主人偏好什么风格？                      │   │
│  └─────────────────────┬──────────────────────────────┘   │
│                        ▼                                 │
│  ┌────────────────────────────────────────────────┐   │
│  │  3. 主人视角的判断                            │   │
│  │     "还有什么不足, 有哪些地方可以优化,          │   │
│  │      使用体验如何？"                            │   │
│  └─────────────────────┬──────────────────────────────┘   │
│                        ▼                                 │
│  ┌────────────────────────────────────────────────┐   │
│  │  4. 决策 + 执行                                │   │
│  │     低风险 → 自动执行 → 记录到 learnings        │   │
│  │     中风险 → 开 PR → 等确认                    │   │
│  │     高风险 → 跳过 → 通知主人                    │   │
│  └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 完整安装（推荐）

```bash
# 1. 安装 auto-evolve（核心引擎）
clawhub install auto-evolve

# 2. 安装 soul-force（提供 learnings + 记忆进化）
clawhub install soul-force

# 3. 安装 hawk-bridge（可选，提供向量语义记忆）
clawhub install hawk-bridge

# 4. 配置要巡检的项目
python3 scripts/auto-evolve.py repo-add ~/.openclaw/workspace/skills/soul-force \
  --type skill --monitor

# 5. 设置自动巡检
python3 scripts/auto-evolve.py set-mode full-auto
python3 scripts/auto-evolve.py schedule --every 10
```

### 单独使用

```bash
# 只装 auto-evolve（无 learnings 能力）
clawhub install auto-evolve

# 只做预览，不执行任何改动
python3 scripts/auto-evolve.py scan --dry-run
```

---

## 巡检输出示例

```
🔍 Auto-Evolve Scanner [full-auto]
==================================================

📊 项目状态:
   TODO: 12 → 9  (-3 已解决)
   重复代码: 8 → 5  (-3 已解决)
   测试覆盖率: 68% → 71%  (+3%)

🎯 产品洞察:
   🚫 [停止做] 主人拒绝了 3 次生成 test 文件 → 停止尝试
   😤 [用户体验] 这个配置流程太麻烦，主人得手动做 5 步

🔧 自动执行:
   ✅ duplicate_code: scripts/lua_def_file.py (P=0.68)
   ✅ todo_cleanup: 3 个空 TODO 已删除
   ⏭  等待确认: soulforge.py 长函数 127行

💾 Learnings: 3 个批准, 0 个拒绝 已记录
```

---

## 命令

| 命令 | 说明 |
|------|------|
| `scan` | 巡检所有项目 |
| `scan --dry-run` | 预览模式（不执行） |
| `scan --recall-persona master` | 召回主人记忆巡检 |
| `confirm` | 确认并执行待处理改动 |
| `approve / reject` | 批准/拒绝（记录到 learnings） |
| `set-mode full-auto` | 全自动化模式 |
| `learnings` | 查看项目记忆 |
| `rollback` | 回滚上一版本 |
| `schedule --every 10` | 每 10 分钟自动巡检 |

---

## 安全机制

- **版本控制**：所有改动有 git 历史，可回滚
- **质量门槛**：Python pytest / JS jest 实际测试通过后才算成功
- **learnings 过滤**：被拒绝的改动不会重复尝试
- **隐私保护**：closed 仓库代码不外泄
- **权限分离**：敏感操作需要主人确认

---

## 依赖说明

Auto-Evolve 是一个巡检引擎，以下 skills 提供额外能力：

| Skill | 版本 | 说明 |
|-------|------|------|
| auto-evolve | ≥3.5 | **必需**。核心巡检 + 执行引擎 |
| soul-force | ≥2.2 | 推荐。提供 learnings 分析、每日记忆总结 |
| hawk-bridge | any | 可选。向量语义记忆，按 persona 隔离 |

---

## 相关项目

- [SoulForce](https://github.com/relunctance/soul-force) — AI Agent 记忆进化系统
- [hawk-bridge](https://github.com/relunctance/hawk-bridge) — OpenClaw 上下文记忆集成

---

## License

MIT

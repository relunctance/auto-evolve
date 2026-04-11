# auto-evolve Roadmap — 自我进化架构 L1+L4 层补全

## 背景

auto-evolve 是自我进化闭环的 L1（巡检层）和 L4（验证层）。当前只有 scan mode，需要补全 inspect/verify 模式分离，以及与 soul-force、hawk-bridge 的闭环接口。

---

## 当前能力 vs 架构需求差距

| 功能 | 当前 | 架构需求 | 状态 |
|------|------|----------|------|
| 巡检扫描 | ✅ scan mode | ✅ inspect mode | **需分离** |
| 修复验证 | ❌ 无 | ✅ verify mode | **缺失** |
| 标准 JSON 输出 | ❌ markdown 报告 | ✅ JSON 供 soul-force 读 | **缺失** |
| hawk-bridge 写回 | ❌ 只读 | ✅ verify 结果写回 L0 | **缺失** |
| L0→L1 自动触发 | ❌ 手动 | ✅ hawk-dream 后触发 | **缺失** |
| learnings 标准 issue_id | ❌ 自由文本 | ✅ CODE-xxx 从 project-standard | **缺失** |
| 多项目聚合扫描 | ❌ 单 repo | ✅ 全局健康度报告 | **缺失** |

---

## 待实现功能

### P0 — 核心闭环功能

#### 1. inspect / verify 模式分离

**目标**：L1 inspect（首次巡检）和 L4 verify（验证修复）是两个独立阶段

**实现**：
```bash
# L1：首次巡检
auto-evolve inspect --repo /path/to/repo
# 输出：~/.hawk/inspect-reports/{run_id}.json

# L4：验证修复
auto-evolve verify --repo /path/to/repo --baseline-run-id inspect_xxx
# 输出：~/.hawk/verify-reports/{run_id}.json
```

---

#### 2. 标准 JSON 输出

**目标**：输出标准 JSON 格式供 soul-force 读取

**JSON 格式**：
```json
{
  "run_id": "inspect_20260412",
  "baseline_run_id": null,
  "timestamp": "2026-04-12T00:00:00Z",
  "repo": "/path/to/repo",
  "results": [
    {
      "issue_id": "CODE-045",
      "title": "API 错误必须返回统一格式",
      "perspective": "tech",
      "severity": "high",
      "status": "open",
      "evidence": "src/api/users.py:23 未返回统一错误格式",
      "fix_suggestion": "使用统一的 ErrorResponse 类"
    }
  ],
  "summary": {
    "total": 12,
    "critical": 1,
    "high": 4,
    "medium": 5,
    "low": 2
  }
}
```

---

#### 3. hawk-bridge 写回

**目标**：verify 结果写回 L0，影响记忆的 reliability

**实现**：
```python
# verify 完成后
if result['status'] == 'solved':
    hawk_bridge.update_memory(
        filter={'source': 'auto-evolve', 'issue_id': issue_id},
        updates={'reliability': 0.95, 'verified_at': now}
    )
else:
    hawk_bridge.update_memory(
        filter={'source': 'auto-evolve', 'issue_id': issue_id},
        updates={'reliability': 0.3, 'failure_count': +1}
    )
```

---

### P1 — 闭环触发

#### 4. L0→L1 自动触发

**目标**：hawk-dream 完成后自动触发 inspect

**触发条件**：
- hawk-dream 检测到 ≥5 条新记忆
- 调用 `auto-evolve inspect --repo {path}`

**配置**：
```yaml
hawk:
  autoInspect:
    enabled: true
    minNewMemories: 5
```

---

#### 5. learnings 标准 issue_id

**目标**：每次发现从 project-standard 分配标准 issue_id

**实现**：
- 每次 scan 发现问题 → 映射到 project-standard 的 check ID
- approvals.json / rejections.json 用 issue_id 索引
- 例：`CODE-045: API 错误统一格式` 被拒绝 → 记录 `CODE-045`

---

### P2 — 生态功能

#### 6. 多项目聚合扫描

**目标**：团队多项目统一健康度报告

**命令**：
```bash
auto-evolve scan-all \
  --repos /path/to/repo1,/path/to/repo2,/path/to/repo3
```

**输出**：
```json
{
  "total_projects": 3,
  "overall_health_score": 0.72,
  "projects": [
    {"name": "repo1", "score": 0.85, "critical": 0},
    {"name": "repo2", "score": 0.60, "critical": 2},
    {"name": "repo3", "score": 0.78, "critical": 0}
  ],
  "recommended_action": "优先修复 repo2 的 2 个 critical 问题"
}
```

---

## 实现顺序建议

```
Step 1: inspect/verify 模式分离
Step 2: 标准 JSON 输出（先有结构，L4 才能跑通）
Step 3: learnings issue_id 标准化
Step 4: hawk-bridge 写回
Step 5: L0→L1 自动触发
Step 6: 多项目聚合扫描
```

---

## 参考架构

```
L0 hawk-bridge
    ↓ 新记忆 ≥5 条
hawk-dream hook
    ↓ 自动触发
auto-evolve inspect
    ↓ 输出 inspect-reports/{run_id}.json
L2 tangseng-brain
    ↓ 派发任务
L3 悟空/八戒修复
    ↓ PR 合并
auto-evolve verify
    ↓ 输出 verify-reports/{run_id}.json
    ↓ 写回 hawk-bridge
L5 soul-force
    ↓ 读取验证结果 → 进化
```

---

## 细节功能补全（v2.x）

### 7. 增量扫描

**目标**：只扫描距上次有变更的文件，节省 token

**实现**：
- 记录上次 scan 的文件列表 + 最后修改时间
- 本次只扫变更文件 + 新增文件
- `auto-evolve inspect --incremental`

---

### 8. 扫描取消机制

**目标**：发现过多 critical 时中止，避免资源浪费

**实现**：
```python
if critical_count > 10:
    print("🚨 Critical 问题过多（{critical_count}），建议先修阻断性问题")
    raise ScanAbortException("Too many critical findings")
```

---

### 9. Verify 对比基准选择

**目标**：可指定 compare-run-id，不只用上一次

**实现**：
```bash
auto-evolve verify --repo . --baseline-run-id inspect_20260401
# 对比 2026-04-01 的 inspect 结果
```

---

### 10. 回归通知

**目标**：verify 时只有退化了才通知，做好了不打扰

**实现**：
- verify 结果和上次比
- 只有 `solved_count < previous_solved_count` 或 `new_critical > 0` 时才通知
- 做好了 → 静默
- 退化了 → 通知唐僧

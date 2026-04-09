# policy.py - 轻量级规则引擎
# 
# 设计原则：
# 1. 简单 if/else 规则表，易于理解和维护
# 2. 基于 core.py 已有的 RiskLevel 体系
# 3. 支持规则覆盖（override）机制
# 4. 可插拔：规则可独立于主流程测试

import re
from dataclasses import dataclass, field
from typing import Optional
from core import RiskLevel, ChangeItem, ChangeCategory

# ============================================================================
# 规则配置表
# ============================================================================

# ---- 风险分类规则 -------------------------------------------------------

RISK_PATTERNS = {
    # 高风险文件路径（修改这些需要额外确认）
    "high_risk_paths": [
        r"\.git/hooks/",
        r"\.github/workflows/",
        r"secrets\.yaml",
        r"password",
        r"credential",
    ],
    
    # 低风险文件路径（可直接执行）
    "low_risk_paths": [
        r"README.*\.md$",
        r"CHANGELOG\.md$",
        r"\.gitignore$",
        r"\.md$",                    # 所有 markdown 文档
        r"comments?/",              # 注释相关
        r"\.yml/.*\.md$",           # yml 子目录的 markdown
    ],
    
    # 高风险操作
    "high_risk_operations": [
        "delete",
        "remove",
        "drop",
        "truncate",
        "rm ",
        "rmdir",
    ],
    
    # 必须审批的操作
    "require_approval_operations": [
        "publish",
        "push",
        "commit",
        "merge",
        "delete_branch",
        "close_issue",
        "create_pr",
    ],
}

# ---- 偏离检测规则 -------------------------------------------------------

TRACKING_RULES = {
    "max_tool_calls": 10,          # 单次任务最大 tool 调用数
    "max_loops_same_tool": 3,     # 同一 tool 连续调用阈值
    "off_topic_threshold": 0.5,   # 偏离度阈值（0-1）
    "empty_result_threshold": 3,  # 连续空结果次数上限
}

# ---- 风险级别对应的处理策略 --------------------------------------------

RISK_POLICY = {
    RiskLevel.LOW: {
        "auto_execute": True,
        "require_approval": False,
        "notify_after": True,
        "commit_prefix": "auto:",
    },
    RiskLevel.MEDIUM: {
        "auto_execute": False,
        "require_approval": True,    # 需人工审批
        "notify_after": True,
        "commit_prefix": "review:",
    },
    RiskLevel.HIGH: {
        "auto_execute": False,
        "require_approval": True,   # 必须人工审批
        "notify_after": True,
        "commit_prefix": "pr:",
        "create_branch": True,
    },
    RiskLevel.CRITICAL: {
        "auto_execute": False,
        "require_approval": True,
        "require_signed_commit": True,
        "notify_before": True,
        "commit_prefix": "critical:",
        "create_branch": True,
    },
}

# ============================================================================
# Policy 决策结果
# ============================================================================

@dataclass
class PolicyDecision:
    """规则引擎决策结果"""
    allowed: bool              # 是否允许执行
    risk_level: RiskLevel      # 判定风险级别
    requires_approval: bool    # 是否需要审批
    reason: str                # 决策原因
    suggestions: list[str] = field(default_factory=list)  # 改进建议
    override_applied: bool = False  # 是否应用了 override

@dataclass
class TrackingState:
    """追踪状态（用于检测偏离）"""
    tool_call_count: int = 0
    consecutive_empty: int = 0
    last_tool: str = ""
    last_tool_sequence: int = 0  # 同一 tool 连续调用次数
    off_topic_score: float = 0.0
    history: list[str] = field(default_factory=list)  # tool 调用历史
    
    def record_tool(self, tool_name: str, has_result: bool):
        self.tool_call_count += 1
        self.history.append(tool_name)
        
        # 检测连续空结果
        if not has_result:
            self.consecutive_empty += 1
        else:
            self.consecutive_empty = 0
        
        # 检测同一 tool 循环调用
        if tool_name == self.last_tool:
            self.last_tool_sequence += 1
        else:
            self.last_tool_sequence = 1
            self.last_tool = tool_name

# ============================================================================
# 核心规则函数
# ============================================================================

def classify_risk(item: ChangeItem) -> RiskLevel:
    """
    根据 ChangeItem 的特征分类风险级别
    规则顺序：override > 高风险路径 > 低风险路径 > 默认
    """
    file_path = item.file_path.lower()
    description = item.description.lower()
    
    # 1. 检查是否命中高风险路径
    for pattern in RISK_PATTERNS["high_risk_paths"]:
        if re.search(pattern, file_path, re.IGNORECASE):
            return RiskLevel.HIGH
    
    # 2. 检查是否命中高风险操作
    for pattern in RISK_PATTERNS["high_risk_operations"]:
        if re.search(pattern, description, re.IGNORECASE):
            return RiskLevel.HIGH
    
    # 3. 检查是否命中低风险路径
    for pattern in RISK_PATTERNS["low_risk_paths"]:
        if re.search(pattern, file_path, re.IGNORECASE):
            return RiskLevel.LOW
    
    # 4. 根据 change category 判断
    if item.category == ChangeCategory.DELETED:
        return RiskLevel.HIGH
    elif item.category == ChangeCategory.ADDED:
        return RiskLevel.MEDIUM
    elif item.category == ChangeCategory.MODIFIED:
        # 修改操作默认 MEDIUM，除非是文档
        return RiskLevel.MEDIUM
    
    # 5. 默认风险级别
    return item.risk

def check_approval_required(item: ChangeItem) -> bool:
    """检查是否需要人工审批"""
    file_path = item.file_path.lower()
    description = item.description.lower()
    
    # 高风险操作必须审批
    for pattern in RISK_PATTERNS["require_approval_operations"]:
        if re.search(pattern, description, re.IGNORECASE):
            return True
    
    # 高风险文件必须审批
    for pattern in RISK_PATTERNS["high_risk_paths"]:
        if re.search(pattern, file_path, re.IGNORECASE):
            return True
    
    # 中高风险以上都需要审批
    risk = classify_risk(item)
    if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return True
    
    return False

def apply_policy(item: ChangeItem) -> PolicyDecision:
    """
    应用规则策略，返回决策结果
    """
    risk_level = classify_risk(item)
    policy = RISK_POLICY[risk_level]
    
    requires_approval = (
        check_approval_required(item) or 
        policy["require_approval"]
    )
    
    # 生成建议
    suggestions = []
    if risk_level == RiskLevel.HIGH:
        suggestions.append("建议创建分支 + PR 流程")
        suggestions.append("执行前请确认变更范围")
    elif requires_approval:
        suggestions.append("请在 approve 阶段确认")
    
    return PolicyDecision(
        allowed=True,  # 规则不拦截，只标记需要审批
        risk_level=risk_level,
        requires_approval=requires_approval,
        reason=f"风险级别: {risk_level.value}, {'需要审批' if requires_approval else '可直接执行'}",
        suggestions=suggestions,
    )

# ============================================================================
# 偏离检测
# ============================================================================

def check_off_track(state: TrackingState, original_goal: str, current_action: str) -> tuple[bool, str]:
    """
    检测是否偏离目标
    返回: (is_off_track, reason)
    """
    # 1. 检查 tool 调用次数超限
    if state.tool_call_count > TRACKING_RULES["max_tool_calls"]:
        return True, f"已超过最大 tool 调用次数 ({TRACKING_RULES['max_tool_calls']})"
    
    # 2. 检查同一 tool 循环调用
    if state.last_tool_sequence > TRACKING_RULES["max_loops_same_tool"]:
        return True, f"检测到 tool '{state.last_tool}' 被重复调用 {state.last_tool_sequence} 次，可能陷入循环"
    
    # 3. 检查连续空结果
    if state.consecutive_empty > TRACKING_RULES["empty_result_threshold"]:
        return True, f"连续 {state.consecutive_empty} 次无有效结果，可能已偏离目标"
    
    return False, ""

def should_interrupt(state: TrackingState, original_goal: str, current_action: str) -> bool:
    """
    判断是否应该中断当前执行
    """
    is_off, reason = check_off_track(state, original_goal, current_action)
    return is_off

# ============================================================================
# 规则覆盖机制
# ============================================================================

@dataclass
class PolicyOverride:
    """规则覆盖配置"""
    path_pattern: str          # 路径匹配模式
    risk_level: Optional[RiskLevel] = None
    require_approval: Optional[bool] = None
    
# 项目级 override 配置（可在外部传入）
OVERRIDE_LIST: list[PolicyOverride] = []

def apply_override(item: ChangeItem, overrides: list[PolicyOverride] = None) -> PolicyDecision:
    """
    应用 override 规则，覆盖默认决策
    """
    global OVERRIDE_LIST
    
    if overrides is None:
        overrides = OVERRIDE_LIST
    
    for override in overrides:
        if re.match(override.path_pattern, item.file_path):
            # 找到匹配的 override
            base_decision = apply_policy(item)
            
            if override.risk_level is not None:
                base_decision.risk_level = override.risk_level
            if override.require_approval is not None:
                base_decision.requires_approval = override.require_approval
            
            base_decision.override_applied = True
            base_decision.reason += f" [override: {override.path_pattern}]"
            
            return base_decision
    
    return apply_policy(item)

# ============================================================================
# 外部调用入口
# ============================================================================

def evaluate(item: ChangeItem, overrides: list[PolicyOverride] = None) -> PolicyDecision:
    """
    评估单个 ChangeItem 的策略决策（外部入口）
    """
    return apply_override(item, overrides)

def evaluate_batch(items: list[ChangeItem], overrides: list[PolicyOverride] = None) -> dict[int, PolicyDecision]:
    """
    批量评估，返回 {item_id: decision} 字典
    """
    return {item.id: apply_override(item, overrides) for item in items}

def get_tracking_state() -> TrackingState:
    """获取新的追踪状态对象"""
    return TrackingState()

# ============================================================================
# 调试 / 打印工具
# ============================================================================

def print_decision(decision: PolicyDecision, item: ChangeItem = None):
    """打印决策结果（调试用）"""
    print(f"\n{'='*60}")
    print(f"Policy Decision")
    print(f"{'='*60}")
    if item:
        print(f"File: {item.file_path}")
        print(f"Category: {item.category.value}")
        print(f"Description: {item.description[:80]}...")
    print(f"Risk Level: {decision.risk_level.value}")
    print(f"Requires Approval: {decision.requires_approval}")
    print(f"Allowed: {decision.allowed}")
    print(f"Reason: {decision.reason}")
    if decision.suggestions:
        print(f"Suggestions:")
        for s in decision.suggestions:
            print(f"  - {s}")
    print(f"{'='*60}\n")

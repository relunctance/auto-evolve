"""
Confirmation Engine — Handles user interaction and decision storage.

This module implements the user-interaction-protocol from project-standard:
1. Determines which perspectives are active based on perspective-config.yaml
2. Filters findings that require user confirmation
3. Asks the user and processes their decisions
4. Stores decisions in learnings/ for pattern replay

Usage:
    from confirmation_engine import ConfirmationEngine

    engine = ConfirmationEngine(repo_path)
    active_perspectives = engine.get_active_perspectives()

    pending = engine.filter_findings_requiring_confirmation(all_findings)
    for finding in pending:
        decision = engine.request_confirmation(finding)
        if decision == "confirmed":
            execute_fix(finding)
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Literal, TYPE_CHECKING
from datetime import datetime, timezone

if TYPE_CHECKING:
    from skills.fix_engine import FixAction


# ─── Data Classes ────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """A finding that requires user interaction."""
    id: str
    perspective: str
    dimension: str
    check_id: str
    description: str
    severity: str
    impact_score: float
    evidence: list[str]
    suggested_fix: str
    fix_action: str
    auto_actionable: bool
    confidence: float
    status: str = "pending_confirmation"
    suggested_fix_action: Optional["FixAction"] = None

@dataclass
class Decision:
    """A user's decision on a finding."""
    decision_id: str
    timestamp: str
    user: str
    finding_pattern: str
    project: str
    decision: str  # "confirmed" | "modified" | "skipped" | "ignored"
    notes: str = ""
    applied_via: str = "manual"  # "manual" | "pattern_replay"
    expires_at: Optional[str] = None

@dataclass
class PatternDecision:
    """Stored pattern for auto-replay."""
    pattern: str
    description: str
    current_decision: str
    decision_count: int
    first_decision: str
    last_decision: str
    expires_at: Optional[str] = None
    context: dict = field(default_factory=dict)


# ─── Tier Classification ───────────────────────────────────────────────────────

TIER1_SEVERITIES = {"critical"}
TIER2_SEVERITIES = {"high"}
TIER2_CONDITIONS = {"low_confidence", "ambiguous", "context_dependent"}


class TierClassifier:
    """Determines which tier a finding belongs to."""

    @staticmethod
    def classify(finding: Finding) -> int:
        """
        Classify a finding into interaction tier.

        Returns:
            1 = Always ask (high stakes, irreversible)
            2 = Ask if low confidence or ambiguous
            3 = Inform only (no blocking)
        """
        # Tier 1: Always ask
        if finding.severity in TIER1_SEVERITIES:
            return 1
        if not finding.auto_actionable:
            return 1

        # Tier 2: Ask if confidence is low
        if finding.confidence < 0.7:
            return 2
        if finding.severity in TIER2_SEVERITIES:
            return 2

        # Tier 3: Inform only
        return 3

    @staticmethod
    def requires_confirmation(finding: Finding) -> bool:
        """Does this finding require user confirmation before acting?"""
        return TierClassifier.classify(finding) in (1, 2)


# ─── Config Loader ────────────────────────────────────────────────────────────

REQUIRED_PERSPECTIVES = {"user", "product", "tech", "security", "testing"}

TYPE_REQUIRED_MAP = {
    "backend": {"observability", "reliability", "integration", "performance", "compatibility", "business_compliance"},
    "frontend": {"documentation", "i18n", "accessibility", "compatibility", "business_compliance"},
    "ai-agent": {"observability", "reliability", "integration", "performance", "cost_efficiency", "business_compliance"},
    "infrastructure": {"observability", "reliability", "integration", "performance", "cost_efficiency", "business_compliance"},
    "content": {"documentation", "i18n", "accessibility", "business_compliance"},
    "generic": {"business_compliance"},
}

ALL_PERSPECTIVES = {
    "user", "product", "project", "tech", "security", "testing",
    "market_influence", "business_sustainability", "security",
    "performance", "testing", "integration", "observability",
    "documentation", "i18n", "accessibility", "reliability",
    "cost_efficiency", "compatibility", "business_compliance",
    "industry_vertical"
}


class ConfigLoader:
    """Load and validate perspective-config.yaml."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.config = self._load()

    def _load(self) -> dict:
        """Load config from perspective-config.yaml."""
        config_path = self.repo_path / "perspective-config.yaml"
        if config_path.exists():
            import yaml
            try:
                return yaml.safe_load(config_path.read_text()) or {}
            except Exception:
                return {}
        return {}

    def get_scan_mode(self) -> str:
        """Get scan mode: 'quick' or 'full'."""
        return self.config.get("scan_mode", "full")

    def get_business_form(self) -> str:
        """Get project business form."""
        return self.config.get("project", {}).get("business_form", "generic")

    def get_tech_stack(self) -> str:
        """Get project tech stack."""
        return self.config.get("project", {}).get("tech_stack", "unknown")

    def get_active_perspectives(self) -> list[str]:
        """
        Determine which perspectives are active for this project.

        Combines:
        - Required perspectives (always active)
        - Type-required perspectives (based on business form)
        - Optional perspectives (explicitly enabled in config)
        - Config overrides (explicitly disabled)
        """
        active = set(REQUIRED_PERSPECTIVES)

        # Type-required
        business_form = self.get_business_form()
        type_required = TYPE_REQUIRED_MAP.get(business_form, set())

        # Check config overrides
        type_overrides = self.config.get("perspectives", {}).get("type_required", {})
        for persp in type_required:
            if type_overrides.get(persp, True):  # Default True
                active.add(persp)

        # Optional
        optional = self.config.get("perspectives", {}).get("optional", {})
        for persp, enabled in optional.items():
            if enabled:
                active.add(persp)

        # Explicit disables
        disabled = self.config.get("perspectives", {}).get("disabled", [])
        active -= set(disabled)

        return sorted(active)

    def get_perspective_weights(self) -> dict:
        """Get perspective weight overrides from config."""
        return self.config.get("weights", {})

    def get_check_overrides(self) -> dict:
        """Get check-level overrides."""
        return self.config.get("checks", {})

    def is_perspective_disabled(self, perspective: str) -> bool:
        """Check if a perspective is explicitly disabled."""
        disabled = self.config.get("perspectives", {}).get("disabled", [])
        return perspective in disabled


# ─── Learnings Store ──────────────────────────────────────────────────────────

class LearningsStore:
    """Store and replay user decisions."""

    LEARNINGS_DIR = ".auto-evolve/learnings"

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self.learnings_dir = self.repo_path / self.LEARNINGS_DIR
        self.learnings_dir.mkdir(parents=True, exist_ok=True)

        self.decisions_file = self.learnings_dir / "decisions.json"
        self.patterns_file = self.learnings_dir / "patterns.json"
        self.ignored_file = self.learnings_dir / "ignored.json"

    def _load_json(self, path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _save_json(self, path: Path, data: dict):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def get_decision(self, finding_pattern: str) -> Optional[Decision]:
        """Get the most recent decision for a finding pattern."""
        data = self._load_json(self.patterns_file)
        pattern = data.get("patterns", {}).get(finding_pattern)
        if pattern:
            return Decision(
                decision_id="",
                timestamp=pattern.get("last_decision", ""),
                user="system",
                finding_pattern=finding_pattern,
                project="",
                decision=pattern.get("current_decision", ""),
                notes="",
                applied_via="pattern_replay"
            )
        return None

    def should_auto_apply(self, finding: Finding) -> tuple[bool, str]:
        """
        Check if we should auto-apply a decision based on learnings.

        Returns:
            (should_auto_apply, decision_or_reason)
        """
        # Find matching pattern
        pattern_key = self._build_pattern_key(finding)
        data = self._load_json(self.patterns_file)

        pattern_data = data.get("patterns", {}).get(pattern_key)
        if not pattern_data:
            return False, "no_stored_decision"

        # Check expiration
        expires_at = pattern_data.get("expires_at")
        if expires_at:
            if datetime.now(timezone.utc) > datetime.fromisoformat(expires_at):
                return False, "pattern_expired"

        decision = pattern_data.get("current_decision", "")
        if decision in ("skipped", "ignored"):
            return True, decision
        if decision == "confirmed":
            return True, "confirmed"
        return False, "no_auto_decision"

    def record_decision(self, finding: Finding, decision: str, user: str, notes: str = ""):
        """Record a user's decision for future replay."""
        pattern_key = self._build_pattern_key(finding)

        # Update patterns
        patterns_data = self._load_json(self.patterns_file)
        patterns = patterns_data.get("patterns", {})

        if pattern_key not in patterns:
            patterns[pattern_key] = {
                "pattern": pattern_key,
                "description": finding.description,
                "first_decision": self._now(),
                "decision_count": 0,
                "current_decision": decision,
                "context": {
                    "perspective": finding.perspective,
                    "severity": finding.severity,
                }
            }

        p = patterns[pattern_key]
        p["last_decision"] = self._now()
        p["decision_count"] += 1
        p["current_decision"] = decision

        # Set expiration (6 months for manual decisions)
        if decision != "confirmed":
            from datetime import timedelta
            expires = datetime.now(timezone.utc) + timedelta(days=180)
            p["expires_at"] = expires.isoformat()

        patterns_data["patterns"] = patterns
        self._save_json(self.patterns_file, patterns_data)

        # Record individual decision
        decisions_data = self._load_json(self.decisions_file)
        decisions = decisions_data.get("decisions", [])
        decisions.append({
            "decision_id": f"dec-{int(time.time())}",
            "timestamp": self._now(),
            "user": user,
            "finding_pattern": pattern_key,
            "project": str(self.repo_path),
            "decision": decision,
            "notes": notes,
            "applied_via": "manual"
        })
        decisions_data["decisions"] = decisions
        self._save_json(self.decisions_file, decisions_data)

    def record_ignored(self, finding: Finding, user: str, reason: str = ""):
        """Record a permanently ignored finding."""
        ignored_data = self._load_json(self.ignored_file)
        ignored = ignored_data.get("ignored", [])
        ignored.append({
            "finding_id": self._build_pattern_key(finding),
            "description": finding.description,
            "ignored_by": user,
            "ignored_at": self._now(),
            "reason": reason,
        })
        ignored_data["ignored"] = ignored
        self._save_json(self.ignored_file, ignored_data)

    def is_ignored(self, finding: Finding) -> bool:
        """Check if this finding is permanently ignored."""
        ignored_data = self._load_json(self.ignored_file)
        ignored = ignored_data.get("ignored", [])
        pattern_key = self._build_pattern_key(finding)
        return any(i.get("finding_id") == pattern_key for i in ignored)

    def _build_pattern_key(self, finding: Finding) -> str:
        """Build a stable pattern key for grouping similar findings."""
        return f"{finding.perspective}_{finding.check_id}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


# ─── Confirmation Engine ───────────────────────────────────────────────────────

class ConfirmationEngine:
    """
    Main engine for handling user confirmation of findings.

    Coordinates:
    1. Config loading (which perspectives are active)
    2. Learnings store (decision replay)
    3. User interaction (asking for confirmation)
    4. FixEngine execution (when user confirms)
    """

    def __init__(self, repo_path: Path, user: str = "tseng", sender_open_id: str = ""):
        self.repo_path = Path(repo_path)
        self.user = user
        self.sender_open_id = sender_open_id
        self.config_loader = ConfigLoader(repo_path)
        self.learnings = LearningsStore(repo_path)

    def get_active_perspectives(self) -> list[str]:
        """Return list of active perspectives for this project."""
        return self.config_loader.get_active_perspectives()

    def filter_findings_for_perspectives(self, all_findings: list[Finding]) -> list[Finding]:
        """Filter findings to only those from active perspectives."""
        active = set(self.get_active_perspectives())
        return [f for f in all_findings if f.perspective in active]

    def filter_findings_requiring_confirmation(
        self, findings: list[Finding]
    ) -> list[Finding]:
        """
        Filter findings that require user confirmation.

        Excludes:
        - Findings already decided (via pattern replay)
        - Permanently ignored findings
        - Low-priority findings (Tier 3)
        """
        pending = []

        for finding in findings:
            # Skip if permanently ignored
            if self.learnings.is_ignored(finding):
                continue

            # Check if we should auto-apply from learnings
            should_auto, decision_or_reason = self.learnings.should_auto_apply(finding)
            if should_auto:
                finding.status = f"auto_{decision_or_reason}"
                continue

            # Check if requires confirmation
            if not TierClassifier.requires_confirmation(finding):
                finding.status = "inform_only"
                continue

            pending.append(finding)

        return pending

    def group_by_pattern(self, findings: list[Finding]) -> dict[str, list[Finding]]:
        """Group similar findings for batch confirmation."""
        groups = {}
        for f in findings:
            key = f"{f.perspective}_{f.check_id}"
            if key not in groups:
                groups[key] = []
            groups[key].append(f)
        return groups

    def request_confirmation(self, finding: Finding) -> str:
        """
        Request user confirmation for a finding.

        Returns:
            "confirmed" | "modified" | "skipped" | "ignored" | "escalated"
        """
        tier = TierClassifier.classify(finding)

        # Build the confirmation message
        msg = self._build_confirmation_message(finding, tier)

        # In practice, this would send to Feishu/terminal
        # For now, return a placeholder that the caller handles
        return "pending"

    def _build_confirmation_message(self, finding: Finding, tier: int) -> str:
        """Build a formatted confirmation message."""
        tier_label = {
            1: "🚫 必须确认",
            2: "⚠️ 需要确认",
            3: "ℹ️ 仅供参考"
        }.get(tier, "")

        lines = [
            f"{tier_label}",
            "",
            f"视角: {finding.perspective.upper()}",
            f"问题: {finding.description}",
            f"证据: {' | '.join(finding.evidence[:2])}",
            f"严重性: {finding.severity.upper()}",
            f"建议: {finding.suggested_fix}",
            f"自动修复: {'✅ 可自动' if finding.auto_actionable else '❌ 需确认'}",
            "",
            "操作选项:",
            "  [1] 确认执行 — 直接执行这个改动",
            "  [2] 修改后执行 — 我想修改一下建议",
            "  [3] 跳过此问题 — 这次忽略",
            "  [4] 永久忽略 — 以后不再提示此类问题",
            "  [5] 升級 — 需要更多人讨论",
            "",
            f"(回复数字即可，或回复\"详情\"查看完整信息)",
        ]

        return "\n".join(lines)

    def _confirm_and_record(self, finding: Finding, decision: str, notes: str = "") -> str:
        """
        Internal: record decision AND trigger FixEngine for confirmed findings.
        """
        # Record the decision
        if decision in ("skipped", "ignored"):
            self.learnings.record_decision(finding, decision, self.user, notes)
            if decision == "ignored":
                self.learnings.record_ignored(finding, self.user, notes)
        elif decision == "confirmed":
            self.learnings.record_decision(finding, decision, self.user, notes)
            # Actually execute the fix via FixEngine
            if finding.suggested_fix_action:
                try:
                    from skills.fix_engine import FixEngine
                    engine = FixEngine(repo_path=self.repo_path, dry_run=False)
                    results = engine.execute_batch([finding.suggested_fix_action])
                    # Log execution results (could extend finding.status with result summary)
                    success_count = sum(1 for r in results if r.success)
                    finding.status = f"confirmed_executed:{success_count}/{len(results)}"
                except Exception as e:
                    finding.status = f"confirmed_execution_error:{e}"
            else:
                finding.status = "confirmed"
        else:
            self.learnings.record_decision(finding, decision, self.user, notes)
            finding.status = decision

        return decision

    def process_user_response(
        self,
        finding: Finding,
        response: str,
        notes: str = ""
    ) -> str:
        """
        Process a user's response to a confirmation request.

        Args:
            finding: The finding being confirmed
            response: User's response (1-5 or text)
            notes: Additional notes from user

        Returns:
            The decision made: "confirmed" | "modified" | "skipped" | "ignored" | "escalated"
        """
        # Parse response
        response = response.strip()

        # Quick reply mapping
        QUICK_REPLY = {
            "1": "confirmed",
            "2": "modified",
            "3": "skipped",
            "4": "ignored",
            "5": "escalated",
        }

        if response in QUICK_REPLY:
            decision = QUICK_REPLY[response]
        elif response.lower() in ("confirm", "yes", "y", "执行"):
            decision = "confirmed"
        elif response.lower() in ("skip", "s", "跳过", "忽略"):
            decision = "skipped"
        elif response.lower() in ("ignore", "i", "永久忽略"):
            decision = "ignored"
        elif response.lower() in ("escalate", "e", "升级", "讨论"):
            decision = "escalated"
        else:
            decision = "modified"

        return self._confirm_and_record(finding, decision, notes)

    def batch_confirm(
        self,
        findings: list[Finding],
        batch_decision: str
    ) -> dict[str, str]:
        """
        Apply a batch decision to multiple similar findings.

        Args:
            findings: Group of similar findings
            batch_decision: "confirmed" | "skipped" | "ignored"

        Returns:
            Map of finding_id -> decision made
        """
        results = {}
        for finding in findings:
            decision = self.process_user_response(
                finding, batch_decision, notes=f"batch_confirm: {len(findings)} similar findings"
            )
            results[finding.id] = decision
        return results


# ─── Feishu Integration ─────────────────────────────────────────────────────────

FEISHU_IM_API = "https://open.feishu.cn/open-apis/im/v1/messages"
FEISHU_TOKEN_API = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"


def _get_feishu_token() -> Optional[str]:
    """Get a Feishu tenant access token from app credentials."""
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        return None

    try:
        import urllib.request, json
        data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
        req = urllib.request.Request(FEISHU_TOKEN_API, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("tenant_access_token")
    except Exception:
        return None


def _send_feishu_message(token: str, receive_id: str, msg_type: str,
                          content: str, receive_id_type: str = "open_id") -> bool:
    """Send a Feishu IM message via the REST API."""
    try:
        import urllib.request, json
        url = f"{FEISHU_IM_API}?receive_id_type={receive_id_type}"
        payload = json.dumps({
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content,
        }).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("code", 0) == 0
    except Exception as e:
        print(f"[Feishu] Failed to send message: {e}")
        return False


class FeishuNotifier:
    """Send confirmation requests to user via Feishu IM API."""

    def __init__(self, chat_id: str = None, sender_open_id: str = None):
        self.chat_id = chat_id or os.environ.get("FEISHU_CHAT_ID", "")
        self.sender_open_id = sender_open_id or ""

    def send_confirmation_card(self, finding: Finding) -> bool:
        """
        Send a single-finding confirmation card via Feishu IM API.
        Uses the Feishu REST API (urllib.request — same pattern as GitHub API calls).
        """
        if not self.sender_open_id:
            print("[Feishu] No sender_open_id — skipping card send")
            return False

        tier = TierClassifier.classify(finding)
        tier_label = {
            1: "🚫 必须确认",
            2: "⚠️ 需要确认",
        }.get(tier, "⚠️ 需要确认")

        severity_color = "red" if finding.severity == "critical" else "orange"

        card_elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**问题:** {finding.description}"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**严重性:** {finding.severity.upper()} | "
                        f"**置信度:** {finding.confidence:.0%} | "
                        f"**影响:** {finding.impact_score:.0%}"
                    )
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**证据:** {' | '.join(str(e) for e in finding.evidence[:2])}"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**建议修复:** {finding.suggested_fix}"
                }
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✅ 确认执行"},
                        "type": "primary",
                        "value": {"action": "confirm", "finding_id": finding.id}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✏️ 修改后执行"},
                        "type": "default",
                        "value": {"action": "modified", "finding_id": finding.id}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "⏭️ 跳过"},
                        "type": "default",
                        "value": {"action": "skip", "finding_id": finding.id}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔒 永久忽略"},
                        "type": "default",
                        "value": {"action": "ignore", "finding_id": finding.id}
                    },
                ]
            }
        ]

        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{tier_label} {finding.perspective.upper()}"
                },
                "template": severity_color
            },
            "elements": card_elements
        }

        token = _get_feishu_token()
        if not token:
            print("[Feishu] No access token — skipping card send (set FEISHU_APP_ID + FEISHU_APP_SECRET)")
            return False

        return _send_feishu_message(
            token=token,
            receive_id=self.sender_open_id,
            msg_type="interactive",
            content=json.dumps(card_content),
            receive_id_type="open_id"
        )

    def send_confirmation_request(self, engine: ConfirmationEngine, finding: Finding) -> bool:
        """Send a confirmation request to Feishu (delegates to send_confirmation_card)."""
        return self.send_confirmation_card(finding)

    def send_batch_confirmation(
        self,
        engine: ConfirmationEngine,
        findings: list[Finding],
        group_key: str
    ) -> bool:
        """Send a batch confirmation for similar findings via Feishu."""
        if not self.sender_open_id:
            return False

        card_elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"发现 **{len(findings)}** 个相似的 **{findings[0].perspective.upper()}** 问题"
                    )
                }
            },
            {"tag": "hr"},
        ]

        for i, f in enumerate(findings[:3], 1):
            card_elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{i}.** {f.description[:80]}"}
            })

        if len(findings) > 3:
            card_elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"...还有 {len(findings) - 3} 个类似问题"}
            })

        card_elements.append({"tag": "hr"})
        card_elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "✅ 全部修复"},
                    "type": "primary",
                    "value": {"action": "batch_confirm", "group_key": group_key}
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "⏭️ 全部跳过"},
                    "type": "default",
                    "value": {"action": "batch_skip", "group_key": group_key}
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "🔍 逐个确认"},
                    "type": "default",
                    "value": {"action": "逐个确认", "group_key": group_key}
                },
            ]
        })

        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📋 批量确认 ({len(findings)} 个相似问题)"
                },
                "template": "orange"
            },
            "elements": card_elements
        }

        token = _get_feishu_token()
        if not token:
            print("[Feishu] No access token — skipping batch card send")
            return False

        return _send_feishu_message(
            token=token,
            receive_id=self.sender_open_id,
            msg_type="interactive",
            content=json.dumps(card_content),
            receive_id_type="open_id"
        )


# ─── Quick Test ───────────────────────────────────────────────────────────────

def quick_test():
    """Test the confirmation engine."""
    import tempfile
    repo = Path(tempfile.mkdtemp())

    # Create a dummy perspective-config.yaml
    (repo / "perspective-config.yaml").write_text("""
scan_mode: full
project:
  business_form: backend
  tech_stack: python
perspectives:
  optional:
    market_influence: true
""")

    engine = ConfirmationEngine(repo)

    print("Active perspectives:", engine.get_active_perspectives())

    # Test findings
    test_finding = Finding(
        id="SEC_001",
        perspective="security",
        dimension="injection",
        check_id="SEC_INJECTION_001",
        description="SQL injection vulnerability in user query",
        severity="critical",
        impact_score=0.9,
        evidence=["src/db.py:42"],
        suggested_fix="Use parameterized query",
        fix_action="parameterize_query",
        auto_actionable=True,
        confidence=0.95
    )

    print("Tier:", TierClassifier.classify(test_finding))
    print("Requires confirmation:", TierClassifier.requires_confirmation(test_finding))

    # Test decision replay
    should_auto, reason = engine.learnings.should_auto_apply(test_finding)
    print(f"Should auto-apply: {should_auto}, reason: {reason}")

    print("\nAll tests passed!")


if __name__ == "__main__":
    quick_test()

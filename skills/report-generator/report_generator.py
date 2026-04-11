"""
Report Generator — Generates human-readable scan reports from ScanResult objects.

Supports multiple output formats: Markdown, HTML, JSON, Feishu card.

Usage:
    from report_generator import ReportGenerator, Format

    generator = ReportGenerator()
    report = generator.generate(
        scan_results=[security_result, testing_result],
        project_score=81.2,
        trend=trend_data,
        format=Format.MARKDOWN
    )
"""

import json
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class TrendData:
    direction: str          # "up" | "down" | "stable"
    delta: float
    delta_percent: str
    previous_score: float

@dataclass
class ProjectScore:
    weighted_score: float
    grade: str
    trend: Optional[TrendData]


# ─── Grade Emoji Mapping ────────────────────────────────────────────────────────

GRADE_EMOJI = {
    "excellent": "🟢",
    "good": "🟢",
    "acceptable": "🟡",
    "poor": "🔴",
    "critical": "🔴",
}

GRADE_COLOR = {
    "excellent": "#22c55e",
    "good": "#22c55e",
    "acceptable": "#eab308",
    "poor": "#ef4444",
    "critical": "#dc2626",
}


# ─── Markdown Report ──────────────────────────────────────────────────────────

class MarkdownReport:
    """Generate Markdown-formatted scan reports."""

    def generate(
        self,
        scan_results: list[dict],
        project_score: ProjectScore,
        meta: dict,
        finding_limit: int = 20,
    ) -> str:
        """Generate a complete Markdown report."""
        lines = []

        # Header
        lines.append(self._header(meta))

        # Score Overview
        lines.append(self._score_overview(project_score))

        # Perspective Results
        lines.append(self._perspective_results(scan_results))

        # Findings
        lines.append(self._findings(scan_results, finding_limit))

        # Recommendations
        lines.append(self._recommendations(scan_results))

        # Footer
        lines.append(self._footer(meta))

        return "\n\n".join(lines)

    def _header(self, meta: dict) -> str:
        repo = meta.get("repo", "unknown")
        branch = meta.get("branch", "unknown")
        scan_mode = meta.get("scan_mode", "unknown")
        timestamp = meta.get("timestamp", datetime.now(timezone.utc).isoformat())

        return f"""# 🔍 Auto-Evolve Scan Report

**Project:** `{repo}`
**Branch:** `{branch}`
**Scan Mode:** {scan_mode}
**Scanned:** {timestamp.split(".")[0].replace("T", " ")}

---

## 📊 Overall Score

"""

    def _score_overview(self, project_score: ProjectScore) -> str:
        emoji = GRADE_EMOJI.get(project_score.grade, "🟡")
        trend_arrow = {
            "up": "↗️",
            "down": "↘️",
            "stable": "→",
        }.get(project_score.trend.direction if project_score.trend else "stable", "→")

        lines = [
            f"| Score | Grade | Trend |",
            f"|-------|-------|-------|",
            f"| **{project_score.weighted_score:.1f}** | {emoji} {project_score.grade.capitalize()} | {trend_arrow}",
        ]

        if project_score.trend:
            lines.append(
                f"**{project_score.trend.delta_percent}** vs last scan "
                f"(was {project_score.trend.previous_score:.1f})"
            )

        return "\n".join(lines) + "\n\n---\n"

    def _perspective_results(self, scan_results: list[dict]) -> str:
        lines = ["## 🔬 Perspective Results\n"]

        for result in scan_results:
            emoji = GRADE_EMOJI.get(result.get("grade", "acceptable"), "🟡")
            lines.append(
                f"| {emoji} **{result['perspective'].capitalize()}** "
                f"| {result.get('overall_score', 0):.1f} "
                f"| {result.get('grade', 'N/A').capitalize()} |"
            )

        lines.append("\n---\n")
        return "\n".join(lines)

    def _findings(self, scan_results: list[dict], limit: int) -> str:
        lines = ["## 🚨 Priority Findings\n"]

        all_findings = []
        for result in scan_results:
            perspective = result.get("perspective", "unknown")
            for finding in result.get("findings", []):
                if finding.get("status") in ("fail", "warning"):
                    finding["_perspective"] = perspective
                    all_findings.append(finding)

        # Sort by severity then confidence
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_findings.sort(
            key=lambda f: (
                severity_order.get(f.get("severity", "low"), 4),
                -(f.get("confidence", 0.5))
            )
        )

        if not all_findings:
            lines.append("✅ **All Clear** — No issues found.")
            return "\n".join(lines)

        for i, finding in enumerate(all_findings[:limit]):
            emoji = "🔴" if finding.get("severity") == "critical" else \
                    "🟠" if finding.get("severity") == "high" else \
                    "🟡"
            lines.append(
                f"### {emoji} {i+1}. [{finding.get('severity', '?').upper()}] "
                f"{finding.get('description', 'No description')[:80]}\n"
            )
            lines.append(f"**Perspective:** {finding.get('_perspective', 'N/A')}")
            lines.append(f"**Fix:** {finding.get('suggested_fix', 'N/A')}")
            if finding.get("evidence"):
                lines.append(f"**Evidence:** `{'` `'.join(finding['evidence'][:3])}`")
            if finding.get("fix_action"):
                lines.append(f"**Action:** `{finding['fix_action']}`")
            lines.append("")

        if len(all_findings) > limit:
            lines.append(f"\n*... and {len(all_findings) - limit} more findings.*\n")

        lines.append("---\n")
        return "\n".join(lines)

    def _recommendations(self, scan_results: list[dict]) -> str:
        lines = ["## 💡 Top Recommendations\n"]

        # Collect auto-actionable findings sorted by severity
        actionable = []
        for result in scan_results:
            for finding in result.get("findings", []):
                if finding.get("auto_actionable") and finding.get("status") in ("fail", "warning"):
                    actionable.append(finding)

        if not actionable:
            lines.append("No auto-actionable recommendations at this time.")
            return "\n".join(lines) + "\n"

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        actionable.sort(key=lambda f: severity_order.get(f.get("severity", "low"), 4))

        for i, finding in enumerate(actionable[:5], 1):
            lines.append(
                f"{i}. **{finding.get('perspective', '').capitalize()}** — "
                f"{finding.get('description', '')[:100]}"
            )
            if finding.get("fix_action"):
                lines.append(f"   → Fix: `{finding['fix_action']}`")

        return "\n".join(lines) + "\n"

    def _footer(self, meta: dict) -> str:
        return (
            f"---\n"
            f"*Generated by Auto-Evolve | Scan ID: {meta.get('scan_id', 'N/A')}*\n"
        )


# ─── Feishu Card Report ────────────────────────────────────────────────────────

class FeishuCardReport:
    """Generate Feishu interactive card messages for notifications."""

    def generate(self, scan_results: list[dict], project_score: ProjectScore, meta: dict) -> dict:
        """Generate Feishu card JSON payload."""
        emoji = GRADE_EMOJI.get(project_score.grade, "🟡")
        trend = project_score.trend
        trend_str = ""
        if trend:
            arrow = {"up": "⬆️", "down": "⬇️", "stable": "➡️"}.get(trend.direction, "➡️")
            trend_str = f" {arrow} {trend.delta_percent}"

        # Build finding summary
        critical_count = sum(
            1 for r in scan_results
            for f in r.get("findings", [])
            if f.get("severity") == "critical"
        )
        high_count = sum(
            1 for r in scan_results
            for f in r.get("findings", [])
            if f.get("severity") == "high"
        )

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"🔍 Auto-Evolve Scan: {emoji} {project_score.weighted_score:.0f}分 ({project_score.grade.capitalize()})"},
                    "template": GRADE_COLOR.get(project_score.grade, "#gray"),
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                f"**项目:** `{meta.get('repo', 'unknown')}`\n"
                                f"**分支:** `{meta.get('branch', 'unknown')}`\n"
                                f"**扫描模式:** {meta.get('scan_mode', 'unknown')}"
                            ),
                        },
                    },
                    {"tag": "hr"},
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                f"**趋势:** {trend_str}\n"
                                f"**关键问题:** 🔴 {critical_count} 个严重 | 🟠 {high_count} 个高危"
                            ),
                        },
                    },
                    {"tag": "hr"},
                ],
            },
        }

        # Add top findings
        top_findings = self._get_top_findings(scan_results, n=3)
        if top_findings:
            elements = card["card"]["elements"]
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**🔺 Top 发现:**"}
            })
            for finding in top_findings:
                emoji_sev = "🔴" if finding["severity"] == "critical" else "🟠"
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"{emoji_sev} **{finding['perspective'].upper()}** | "
                            f"{finding['description'][:60]}\n"
                            f"→ Fix: `{finding.get('fix_action', 'N/A')}`"
                        ),
                    },
                })

        # Add action buttons
        elements = card["card"]["elements"]
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "lark_md", "content": "📋 查看报告"},
                    "type": "primary",
                    "url": meta.get("report_url", "https://github.com"),
                },
                {
                    "tag": "button",
                    "text": {"tag": "lark_md", "content": "🤖 自动修复"},
                    "type": "default",
                },
            ],
        })

        return card

    def _get_top_findings(self, scan_results: list[dict], n: int = 3) -> list:
        all_findings = []
        for result in scan_results:
            for f in result.get("findings", []):
                if f.get("status") in ("fail", "warning"):
                    f["_perspective"] = result.get("perspective", "unknown")
                    all_findings.append(f)

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_findings.sort(
            key=lambda f: (
                severity_order.get(f.get("severity", "low"), 4),
                -(f.get("confidence", 0.5))
            )
        )

        return [
            {**f, "perspective": f.get("_perspective", "unknown")}
            for f in all_findings[:n]
        ]


# ─── JSON Report ───────────────────────────────────────────────────────────────

class JSONReport:
    """Generate machine-readable JSON reports."""

    def generate(self, scan_results: list[dict], project_score: ProjectScore, meta: dict) -> str:
        """Generate a JSON report."""
        report = {
            "meta": meta,
            "project_score": {
                "weighted_score": project_score.weighted_score,
                "grade": project_score.grade,
                "trend": {
                    "direction": project_score.trend.direction if project_score.trend else None,
                    "delta": project_score.trend.delta if project_score.trend else None,
                    "delta_percent": project_score.trend.delta_percent if project_score.trend else None,
                    "previous_score": project_score.trend.previous_score if project_score.trend else None,
                } if project_score.trend else None,
            },
            "perspectives": [
                {
                    "name": r.get("perspective"),
                    "score": r.get("overall_score"),
                    "grade": r.get("grade"),
                    "finding_count": len(r.get("findings", [])),
                }
                for r in scan_results
            ],
            "findings": [
                f
                for r in scan_results
                for f in r.get("findings", [])
                if f.get("status") in ("fail", "warning")
            ],
        }
        return json.dumps(report, indent=2, ensure_ascii=False)


# ─── Main Report Generator ─────────────────────────────────────────────────────

class Format:
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    FEISHU = "feishu"


class ReportGenerator:
    """
    Unified report generator supporting multiple output formats.

    Usage:
        generator = ReportGenerator()

        # Markdown report
        md = generator.generate(scan_results, project_score, meta, Format.MARKDOWN)

        # Feishu card
        feishu_card = generator.generate(scan_results, project_score, meta, Format.FEISHU)
    """

    def __init__(self):
        self.markdown = MarkdownReport()
        self.feishu = FeishuCardReport()
        self.json = JSONReport()

    def generate(
        self,
        scan_results: list[dict],
        project_score: ProjectScore,
        meta: dict,
        format: str = Format.MARKDOWN,
    ) -> str | dict:
        """Generate a report in the specified format."""

        if format == Format.MARKDOWN:
            return self.markdown.generate(scan_results, project_score, meta)

        elif format == Format.FEISHU:
            return self.feishu.generate(scan_results, project_score, meta)

        elif format == Format.JSON:
            return self.json.generate(scan_results, project_score, meta)

        elif format == Format.HTML:
            # Convert markdown to HTML (basic conversion)
            md = self.markdown.generate(scan_results, project_score, meta)
            return self._markdown_to_html(md)

        else:
            raise ValueError(f"Unknown format: {format}")

    def _markdown_to_html(self, md: str) -> str:
        """Basic Markdown to HTML conversion."""
        import re

        html = md
        # Headers
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        # Code blocks
        html = re.sub(r"```(\w+)?\n(.*?)```", r"<pre><code>\2</code></pre>", html, flags=re.DOTALL)
        # Inline code
        html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
        # Bold
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        # Tables (basic)
        html = re.sub(r"\|(.+)\|\n\|[-| ]+\|", r"<table><tr>\1</tr>", html)
        # Paragraphs
        html = re.sub(r"\n\n", r"</p><p>", html)
        return f"<html><body><p>{html}</p></body></html>"

    def generate_summary(
        self,
        scan_results: list[dict],
        project_score: ProjectScore,
    ) -> str:
        """Generate a one-line summary for quick notification."""
        emoji = GRADE_EMOJI.get(project_score.grade, "🟡")
        trend = project_score.trend
        trend_str = ""
        if trend:
            arrow = {"up": "↗️", "down": "↘️", "stable": "→"}.get(trend.direction, "→")
            trend_str = f" {arrow} {trend.delta_percent}"

        total_findings = sum(
            1 for r in scan_results
            for f in r.get("findings", [])
            if f.get("status") in ("fail", "warning")
        )

        return (
            f"{emoji} **{project_score.weighted_score:.0f}分** ({project_score.grade})"
            f"{trend_str} | "
            f"🚨 {total_findings}个问题"
        )

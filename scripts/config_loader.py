#!/usr/bin/env python3
"""
Config loader for auto-evolve perspective configuration.

Reads perspective-config.yaml and resolves which perspectives are active,
what weights to apply, and what overrides to use.

Config file locations (in order of priority):
  1. ./perspective-config.yaml  (project root)
  2. ~/.auto-evolve/perspective-config.yaml  (user home)
  3. Default hardcoded config  (backward compatibility)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

# ---------------------------------------------------------------------------
# Default configuration (backward compatibility)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1.0",
    "project_type": "通用项目",
    "required": ["user", "product", "tech", "security", "testing"],
    "type_required": [],
    "optional": [],
    "disabled": [],
    "perspective_overrides": {},
    "scan_mode": "quick",
    "project": {"name": "auto-evolve"},
    "notifications": {"channel": "feishu"},
}

# Perspectives excluded in Quick Scan mode (beyond optional)
QUICK_SKIP_PERSPECTIVES: set[str] = {
    "market_influence",
    "business_sustainability",
    "industry_vertical",
}

# Default type_required perspectives per project type
# When type_required is empty in config, these are used instead
PROJECT_TYPE_DEFAULTS: dict[str, list[str]] = {
    "前端应用":    ["user", "product"],
    "后端服务":    ["tech", "user"],
    "智能体/AI": ["product", "user"],
    "基础设施":    ["tech", "project"],
    "内容与文档": ["product", "user"],
    "通用项目":    [],
    # Aliases
    "frontend":    ["user", "product"],
    "backend":     ["tech", "user"],
    "agent":       ["product", "user"],
    "infrastructure": ["tech", "project"],
    "content":     ["product", "user"],
    "general":     [],
}

# Numeric weights per project type for the standard 4 perspectives.
# Maps project_type → {perspective: weight}
# These are used as base weights; perspective_overrides can adjust them.
PERSPECTIVE_BASE_WEIGHTS: dict[str, dict[str, float]] = {
    "前端应用":    {"user": 0.35, "product": 0.25, "project": 0.15, "tech": 0.25},
    "后端服务":    {"user": 0.25, "product": 0.20, "project": 0.20, "tech": 0.35},
    "智能体/AI": {"user": 0.25, "product": 0.30, "project": 0.20, "tech": 0.25},
    "基础设施":    {"user": 0.15, "product": 0.20, "project": 0.25, "tech": 0.40},
    "内容与文档": {"user": 0.30, "product": 0.35, "project": 0.20, "tech": 0.15},
    "通用项目":    {"user": 0.25, "product": 0.25, "project": 0.25, "tech": 0.25},
    # Aliases
    "frontend":    {"user": 0.35, "product": 0.25, "project": 0.15, "tech": 0.25},
    "backend":     {"user": 0.25, "product": 0.20, "project": 0.20, "tech": 0.35},
    "agent":       {"user": 0.25, "product": 0.30, "project": 0.20, "tech": 0.25},
    "infrastructure": {"user": 0.15, "product": 0.20, "project": 0.25, "tech": 0.40},
    "content":     {"user": 0.30, "product": 0.35, "project": 0.20, "tech": 0.15},
    "general":     {"user": 0.25, "product": 0.25, "project": 0.25, "tech": 0.25},
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PerspectiveConfig:
    """Resolved perspective configuration."""

    version: str = "1.0"
    project_type: str = "通用项目"
    required: list[str] = field(default_factory=list)
    type_required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)
    perspective_overrides: dict = field(default_factory=dict)
    scan_mode: str = "quick"
    project: dict = field(default_factory=dict)
    notifications: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PerspectiveConfig":
        """Construct PerspectiveConfig from a parsed dict."""
        return cls(
            version=str(data.get("version", DEFAULT_CONFIG["version"])),
            project_type=str(data.get("project_type", DEFAULT_CONFIG["project_type"])),
            required=list(data.get("required", DEFAULT_CONFIG["required"])),
            type_required=list(data.get("type_required", DEFAULT_CONFIG["type_required"])),
            optional=list(data.get("optional", DEFAULT_CONFIG["optional"])),
            disabled=list(data.get("disabled", DEFAULT_CONFIG["disabled"])),
            perspective_overrides=dict(data.get("perspective_overrides", DEFAULT_CONFIG["perspective_overrides"])),
            scan_mode=str(data.get("scan_mode", DEFAULT_CONFIG["scan_mode"])),
            project=dict(data.get("project", DEFAULT_CONFIG["project"])),
            notifications=dict(data.get("notifications", DEFAULT_CONFIG["notifications"])),
        )


# ---------------------------------------------------------------------------
# Config Loader
# ---------------------------------------------------------------------------

class ConfigLoader:
    """
    Loads and resolves perspective-config.yaml.

    Config file locations (in order of priority):
      1. ./perspective-config.yaml  (project root)
      2. ~/.auto-evolve/perspective-config.yaml  (user home)
      3. Default hardcoded config  (backward compatibility)
    """

    def load(self, config_path: str | Path | None = None) -> PerspectiveConfig:
        """
        Load config from file or return defaults.

        Args:
            config_path: Explicit config path. If provided, only that file is tried.
                        Otherwise searches in order: ./perspective-config.yaml,
                        ~/.auto-evolve/perspective-config.yaml, then defaults.

        Returns:
            PerspectiveConfig instance (never raises)
        """
        if config_path is not None:
            path = Path(config_path)
            if path.exists():
                return self._load_file(path)
            return PerspectiveConfig.from_dict(DEFAULT_CONFIG)

        # Search locations in priority order
        search_paths: list[Path] = [
            Path.cwd() / "perspective-config.yaml",
            Path.home() / ".auto-evolve" / "perspective-config.yaml",
        ]

        for path in search_paths:
            if path.exists():
                loaded = self._load_file(path)
                if loaded is not None:
                    return loaded

        # Fall back to defaults
        return PerspectiveConfig.from_dict(DEFAULT_CONFIG)

    def _load_file(self, path: Path) -> PerspectiveConfig | None:
        """Parse a single YAML config file. Returns None on failure."""
        try:
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            if not isinstance(data, dict):
                return None
            return PerspectiveConfig.from_dict(data)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Perspective resolution
    # -------------------------------------------------------------------------

    def get_active_perspectives(self, config: PerspectiveConfig) -> list[str]:
        """
        Resolve which perspectives are active for this config.

        Resolution order:
          1. All `required` perspectives
          2. All `type_required` perspectives (based on project type;
             falls back to PROJECT_TYPE_DEFAULTS if config.type_required is empty)
          3. Any `optional` perspectives that are enabled (not in disabled)
          4. Remove any in `disabled`
          5. Quick Scan: skip optional + market_influence + business_sustainability
             + industry_vertical

        Perspective names are normalised to uppercase.

        Args:
            config: PerspectiveConfig instance

        Returns:
            List of active perspective names in resolution order (uppercase)
        """
        active: set[str] = set()
        disabled_lower = {p.lower() for p in config.disabled}

        def _add(perspectives: list[str]) -> None:
            for p in perspectives:
                p_lower = p.lower()
                if p_lower not in disabled_lower and p_lower not in QUICK_SKIP_PERSPECTIVES:
                    active.add(p_lower.upper())

        # 1. Required (always on)
        _add(config.required)

        # 2. Type-required
        type_req = config.type_required
        if not type_req:
            # Empty type_required → fall back to project-type defaults
            pt_defaults = PROJECT_TYPE_DEFAULTS.get(
                config.project_type,
                PROJECT_TYPE_DEFAULTS.get("通用项目", []),
            )
            _add(pt_defaults)
        else:
            _add(type_req)

        # 3. Optional (user-enabled) — only in Full Scan
        if config.scan_mode.lower() != "quick":
            _add(config.optional)

        # Result in a consistent order (not deterministic set order, but stable)
        # Order: required first, then type_required, then the rest
        ordered: list[str] = []
        for p in config.required:
            p_up = p.lower().upper()
            if p_up in active and p_up not in ordered:
                ordered.append(p_up)

        # Type-required that aren't already included
        type_req = config.type_required if config.type_required else PROJECT_TYPE_DEFAULTS.get(
            config.project_type, []
        )
        for p in type_req:
            p_up = p.lower().upper()
            if p_up in active and p_up not in ordered:
                ordered.append(p_up)

        # Remaining active perspectives
        for p in active:
            if p not in ordered:
                ordered.append(p)

        return ordered

    # -------------------------------------------------------------------------
    # Weights
    # -------------------------------------------------------------------------

    def get_weights(
        self, config: PerspectiveConfig, perspective: str
    ) -> float:
        """
        Get weight for a perspective (considering overrides).

        Base weights come from PERSPECTIVE_BASE_WEIGHTS using project_type.
        perspective_overrides can adjust individual perspective weights.

        Args:
            config: PerspectiveConfig instance
            perspective: Perspective name (e.g. "USER", "user")

        Returns:
            Weight as a float (0.0–1.0). Returns 0.0 if perspective is not active.
        """
        perspective_lower = perspective.lower()

        # Check if perspective is active
        active = self.get_active_perspectives(config)
        if perspective_lower.upper() not in {p.upper() for p in active}:
            return 0.0

        # Get base weight from project type
        base_weights = PERSPECTIVE_BASE_WEIGHTS.get(
            config.project_type,
            PERSPECTIVE_BASE_WEIGHTS.get("通用项目", {}),
        )
        weight = base_weights.get(perspective_lower, 0.0)

        # Apply override if present
        overrides = config.perspective_overrides or {}
        if perspective_lower in overrides:
            override = overrides[perspective_lower]
            if isinstance(override, dict):
                weight = float(override.get("weight", weight))
            elif isinstance(override, (int, float)):
                weight = float(override)

        return weight

    def get_all_weights(self, config: PerspectiveConfig) -> dict[str, float]:
        """
        Get weights for all active perspectives.

        Returns:
            Dict mapping perspective name (uppercase) → weight
        """
        active = self.get_active_perspectives(config)
        return {p: self.get_weights(config, p) for p in active}

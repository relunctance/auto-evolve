#!/usr/bin/env python3
"""
Unit tests for auto-evolve core functionality.

Covers:
  - Config loading (scripts.config_loader)
  - Repository class (resolve_path, is_closed, get_default_risk)
  - PerspectiveConfig (yaml loading, fallback, get_active_perspectives)
  - Scanner adapter pattern (skills.scanner_contract)
  - FixEngine import (skills.fix_engine)
  - TestingScanner import (skills.testing_scanner)
  - Memory source detection (HawkBridgeMemory, OpenClawMemory)
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ===========================================================
# Test 1: Config loading — scripts.config_loader is importable
# ===========================================================

class TestConfigLoaderImport:
    """Verify scripts.config_loader can be imported without errors."""

    def test_config_loader_imports(self):
        """scripts.config_loader must be importable."""
        import scripts.config_loader as cl
        assert cl is not None

    def test_default_config_defined(self):
        """DEFAULT_CONFIG must be defined and non-empty."""
        from scripts.config_loader import DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG, dict)
        assert "version" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["version"] == "1.0"

    def test_perspective_base_weights_defined(self):
        """PERSPECTIVE_BASE_WEIGHTS must be defined."""
        from scripts.config_loader import PERSPECTIVE_BASE_WEIGHTS
        assert isinstance(PERSPECTIVE_BASE_WEIGHTS, dict)
        assert "通用项目" in PERSPECTIVE_BASE_WEIGHTS
        weights = PERSPECTIVE_BASE_WEIGHTS["通用项目"]
        assert abs(sum(weights.values()) - 1.0) < 0.01  # sum to ~1.0


# ===========================================================
# Helper: import auto-evolve module without running main()
# Uses the sys.modules trick to make dataclass work.
# ===========================================================

def _load_auto_evolve_module():
    """Load scripts/auto-evolve.py as the 'auto_evolve' module.

    Creates a placeholder entry in sys.modules so that dataclass
    decorators resolve the module correctly.
    """
    auto_evolve_path = Path(__file__).parent.parent / "scripts" / "auto-evolve.py"
    mod = types.ModuleType("auto_evolve")
    mod.__file__ = str(auto_evolve_path)
    sys.modules["auto_evolve"] = mod

    try:
        source = auto_evolve_path.read_text(encoding="utf-8")
        exec(source, mod.__dict__)
    except Exception:
        del sys.modules["auto_evolve"]
        raise

    return mod


@pytest.fixture(scope="module")
def ae():
    """Load auto-evolve module once per test module."""
    mod = _load_auto_evolve_module()
    yield mod
    # cleanup
    if "auto_evolve" in sys.modules:
        del sys.modules["auto_evolve"]


# ===========================================================
# Test 2: Repository.resolve_path()
# ===========================================================

class TestRepositoryResolvePath:
    """Tests for Repository.resolve_path()."""

    def test_resolve_absolute_path(self, ae):
        """Absolute path returns the same Path."""
        Repository = ae.Repository
        repo = Repository(path="/tmp/test-repo", type="skill")
        assert repo.resolve_path() == Path("/tmp/test-repo")

    def test_resolve_expands_user_tilde(self, ae):
        """Path with ~ is expanded to user's home directory."""
        Repository = ae.Repository
        repo = Repository(path="~/test-repo", type="skill")
        resolved = repo.resolve_path()
        assert resolved.is_absolute()
        assert "~" not in str(resolved)

    def test_resolve_caches_result(self, ae):
        """resolve_path() caches the result on repeated calls."""
        Repository = ae.Repository
        repo = Repository(path="/tmp/test-repo", type="skill")
        first = repo.resolve_path()
        second = repo.resolve_path()
        assert first == second  # same path (cached)

    def test_resolve_with_tmp_path_fixture(self, ae, tmp_path):
        """resolve_path() works with pytest's tmp_path fixture."""
        Repository = ae.Repository
        test_dir = tmp_path / "my-test-repo"
        test_dir.mkdir()
        repo = Repository(path=str(test_dir), type="skill")
        assert repo.resolve_path() == test_dir
        assert repo.resolve_path().exists()


# ===========================================================
# Test 3: Repository.is_closed()
# ===========================================================

class TestRepositoryIsClosed:
    """Tests for Repository.is_closed()."""

    def test_public_repo_is_not_closed(self, ae):
        """Visibility='public' means not closed."""
        Repository = ae.Repository
        repo = Repository(path="/tmp/test", type="skill", visibility="public")
        assert repo.is_closed() is False

    def test_closed_repo_is_closed(self, ae):
        """Visibility='closed' means is_closed returns True."""
        Repository = ae.Repository
        repo = Repository(path="/tmp/test", type="skill", visibility="closed")
        assert repo.is_closed() is True

    def test_private_repo_is_not_closed(self, ae):
        """Visibility='private' is not the same as closed."""
        Repository = ae.Repository
        repo = Repository(path="/tmp/test", type="skill", visibility="private")
        assert repo.is_closed() is False

    def test_default_visibility_is_public(self, ae):
        """Default visibility is 'public', so default is not closed."""
        Repository = ae.Repository
        repo = Repository(path="/tmp/test", type="skill")
        assert repo.is_closed() is False


# ===========================================================
# Test 4: Repository.get_default_risk()
# ===========================================================

class TestRepositoryGetDefaultRisk:
    """Tests for Repository.get_default_risk()."""

    def test_norms_md_file_is_low_risk(self, ae):
        """norms repo + .md file → LOW risk."""
        Repository = ae.Repository
        RiskLevel = ae.RiskLevel
        repo = Repository(path="/tmp/test", type="norms", visibility="public")
        risk = repo.get_default_risk("added", "README.md")
        assert risk == RiskLevel.LOW

    def test_norms_yaml_file_is_low_risk(self, ae):
        """norms repo + .yaml file → LOW risk."""
        Repository = ae.Repository
        RiskLevel = ae.RiskLevel
        repo = Repository(path="/tmp/test", type="norms", visibility="public")
        risk = repo.get_default_risk("added", "config.yaml")
        assert risk == RiskLevel.LOW

    def test_project_test_file_is_medium_risk(self, ae):
        """project repo + test file → MEDIUM risk."""
        Repository = ae.Repository
        RiskLevel = ae.RiskLevel
        repo = Repository(path="/tmp/test", type="project", visibility="public")
        risk = repo.get_default_risk("added", "tests/test_main.py")
        assert risk == RiskLevel.MEDIUM

    def test_closed_repo_modified_py_is_medium_risk(self, ae):
        """closed repo + modified .py → MEDIUM risk."""
        Repository = ae.Repository
        RiskLevel = ae.RiskLevel
        repo = Repository(path="/tmp/test", type="skill", visibility="closed")
        risk = repo.get_default_risk("modified", "src/main.py")
        assert risk == RiskLevel.MEDIUM

    def test_risk_override_takes_precedence(self, ae):
        """risk_override field takes precedence over default logic."""
        Repository = ae.Repository
        RiskLevel = ae.RiskLevel
        repo = Repository(path="/tmp/test", type="norms", visibility="public", risk_override="high")
        risk = repo.get_default_risk("added", "README.md")
        assert risk == RiskLevel.HIGH

    def test_default_risk_is_medium(self, ae):
        """Unmatched files default to MEDIUM risk."""
        Repository = ae.Repository
        RiskLevel = ae.RiskLevel
        repo = Repository(path="/tmp/test", type="skill", visibility="public")
        risk = repo.get_default_risk("added", "random.file")
        assert risk == RiskLevel.MEDIUM


# ===========================================================
# Test 5: PerspectiveConfig
# ===========================================================

class TestPerspectiveConfig:
    """Tests for PerspectiveConfig class."""

    def test_init_with_no_yaml_uses_fallback(self, ae, tmp_path):
        """When no yaml file exists, falls back to built-in 4-perspective default."""
        PerspectiveConfig = ae.PerspectiveConfig
        # Point to a non-existent path → will use fallback
        pc = PerspectiveConfig(config_path=tmp_path / "nonexistent.yaml")
        active = pc.get_active_perspectives()
        # Fallback includes the 4 core perspectives
        assert "USER" in active
        assert "PRODUCT" in active
        assert "PROJECT" in active
        assert "TECH" in active

    def test_get_active_perspectives_returns_list(self, ae):
        """get_active_perspectives() returns a list of strings."""
        PerspectiveConfig = ae.PerspectiveConfig
        pc = PerspectiveConfig(config_path=None)
        active = pc.get_active_perspectives()
        assert isinstance(active, list)
        assert len(active) > 0
        assert all(isinstance(p, str) for p in active)

    def test_get_levels_returns_dict(self, ae):
        """get_levels() returns {level: [perspective_names]}."""
        PerspectiveConfig = ae.PerspectiveConfig
        pc = PerspectiveConfig(config_path=None)
        levels = pc.get_levels()
        assert isinstance(levels, dict)
        assert all(isinstance(k, int) for k in levels.keys())
        assert all(isinstance(v, list) for v in levels.values())

    def test_get_perspective_returns_perspectivedef(self, ae):
        """get_perspective() returns a PerspectiveDef for known name."""
        PerspectiveConfig = ae.PerspectiveConfig
        pc = PerspectiveConfig(config_path=None)
        user_def = pc.get_perspective("USER")
        assert user_def is not None
        assert user_def.name == "USER"
        assert hasattr(user_def, "display_name")
        assert hasattr(user_def, "icon")
        assert hasattr(user_def, "execution_level")

    def test_get_perspective_returns_none_for_unknown(self, ae):
        """get_perspective() returns None for unknown perspective name."""
        PerspectiveConfig = ae.PerspectiveConfig
        pc = PerspectiveConfig(config_path=None)
        assert pc.get_perspective("NONEXISTENT") is None

    def test_project_weights_returns_dict(self, ae):
        """project_weights() returns perspective→float dict summing to ~1.0."""
        PerspectiveConfig = ae.PerspectiveConfig
        pc = PerspectiveConfig(config_path=None)
        weights = pc.project_weights("通用项目")
        assert isinstance(weights, dict)
        if weights:
            assert abs(sum(weights.values()) - 1.0) < 0.01


# ===========================================================
# Test 6: Scanner adapter pattern — skills.scanner_contract
# ===========================================================

class TestScannerContract:
    """Tests for skills.scanner_contract importable items."""

    def test_llm_evaluator_importable(self):
        """LLMEvaluator and EvaluationContext must be importable."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "scanner-contract"))
        try:
            from llm_evaluator import LLMEvaluator, EvaluationContext
            assert LLMEvaluator is not None
            assert EvaluationContext is not None
        finally:
            # Clean up sys.path
            sys.path.remove(str(Path(__file__).parent.parent / "skills" / "scanner-contract"))


# ===========================================================
# Test 7: FixEngine import — skills.fix_engine
# ===========================================================

class TestFixEngineImport:
    """Verify FixEngine can be imported from skills.fix_engine."""

    def test_fix_engine_importable(self):
        """FixEngine must be importable from skills.fix_engine.fix_engine."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "fix-engine"))
        try:
            from fix_engine import FixEngine
            assert FixEngine is not None
            assert callable(FixEngine)
        finally:
            sys.path.remove(str(Path(__file__).parent.parent / "skills" / "fix-engine"))

    def test_fix_engine_has_execute_method(self):
        """FixEngine must have an execute() method."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "fix-engine"))
        try:
            from fix_engine import FixEngine
            assert hasattr(FixEngine, "execute")
        finally:
            sys.path.remove(str(Path(__file__).parent.parent / "skills" / "fix-engine"))


# ===========================================================
# Test 8: TestingScanner import — skills.testing_scanner
# ===========================================================

class TestTestingScannerImport:
    """Verify TestingScanner can be imported from skills.testing_scanner."""

    def test_testing_scanner_importable(self):
        """TestingScanner must be importable from skills.testing_scanner.scanner."""
        base = Path(__file__).parent.parent
        sys.path.insert(0, str(base / "skills" / "scanner-contract"))
        sys.path.insert(0, str(base / "skills" / "testing-scanner"))
        try:
            from scanner import TestingScanner
            assert TestingScanner is not None
            assert callable(TestingScanner)
        finally:
            sys.path.remove(str(base / "skills" / "scanner-contract"))
            sys.path.remove(str(base / "skills" / "testing-scanner"))


# ===========================================================
# Test 9: Memory source detection
# ===========================================================

class TestMemorySources:
    """Tests for HawkBridgeMemory and OpenClawMemory."""

    def test_hawkbridge_memory_has_expected_methods(self):
        """HawkBridgeMemory must have is_available() and search() methods."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        try:
            from scripts.memory import HawkBridgeMemory
            mem = HawkBridgeMemory(workspace=Path("/tmp/nonexistent"))
            assert hasattr(mem, "is_available")
            assert callable(mem.is_available)
            assert hasattr(mem, "search")
            assert callable(mem.search)
            assert hasattr(mem, "get_preferences")
            assert callable(mem.get_preferences)
            # is_available() returns False for nonexistent path
            assert mem.is_available() is False
        finally:
            sys.path.remove(str(Path(__file__).parent.parent))

    def test_openclaw_memory_has_expected_methods(self):
        """OpenClawMemory must have is_available() and search() methods."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        try:
            from scripts.memory import OpenClawMemory
            mem = OpenClawMemory(workspace=Path("/tmp/nonexistent"))
            assert hasattr(mem, "is_available")
            assert callable(mem.is_available)
            assert hasattr(mem, "search")
            assert callable(mem.search)
            assert hasattr(mem, "get_recent")
            assert callable(mem.get_recent)
            # is_available() returns False for nonexistent path
            assert mem.is_available() is False
        finally:
            sys.path.remove(str(Path(__file__).parent.parent))

    def test_hawkbridge_memory_not_available_without_db(self, tmp_path):
        """HawkBridgeMemory.is_available() returns False when LanceDB is absent."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        try:
            from scripts.memory import HawkBridgeMemory
            mem = HawkBridgeMemory(workspace=tmp_path)
            assert mem.is_available() is False
        finally:
            sys.path.remove(str(Path(__file__).parent.parent))

    def test_openclaw_memory_not_available_without_db(self, tmp_path):
        """OpenClawMemory.is_available() returns False when SQLite is absent."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        try:
            from scripts.memory import OpenClawMemory
            mem = OpenClawMemory(workspace=tmp_path)
            assert mem.is_available() is False
        finally:
            sys.path.remove(str(Path(__file__).parent.parent))

    def test_persona_aware_memory_loads(self):
        """PersonaAwareMemory can be instantiated without error."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        try:
            from scripts.memory import PersonaAwareMemory
            mem = PersonaAwareMemory(recall_persona="", memory_source="auto")
            assert mem is not None
            assert hasattr(mem, "get_context_summary")
            assert hasattr(mem, "get_preferences")
            assert hasattr(mem, "search")
        finally:
            sys.path.remove(str(Path(__file__).parent.parent))


# ===========================================================
# Test 10: RiskLevel and ChangeCategory enums
# ===========================================================

class TestEnumsFromAutoEvolve:
    """RiskLevel and ChangeCategory are accessible from auto_evolve module."""

    def test_risk_level_has_three_values(self, ae):
        """RiskLevel must have LOW, MEDIUM, HIGH."""
        RiskLevel = ae.RiskLevel
        assert hasattr(RiskLevel, "LOW")
        assert hasattr(RiskLevel, "MEDIUM")
        assert hasattr(RiskLevel, "HIGH")
        values = [e.value for e in RiskLevel]
        assert set(values) == {"low", "medium", "high"}

    def test_change_category_has_expected_values(self, ae):
        """ChangeCategory must have expected enum values."""
        ChangeCategory = ae.ChangeCategory
        assert hasattr(ChangeCategory, "AUTO_EXEC")
        assert hasattr(ChangeCategory, "PENDING_APPROVAL")
        assert hasattr(ChangeCategory, "OPTIMIZATION")


# ===========================================================
# Test 11: FourPerspectiveScanner exists
# ===========================================================

class TestFourPerspectiveScanner:
    """FourPerspectiveScanner class must be importable and instantiable."""

    def test_four_perspective_scanner_exists(self, ae):
        """FourPerspectiveScanner must be defined in auto_evolve."""
        assert hasattr(ae, "FourPerspectiveScanner")
        FPS = ae.FourPerspectiveScanner
        assert callable(FPS)

    def test_four_perspective_scanner_can_be_instantiated(self, ae, tmp_path):
        """FourPerspectiveScanner can be instantiated with minimal args."""
        FourPerspectiveScanner = ae.FourPerspectiveScanner
        Repository = ae.Repository
        repo = Repository(path=str(tmp_path), type="skill", visibility="public")
        scanner = FourPerspectiveScanner(
            repos=[repo],
            config={},
            recall_persona="main",
            memory_source="auto",
        )
        assert scanner is not None
        assert hasattr(scanner, "scan")
        assert callable(scanner.scan)

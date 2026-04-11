"""Dataclasses for the fix-action registry system."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ActionType(str, Enum):
    """Standardized action vocabulary from fix-action-registry."""

    SUBSTITUTE_FILE = "substitute_file"
    SUBSTITUTE_BLOCK = "substitute_block"
    INSERT_LINE = "insert_line"
    DELETE_LINE = "delete_line"
    CREATE_FILE = "create_file"
    RENAME_FILE = "rename_file"
    ADD_TO_FILE = "add_to_file"
    ADD_ENVIRONMENT_VAR = "add_environment_var"
    RUN_COMMAND = "run_command"

    @classmethod
    def values(cls) -> list[str]:
        return [e.value for e in cls]


@dataclass
class FixAction:
    """A single standardized fix action."""

    type: ActionType
    params: dict[str, Any] = field(default_factory=dict)

    def get_param(self, key: str, default: Any = None) -> Any:
        """Get a parameter with optional default."""
        return self.params.get(key, default)

    @classmethod
    def substitute_file(cls, path: str, content: str) -> "FixAction":
        return cls(type=ActionType.SUBSTITUTE_FILE, params={"path": path, "content": content})

    @classmethod
    def substitute_block(cls, path: str, old_text: str, new_text: str, count: int = 1) -> "FixAction":
        return cls(
            type=ActionType.SUBSTITUTE_BLOCK,
            params={"path": path, "old_text": old_text, "new_text": new_text, "count": count},
        )

    @classmethod
    def insert_line(cls, path: str, line_number: int, content: str) -> "FixAction":
        return cls(
            type=ActionType.INSERT_LINE,
            params={"path": path, "line_number": line_number, "content": content},
        )

    @classmethod
    def delete_line(cls, path: str, start: int, end: Optional[int] = None) -> "FixAction":
        params = {"path": path, "start": start}
        if end is not None:
            params["end"] = end
        return cls(type=ActionType.DELETE_LINE, params=params)

    @classmethod
    def create_file(cls, path: str, content: str = "") -> "FixAction":
        return cls(type=ActionType.CREATE_FILE, params={"path": path, "content": content})

    @classmethod
    def rename_file(cls, old_path: str, new_path: str) -> "FixAction":
        return cls(type=ActionType.RENAME_FILE, params={"old_path": old_path, "new_path": new_path})

    @classmethod
    def add_to_file(cls, path: str, content: str) -> "FixAction":
        return cls(type=ActionType.ADD_TO_FILE, params={"path": path, "content": content})

    @classmethod
    def add_environment_var(cls, key: str, value: str, config_path: str = ".env") -> "FixAction":
        return cls(
            type=ActionType.ADD_ENVIRONMENT_VAR,
            params={"key": key, "value": value, "config_path": config_path},
        )

    @classmethod
    def run_command(cls, cmd: str, cwd: Optional[str] = None) -> "FixAction":
        params = {"cmd": cmd}
        if cwd is not None:
            params["cwd"] = cwd
        return cls(type=ActionType.RUN_COMMAND, params=params)


@dataclass
class FixResult:
    """Result of executing a fix action."""

    action: FixAction
    success: bool
    message: str
    dry_run: bool
    output: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action.type.value,
            "params": self.action.params,
            "success": self.success,
            "message": self.message,
            "dry_run": self.dry_run,
            "output": self.output,
            "error": self.error,
        }

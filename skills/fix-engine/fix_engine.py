"""FixEngine — executes standardized fix actions from fix-action-registry."""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

try:
    from .fix_action import ActionType, FixAction, FixResult
except ImportError:
    from fix_action import ActionType, FixAction, FixResult


class FixEngine:
    """Executes standardized fix actions from fix-action-registry.

    Safety:
        - dry_run=True by default — only log what would happen, don't execute
        - dry_run=False — actually modify files
        - All file operations use atomic writes where possible
        - Command execution uses subprocess with shell=False and timeout=30s
    """

    SUPPORTED_ACTIONS: set[str] = {a.value for a in ActionType}

    def __init__(self, repo_path: Path, dry_run: bool = True):
        self.repo_path = Path(repo_path)
        self.dry_run = dry_run
        self.execution_log: list[FixResult] = []

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def execute(self, fix_action: FixAction) -> FixResult:
        """Execute a single fix action. Returns result with success/failure."""
        handler_map = {
            ActionType.SUBSTITUTE_FILE: self._substitute_file,
            ActionType.SUBSTITUTE_BLOCK: self._substitute_block,
            ActionType.INSERT_LINE: self._insert_line,
            ActionType.DELETE_LINE: self._delete_line,
            ActionType.CREATE_FILE: self._create_file,
            ActionType.RENAME_FILE: self._rename_file,
            ActionType.ADD_TO_FILE: self._add_to_file,
            ActionType.ADD_ENVIRONMENT_VAR: self._add_environment_var,
            ActionType.RUN_COMMAND: self._run_command,
        }

        handler = handler_map.get(fix_action.type)
        if handler is None:
            result = FixResult(
                action=fix_action,
                success=False,
                message=f"Unsupported action type: {fix_action.type}",
                dry_run=self.dry_run,
                error="Unsupported action type",
            )
        else:
            result = handler(fix_action)

        self.execution_log.append(result)
        return result

    def execute_batch(self, actions: list[FixAction]) -> list[FixResult]:
        """Execute multiple fix actions, collecting results."""
        results = []
        for action in actions:
            result = self.execute(action)
            results.append(result)
            # Stop on first failure unless dry_run (still try all)
        return results

    def can_execute(self, action_type: str) -> bool:
        """Check if this action type is supported."""
        return action_type in self.SUPPORTED_ACTIONS

    # -------------------------------------------------------------------------
    # Action Handlers
    # -------------------------------------------------------------------------

    def _substitute_file(self, action: FixAction) -> FixResult:
        """Write new content to file (replaces entire file)."""
        path = self._resolve_path(action.get_param("path"), action)
        content = action.get_param("content", "")

        if self.dry_run:
            return FixResult(
                action=action,
                success=True,
                message=f"[DRY RUN] Would replace {path} with {len(content)} chars",
                dry_run=True,
            )

        try:
            # Atomic write: write to temp file then rename
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False
            ) as f:
                f.write(content)
                temp_path = Path(f.name)
            shutil.move(str(temp_path), str(path))
            return FixResult(
                action=action,
                success=True,
                message=f"Replaced {path} with {len(content)} chars",
                dry_run=False,
            )
        except Exception as e:
            return FixResult(
                action=action,
                success=False,
                message=f"Failed to substitute file {path}: {e}",
                dry_run=False,
                error=str(e),
            )

    def _substitute_block(self, action: FixAction) -> FixResult:
        """Replace a specific block (text region) within a file."""
        path = self._resolve_path(action.get_param("path"), action)
        old_text = action.get_param("old_text")
        new_text = action.get_param("new_text", "")
        count = action.get_param("count", 1)

        if old_text is None:
            return FixResult(
                action=action,
                success=False,
                message="substitute_block requires 'old_text' param",
                dry_run=self.dry_run,
                error="Missing old_text",
            )

        if self.dry_run:
            return FixResult(
                action=action,
                success=True,
                message=f"[DRY RUN] Would replace block in {path} (count={count})",
                dry_run=True,
            )

        try:
            content = path.read_text(encoding="utf-8")
            new_content, n = re.subn(re.escape(old_text), new_text, content, count=count)
            if n == 0:
                return FixResult(
                    action=action,
                    success=False,
                    message=f"Block not found in {path}",
                    dry_run=False,
                    error="Block not found",
                )
            path.write_text(new_content, encoding="utf-8")
            return FixResult(
                action=action,
                success=True,
                message=f"Replaced {n} occurrence(s) in {path}",
                dry_run=False,
            )
        except Exception as e:
            return FixResult(
                action=action,
                success=False,
                message=f"Failed to substitute block in {path}: {e}",
                dry_run=False,
                error=str(e),
            )

    def _insert_line(self, action: FixAction) -> FixResult:
        """Insert line at specific position (1-indexed)."""
        path = self._resolve_path(action.get_param("path"), action)
        line_number = action.get_param("line_number")
        content = action.get_param("content", "")

        if line_number is None:
            return FixResult(
                action=action,
                success=False,
                message="insert_line requires 'line_number' param",
                dry_run=self.dry_run,
                error="Missing line_number",
            )

        if self.dry_run:
            return FixResult(
                action=action,
                success=True,
                message=f"[DRY RUN] Would insert at line {line_number} in {path}",
                dry_run=True,
            )

        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            # Convert to 0-indexed; append if out of range
            idx = max(0, min(line_number - 1, len(lines)))
            lines.insert(idx, content + "\n")
            path.write_text("".join(lines), encoding="utf-8")
            return FixResult(
                action=action,
                success=True,
                message=f"Inserted at line {line_number} in {path}",
                dry_run=False,
            )
        except Exception as e:
            return FixResult(
                action=action,
                success=False,
                message=f"Failed to insert line in {path}: {e}",
                dry_run=False,
                error=str(e),
            )

    def _delete_line(self, action: FixAction) -> FixResult:
        """Delete specific line(s) by range."""
        path = self._resolve_path(action.get_param("path"), action)
        start = action.get_param("start")
        end = action.get_param("end")

        if start is None:
            return FixResult(
                action=action,
                success=False,
                message="delete_line requires 'start' param",
                dry_run=self.dry_run,
                error="Missing start",
            )

        end = end if end is not None else start

        if self.dry_run:
            return FixResult(
                action=action,
                success=True,
                message=f"[DRY RUN] Would delete lines {start}-{end} in {path}",
                dry_run=True,
            )

        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            # Convert to 0-indexed; clamp
            start_idx = max(0, start - 1)
            end_idx = min(len(lines), end)
            if start_idx >= len(lines):
                return FixResult(
                    action=action,
                    success=False,
                    message=f"Line {start} out of range in {path}",
                    dry_run=False,
                    error="Line out of range",
                )
            del lines[start_idx:end_idx]
            path.write_text("".join(lines), encoding="utf-8")
            return FixResult(
                action=action,
                success=True,
                message=f"Deleted lines {start}-{end} in {path}",
                dry_run=False,
            )
        except Exception as e:
            return FixResult(
                action=action,
                success=False,
                message=f"Failed to delete line in {path}: {e}",
                dry_run=False,
                error=str(e),
            )

    def _create_file(self, action: FixAction) -> FixResult:
        """Create a new file with optional content."""
        path = self._resolve_path(action.get_param("path"), action)
        content = action.get_param("content", "")

        if self.dry_run:
            return FixResult(
                action=action,
                success=True,
                message=f"[DRY RUN] Would create {path} with {len(content)} chars",
                dry_run=True,
            )

        try:
            if path.exists():
                return FixResult(
                    action=action,
                    success=False,
                    message=f"File already exists: {path}",
                    dry_run=False,
                    error="File exists",
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return FixResult(
                action=action,
                success=True,
                message=f"Created {path} with {len(content)} chars",
                dry_run=False,
            )
        except Exception as e:
            return FixResult(
                action=action,
                success=False,
                message=f"Failed to create file {path}: {e}",
                dry_run=False,
                error=str(e),
            )

    def _rename_file(self, action: FixAction) -> FixResult:
        """Rename or move a file."""
        old_path = self._resolve_path(action.get_param("old_path"), action)
        new_path = self._resolve_path(action.get_param("new_path"), action)

        if self.dry_run:
            return FixResult(
                action=action,
                success=True,
                message=f"[DRY RUN] Would rename {old_path} -> {new_path}",
                dry_run=True,
            )

        try:
            if not old_path.exists():
                return FixResult(
                    action=action,
                    success=False,
                    message=f"Source file does not exist: {old_path}",
                    dry_run=False,
                    error="Source does not exist",
                )
            new_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_path), str(new_path))
            return FixResult(
                action=action,
                success=True,
                message=f"Renamed {old_path} -> {new_path}",
                dry_run=False,
            )
        except Exception as e:
            return FixResult(
                action=action,
                success=False,
                message=f"Failed to rename {old_path}: {e}",
                dry_run=False,
                error=str(e),
            )

    def _add_to_file(self, action: FixAction) -> FixResult:
        """Append content to end of file."""
        path = self._resolve_path(action.get_param("path"), action)
        content = action.get_param("content", "")

        if self.dry_run:
            return FixResult(
                action=action,
                success=True,
                message=f"[DRY RUN] Would append {len(content)} chars to {path}",
                dry_run=True,
            )

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
            return FixResult(
                action=action,
                success=True,
                message=f"Appended {len(content)} chars to {path}",
                dry_run=False,
            )
        except Exception as e:
            return FixResult(
                action=action,
                success=False,
                message=f"Failed to append to {path}: {e}",
                dry_run=False,
                error=str(e),
            )

    def _add_environment_var(self, action: FixAction) -> FixResult:
        """Add an environment variable to a config file (.env format)."""
        key = action.get_param("key")
        value = action.get_param("value", "")
        config_path = action.get_param("config_path", ".env")

        if key is None:
            return FixResult(
                action=action,
                success=False,
                message="add_environment_var requires 'key' param",
                dry_run=self.dry_run,
                error="Missing key",
            )

        # Format: KEY="value" or KEY=value
        entry = f'{key}="{value}"'
        return self._add_to_file(
            FixAction(
                type=ActionType.ADD_TO_FILE,
                params={"path": config_path, "content": f"\n{entry}\n"},
            )
        )

    def _run_command(self, action: FixAction) -> FixResult:
        """Execute a shell command safely using subprocess (shell=False)."""
        cmd = action.get_param("cmd")
        cwd = action.get_param("cwd")

        if cmd is None:
            return FixResult(
                action=action,
                success=False,
                message="run_command requires 'cmd' param",
                dry_run=self.dry_run,
                error="Missing cmd",
            )

        resolved_cwd = self.repo_path
        if cwd:
            resolved_cwd = self._resolve_path(cwd, action)

        if self.dry_run:
            return FixResult(
                action=action,
                success=True,
                message=f"[DRY RUN] Would run: {cmd} (cwd={resolved_cwd})",
                dry_run=True,
            )

        try:
            result = subprocess.run(
                cmd,
                shell=False,
                cwd=str(resolved_cwd),
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0:
                return FixResult(
                    action=action,
                    success=True,
                    message=f"Command succeeded: {cmd}",
                    dry_run=False,
                    output=output,
                )
            else:
                return FixResult(
                    action=action,
                    success=False,
                    message=f"Command failed (exit {result.returncode}): {cmd}",
                    dry_run=False,
                    output=output,
                    error=f"Exit {result.returncode}",
                )
        except subprocess.TimeoutExpired:
            return FixResult(
                action=action,
                success=False,
                message=f"Command timed out after 30s: {cmd}",
                dry_run=False,
                error="Timeout",
            )
        except Exception as e:
            return FixResult(
                action=action,
                success=False,
                message=f"Failed to run command {cmd}: {e}",
                dry_run=False,
                error=str(e),
            )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _resolve_path(self, path_str: str, action: FixAction) -> Path:
        """Resolve a path string relative to repo_path."""
        if path_str is None:
            raise ValueError(f"Action {action.type} requires a path parameter")
        p = Path(path_str)
        if p.is_absolute():
            return p
        return self.repo_path / p

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath


class PathPolicyError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


@dataclass(frozen=True)
class ResolvedWorkspacePath:
    relative_path: str
    absolute_path: Path


class WorkspacePathPolicy:
    def __init__(self, root_path: str) -> None:
        self.root = Path(root_path).resolve(strict=True)
        if not self.root.is_dir():
            raise PathPolicyError("WORKSPACE_NOT_DIRECTORY", "Workspace root is not a directory.")

    def resolve_existing(self, relative_path: str) -> ResolvedWorkspacePath:
        return self._resolve(relative_path, must_exist=True, for_directory=False)

    def resolve_directory(self, relative_path: str) -> ResolvedWorkspacePath:
        resolved = self._resolve(relative_path, must_exist=True, for_directory=True)
        if not resolved.absolute_path.is_dir():
            raise PathPolicyError("NOT_DIRECTORY", "Path is not a directory.")
        return resolved

    def resolve_new_child(self, relative_path: str) -> ResolvedWorkspacePath:
        return self._resolve(relative_path, must_exist=False, for_directory=False)

    def ensure_distinct(self, source: Path, destination: Path) -> None:
        if os.path.normcase(str(source.resolve(strict=True))) == os.path.normcase(str(destination.resolve(strict=False))):
            raise PathPolicyError("SAME_PATH", "Source and destination refer to the same path.")

    def _resolve(self, relative_path: str, *, must_exist: bool, for_directory: bool) -> ResolvedWorkspacePath:
        candidate_text = self._validate_relative_text(relative_path)
        candidate = self.root / candidate_text
        parent = candidate if for_directory else candidate.parent
        resolved_parent = parent.resolve(strict=True)
        self._ensure_inside(resolved_parent)
        resolved = candidate.resolve(strict=must_exist)
        self._ensure_inside(resolved)
        if must_exist:
            self._reject_reparse_escape(candidate, resolved)
        return ResolvedWorkspacePath(relative_path=candidate_text, absolute_path=resolved)

    def _validate_relative_text(self, relative_path: str) -> str:
        value = relative_path.strip().replace("/", "\\")
        if not value or value in {".", "\\"}:
            return "."
        pure = PureWindowsPath(value)
        if pure.is_absolute() or value.startswith("\\") or value.startswith("//"):
            raise PathPolicyError("ABSOLUTE_PATH_REJECTED", "Absolute, UNC, and rooted paths are not allowed.")
        if value.startswith("\\\\?\\") or value.startswith("\\\\.\\"):
            raise PathPolicyError("DEVICE_PATH_REJECTED", "Windows device paths are not allowed.")
        parts = [part for part in pure.parts if part not in {"", "."}]
        if any(part == ".." for part in parts):
            raise PathPolicyError("PATH_TRAVERSAL_REJECTED", "Path traversal is not allowed.")
        for part in parts:
            if ":" in part:
                raise PathPolicyError("ADS_REJECTED", "Alternate data streams and drive-qualified paths are not allowed.")
            stem = re.split(r"[. ]+", part)[0].upper()
            if stem in WINDOWS_RESERVED:
                raise PathPolicyError("RESERVED_NAME_REJECTED", "Windows reserved device names are not allowed.")
        return str(PureWindowsPath(*parts)) if parts else "."

    def _ensure_inside(self, path: Path) -> None:
        root = os.path.normcase(str(self.root))
        candidate = os.path.normcase(str(path))
        if os.path.commonpath([root, candidate]) != root:
            raise PathPolicyError("WORKSPACE_ESCAPE_REJECTED", "Resolved path escapes the workspace.")

    def _reject_reparse_escape(self, original: Path, resolved: Path) -> None:
        if original.exists() and (original.is_symlink() or os.path.normcase(str(original.absolute())) != os.path.normcase(str(resolved))):
            self._ensure_inside(resolved)

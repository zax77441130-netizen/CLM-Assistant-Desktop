from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.path_policy import PathPolicyError, WorkspacePathPolicy
from app.engineering.command_catalog import EngineeringCommandAvailability
from app.engineering.command_runner import EngineeringCommandRunner
from app.models import WorkspaceGrant


IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".runtime",
    ".venv",
    ".venv-win",
    "__pycache__",
    "build",
    "dist",
    "dist-electron",
    "node_modules",
    "release",
    "venv",
}
MAX_SCAN_DEPTH = 8
MAX_MARKER_DEPTH = 4
MAX_SCAN_FILES = 10_000
MAX_MARKERS = 200
MAX_ENTRYPOINTS = 50
MAX_GIT_TEXT_BYTES = 1024 * 1024
SAFE_GIT_REF = re.compile(r"^refs/[A-Za-z0-9._/-]+$")
SAFE_COMMIT = re.compile(r"^[0-9a-fA-F]{40}$")


class GitContext(BaseModel):
    detected: bool = False
    branch: str | None = None
    commit: str | None = None
    dirty: bool | None = None


class ScanContext(BaseModel):
    fileCount: int = 0
    directoryCount: int = 0
    truncated: bool = False
    maxDepth: int = MAX_SCAN_DEPTH


class EngineeringProjectContextResponse(BaseModel):
    workspaceId: str
    projectName: str
    stacks: list[str] = Field(default_factory=list)
    markers: list[str] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    testCommands: list[str] = Field(default_factory=list)
    buildCommands: list[str] = Field(default_factory=list)
    testReadiness: EngineeringCommandAvailability
    buildReadiness: EngineeringCommandAvailability
    git: GitContext = Field(default_factory=GitContext)
    scan: ScanContext = Field(default_factory=ScanContext)


class ProjectContextError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ProjectContextService:
    """Inspect a grant and perform bounded, non-mutating runner readiness probes."""

    def __init__(self, command_runner: EngineeringCommandRunner | None = None) -> None:
        self._command_runner = command_runner or EngineeringCommandRunner()

    def inspect(self, grant: WorkspaceGrant) -> EngineeringProjectContextResponse:
        if not grant.enabled:
            raise ProjectContextError("WORKSPACE_DISABLED")
        try:
            policy = WorkspacePathPolicy(grant.root_path)
            root = policy.resolve_directory(".").absolute_path
        except (OSError, RuntimeError, PathPolicyError) as exc:
            raise ProjectContextError("WORKSPACE_UNAVAILABLE") from exc
        markers = self._markers(root)
        stacks = self._stacks(markers)
        entrypoints = self._entrypoints(root)
        test_readiness = self._command_runner.availability(str(root), "test")
        build_readiness = self._command_runner.availability(str(root), "build")
        test_commands = (
            [test_readiness.displayCommand]
            if test_readiness.status == "READY" and test_readiness.displayCommand
            else []
        )
        build_commands = (
            [build_readiness.displayCommand]
            if build_readiness.status == "READY" and build_readiness.displayCommand
            else []
        )
        return EngineeringProjectContextResponse(
            workspaceId=grant.id,
            projectName=grant.display_name or root.name,
            stacks=stacks,
            markers=markers,
            entrypoints=entrypoints,
            testCommands=test_commands,
            buildCommands=build_commands,
            testReadiness=test_readiness,
            buildReadiness=build_readiness,
            git=self._git_context(root),
            scan=self._scan(root),
        )

    def _markers(self, root: Path) -> list[str]:
        names = {
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "tsconfig.json",
            "tsconfig.base.json",
            "pyproject.toml",
            "requirements.txt",
            "Pipfile",
            "pubspec.yaml",
            "Cargo.toml",
            "go.mod",
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
        }
        found: list[str] = []
        for current, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            try:
                depth = len(current_path.relative_to(root).parts)
            except ValueError:
                break
            dir_names[:] = [
                name
                for name in sorted(dir_names)
                if name not in IGNORED_DIRECTORIES
                and depth < MAX_MARKER_DEPTH
                and not self._is_link_or_junction(current_path / name)
            ]
            for name in sorted(set(file_names) & names):
                candidate = current_path / name
                if self._safe_file(candidate):
                    found.append(candidate.relative_to(root).as_posix())
                    if len(found) >= MAX_MARKERS:
                        return found
        return found

    def _stacks(self, markers: list[str]) -> list[str]:
        found: set[str] = set()
        marker_names = {Path(marker).name for marker in markers}
        if "package.json" in marker_names:
            found.add("node")
        if marker_names & {"tsconfig.json", "tsconfig.base.json"}:
            found.add("typescript")
        if marker_names & {"pyproject.toml", "requirements.txt", "Pipfile"}:
            found.add("python")
        if "pubspec.yaml" in marker_names:
            found.add("flutter")
        if "Cargo.toml" in marker_names:
            found.add("rust")
        if "go.mod" in marker_names:
            found.add("go")
        if marker_names & {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
            found.add("docker")
        return sorted(found)

    def _entrypoints(self, root: Path) -> list[str]:
        names = {
            "Program.cs",
            "index.ts",
            "index.tsx",
            "main.dart",
            "main.go",
            "main.py",
            "main.ts",
            "main.tsx",
        }
        found: list[str] = []
        for current, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            try:
                depth = len(current_path.relative_to(root).parts)
            except ValueError:
                break
            dir_names[:] = [
                name
                for name in sorted(dir_names)
                if name not in IGNORED_DIRECTORIES
                and depth < MAX_MARKER_DEPTH
                and not self._is_link_or_junction(current_path / name)
            ]
            for name in sorted(set(file_names) & names):
                candidate = current_path / name
                if self._safe_file(candidate):
                    found.append(candidate.relative_to(root).as_posix())
                    if len(found) >= MAX_ENTRYPOINTS:
                        return found
        return found

    def _git_context(self, root: Path) -> GitContext:
        git_dir = root / ".git"
        if self._safe_file(git_dir):
            return GitContext(detected=True)
        if not self._safe_directory(git_dir):
            return GitContext()
        head = self._read_small_text(git_dir / "HEAD", 4096)
        if not head:
            return GitContext(detected=True)
        head = head.strip()
        if SAFE_COMMIT.fullmatch(head):
            return GitContext(detected=True, commit=head.lower())
        if not head.startswith("ref: "):
            return GitContext(detected=True)
        reference = head[5:].strip()
        if not SAFE_GIT_REF.fullmatch(reference) or ".." in reference.split("/"):
            return GitContext(detected=True)
        commit = self._read_small_text(git_dir.joinpath(*reference.split("/")), 4096)
        commit = commit.strip().lower() if commit else None
        if commit and not SAFE_COMMIT.fullmatch(commit):
            commit = None
        branch = (
            reference.removeprefix("refs/heads/")
            if reference.startswith("refs/heads/")
            else None
        )
        return GitContext(detected=True, branch=branch, commit=commit)

    def _scan(self, root: Path) -> ScanContext:
        files = 0
        directories = 0
        truncated = False
        for current, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            try:
                depth = len(current_path.relative_to(root).parts)
            except ValueError:
                truncated = True
                break
            had_deeper_directories = bool(dir_names)
            safe_dirs: list[str] = []
            if depth < MAX_SCAN_DEPTH:
                for name in sorted(dir_names):
                    candidate = current_path / name
                    if name in IGNORED_DIRECTORIES or self._is_link_or_junction(candidate):
                        continue
                    safe_dirs.append(name)
            dir_names[:] = safe_dirs
            directories += len(safe_dirs)
            files += len(file_names)
            if files >= MAX_SCAN_FILES:
                files = MAX_SCAN_FILES
                truncated = True
                break
            if depth >= MAX_SCAN_DEPTH and had_deeper_directories:
                truncated = True
                dir_names[:] = []
        return ScanContext(
            fileCount=files,
            directoryCount=directories,
            truncated=truncated,
        )

    def _read_small_text(self, path: Path, maximum: int) -> str | None:
        if not self._safe_file(path) or path.stat().st_size > min(maximum, MAX_GIT_TEXT_BYTES):
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def _safe_file(self, path: Path) -> bool:
        try:
            return path.is_file() and not self._is_link_or_junction(path)
        except OSError:
            return False

    def _safe_directory(self, path: Path) -> bool:
        try:
            return path.is_dir() and not self._is_link_or_junction(path)
        except OSError:
            return False

    def _is_link_or_junction(self, path: Path) -> bool:
        try:
            is_junction = getattr(path, "is_junction", None)
            return path.is_symlink() or bool(is_junction and is_junction())
        except OSError:
            return True

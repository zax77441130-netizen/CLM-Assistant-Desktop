from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


MAX_PROJECT_UNIT_DEPTH = 4
MAX_PROJECT_UNITS = 32
MAX_MANIFEST_BYTES = 1024 * 1024
PROJECT_SCAN_IGNORES = {
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
PYTHON_MARKERS = ("pyproject.toml", "requirements.txt", "Pipfile")
ReadinessStatus = Literal[
    "READY",
    "MISSING_TOOL",
    "MISSING_DEPENDENCY",
    "NO_SCRIPT",
    "AMBIGUOUS",
    "UNSUPPORTED",
]


class EngineeringCommandAvailability(BaseModel):
    commandId: str
    status: ReadinessStatus
    reasonCode: str
    reason: str
    displayCommand: str | None = None
    projectRelativePath: str | None = None
    candidateCount: int = 0


@dataclass(frozen=True)
class CommandCandidate:
    command_id: str
    display_command: str
    runner_kind: str
    source_relative_path: str
    working_relative_path: str


class ProjectCommandCatalog:
    """Discover fixed project actions and prove that their local runner is ready."""

    WINDOWS_SCRIPTS = {
        "test": ("scripts/test_windows.ps1", r".\scripts\test_windows.ps1"),
        "build": ("scripts/build_desktop.ps1", r".\scripts\build_desktop.ps1"),
    }

    def __init__(
        self,
        *,
        executable_resolver: Callable[[str], str | None] | None = None,
        python_probe: Callable[[str], bool] | None = None,
    ) -> None:
        self._executable_resolver = executable_resolver or self._find_executable
        self._python_probe = python_probe or self._probe_pytest
        self._python_probe_cache: dict[str, bool] = {}

    def inspect(
        self, root: Path, command_id: str
    ) -> tuple[EngineeringCommandAvailability, CommandCandidate | None]:
        if command_id not in {"test", "build"}:
            return (
                EngineeringCommandAvailability(
                    commandId=command_id,
                    status="UNSUPPORTED",
                    reasonCode="ENGINEERING_COMMAND_NOT_ALLOWED",
                    reason="此工程動作不在允許清單中。",
                ),
                None,
            )
        candidates = self._candidates(root, command_id)
        if not candidates:
            return (
                EngineeringCommandAvailability(
                    commandId=command_id,
                    status="NO_SCRIPT",
                    reasonCode="ENGINEERING_COMMAND_UNAVAILABLE",
                    reason="專案沒有宣告可辨識的測試或建置腳本。",
                ),
                None,
            )

        assessed = [(candidate, *self._assess(root, candidate)) for candidate in candidates]
        ready = [item for item in assessed if item[1] == "READY"]
        root_ready = [item for item in ready if item[0].working_relative_path == "."]
        if len(root_ready) == 1:
            ready = root_ready
        if len(ready) > 1:
            return (
                EngineeringCommandAvailability(
                    commandId=command_id,
                    status="AMBIGUOUS",
                    reasonCode="ENGINEERING_COMMAND_AMBIGUOUS",
                    reason=f"偵測到 {len(ready)} 個可執行工作單元，需先選擇子專案。",
                    candidateCount=len(candidates),
                ),
                None,
            )
        selected = ready[0] if ready else assessed[0]
        candidate, status, reason_code, reason = selected
        availability = EngineeringCommandAvailability(
            commandId=command_id,
            status=status,
            reasonCode=reason_code,
            reason=reason,
            displayCommand=candidate.display_command,
            projectRelativePath=candidate.working_relative_path,
            candidateCount=len(candidates),
        )
        return availability, candidate if status == "READY" else None

    def resolve_executable(self, runner_kind: str) -> str | None:
        return self._executable_resolver(runner_kind)

    def python_executable(self, root: Path, working_relative_path: str) -> str | None:
        unit = root if working_relative_path == "." else root / working_relative_path
        search_roots = [unit]
        if unit != root:
            search_roots.append(root)
        for search_root in search_roots:
            for relative in (
                ".venv-win/Scripts/python.exe",
                ".venv/Scripts/python.exe",
                "venv/Scripts/python.exe",
            ):
                candidate = search_root / relative
                if self._is_regular_file(candidate):
                    return str(candidate.resolve(strict=True))
        return self._executable_resolver("python")

    def _candidates(self, root: Path, command_id: str) -> list[CommandCandidate]:
        script_path, display = self.WINDOWS_SCRIPTS[command_id]
        if self._is_regular_file(root / script_path):
            return [CommandCandidate(command_id, display, "powershell", script_path, ".")]

        candidates: list[CommandCandidate] = []
        python_units: set[str] = set()
        for current, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            try:
                depth = len(current_path.relative_to(root).parts)
            except ValueError:
                break
            dir_names[:] = [
                name
                for name in sorted(dir_names)
                if name not in PROJECT_SCAN_IGNORES
                and depth < MAX_PROJECT_UNIT_DEPTH
                and not self._is_link_or_junction(current_path / name)
            ]
            working = self._relative(root, current_path)
            if "package.json" in file_names:
                manifest = current_path / "package.json"
                payload = self._package_payload(manifest)
                scripts = payload.get("scripts") if payload else None
                if isinstance(scripts, dict) and command_id in scripts:
                    manager = self._package_manager(root, current_path, payload)
                    display_command = (
                        "npm test"
                        if manager == "npm" and command_id == "test"
                        else f"{manager} run {command_id}"
                    )
                    candidates.append(
                        CommandCandidate(
                            command_id,
                            display_command,
                            manager,
                            self._relative(root, manifest),
                            working,
                        )
                    )
            if command_id == "test":
                for marker_name in PYTHON_MARKERS:
                    if marker_name not in file_names:
                        continue
                    marker = current_path / marker_name
                    if self._is_regular_file(marker) and working not in python_units:
                        python_units.add(working)
                        candidates.append(
                            CommandCandidate(
                                command_id,
                                "python -m pytest",
                                "python",
                                self._relative(root, marker),
                                working,
                            )
                        )
                    break
            if len(candidates) >= MAX_PROJECT_UNITS:
                break
        return candidates

    def _assess(
        self, root: Path, candidate: CommandCandidate
    ) -> tuple[ReadinessStatus, str, str]:
        if candidate.runner_kind == "powershell":
            return "READY", "ENGINEERING_COMMAND_READY", "專案腳本與 Windows 執行環境已就緒。"
        if candidate.runner_kind in {"npm", "pnpm", "yarn"}:
            if self._executable_resolver(candidate.runner_kind) is None:
                return (
                    "MISSING_TOOL",
                    "ENGINEERING_PACKAGE_MANAGER_UNAVAILABLE",
                    f"找不到 {candidate.runner_kind}；請先安裝或啟用對應套件管理器。",
                )
            manifest = root / candidate.source_relative_path
            payload = self._package_payload(manifest)
            dependencies = payload.get("dependencies")
            dev_dependencies = payload.get("devDependencies")
            declares_dependencies = any(
                isinstance(item, dict) and bool(item)
                for item in (dependencies, dev_dependencies)
            )
            unit = root if candidate.working_relative_path == "." else root / candidate.working_relative_path
            dependency_roots = (unit / "node_modules", root / "node_modules", unit / ".pnp.cjs")
            if declares_dependencies and not any(path.exists() for path in dependency_roots):
                return (
                    "MISSING_DEPENDENCY",
                    "ENGINEERING_NODE_DEPENDENCIES_UNAVAILABLE",
                    "尚未安裝此工作單元的 Node 依賴，因此不會開放執行。",
                )
            return "READY", "ENGINEERING_COMMAND_READY", "套件管理器與專案腳本已就緒。"
        if candidate.runner_kind == "python":
            executable = self.python_executable(root, candidate.working_relative_path)
            if executable is None:
                return (
                    "MISSING_TOOL",
                    "ENGINEERING_PYTHON_UNAVAILABLE",
                    "找不到此工作單元可用的 Python 執行環境。",
                )
            available = self._python_probe_cache.get(executable)
            if available is None:
                available = self._python_probe(executable)
                self._python_probe_cache[executable] = available
            if not available:
                return (
                    "MISSING_DEPENDENCY",
                    "ENGINEERING_PYTEST_UNAVAILABLE",
                    "此 Python 環境尚未安裝 pytest，因此不會開放執行。",
                )
            return "READY", "ENGINEERING_COMMAND_READY", "Python 與 pytest 已就緒。"
        return "UNSUPPORTED", "ENGINEERING_RUNNER_UNSUPPORTED", "此專案執行方式尚未支援。"

    def _package_payload(self, path: Path) -> dict[str, object]:
        if not self._is_regular_file(path) or path.stat().st_size > MAX_MANIFEST_BYTES:
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _package_manager(
        self, root: Path, unit: Path, payload: dict[str, object]
    ) -> str:
        declared = payload.get("packageManager")
        if isinstance(declared, str):
            manager = declared.split("@", 1)[0].lower()
            if manager in {"npm", "pnpm", "yarn"}:
                return manager
        current = unit
        while True:
            if self._is_regular_file(current / "pnpm-lock.yaml"):
                return "pnpm"
            if self._is_regular_file(current / "yarn.lock"):
                return "yarn"
            if current == root:
                break
            try:
                current.relative_to(root)
            except ValueError:
                break
            current = current.parent
        return "npm"

    def _find_executable(self, name: str) -> str | None:
        names = [name]
        if os.name == "nt" and not name.lower().endswith((".cmd", ".exe")):
            names.insert(0, f"{name}.cmd" if name in {"npm", "pnpm", "yarn"} else f"{name}.exe")
        for candidate_name in names:
            found = shutil.which(candidate_name, path=os.environ.get("PATH"))
            if not found:
                continue
            try:
                resolved = Path(found).resolve(strict=True)
            except OSError:
                continue
            allowed_names = {Path(item).name.lower() for item in names}
            if resolved.is_file() and resolved.name.lower() in allowed_names:
                return str(resolved)
        return None

    def _probe_pytest(self, executable: str) -> bool:
        try:
            completed = subprocess.run(
                [
                    executable,
                    "-I",
                    "-c",
                    "from importlib.util import find_spec; raise SystemExit(0 if find_spec('pytest') else 1)",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0

    def _relative(self, root: Path, path: Path) -> str:
        relative = path.relative_to(root).as_posix()
        return relative or "."

    def _is_regular_file(self, path: Path) -> bool:
        try:
            return path.is_file() and not self._is_link_or_junction(path)
        except OSError:
            return False

    def _is_link_or_junction(self, path: Path) -> bool:
        try:
            is_junction = getattr(path, "is_junction", None)
            return path.is_symlink() or bool(is_junction and is_junction())
        except OSError:
            return True

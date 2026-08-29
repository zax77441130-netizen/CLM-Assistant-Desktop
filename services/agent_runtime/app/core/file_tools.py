from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.path_policy import WorkspacePathPolicy
from app.core.tool_sdk import ToolEvidence, ToolResult, now_utc

MAX_READ_BYTES = 200 * 1024
SYSTEM_MAX_READ_BYTES = 1024 * 1024


class WorkspaceInput(BaseModel):
    workspace_root: str
    path: str = "."


class ReadTextInput(WorkspaceInput):
    max_bytes: int = Field(default=MAX_READ_BYTES, gt=0, le=SYSTEM_MAX_READ_BYTES)


class SearchInput(WorkspaceInput):
    query: str = Field(min_length=1, max_length=120)
    search_content: bool = False
    max_results: int = Field(default=50, gt=0, le=200)
    max_file_bytes: int = Field(default=MAX_READ_BYTES, gt=0, le=SYSTEM_MAX_READ_BYTES)
    max_depth: int = Field(default=5, ge=0, le=20)


class BinaryWriteInput(WorkspaceInput):
    destination: str


class WriteTextInput(WorkspaceInput):
    content: str = Field(max_length=SYSTEM_MAX_READ_BYTES)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_binary(path: Path, sample_size: int = 4096) -> bool:
    sample = path.read_bytes()[:sample_size]
    return b"\x00" in sample


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp_name = handle.name
    os.replace(temp_name, path)


def ok(summary: str, observation: dict[str, Any], *, side_effect: bool = False, undo_record_id: str | None = None) -> ToolResult:
    started = now_utc()
    return ToolResult(
        success=True,
        status="COMPLETED",
        summary=summary,
        observation=observation,
        evidence=[ToolEvidence(kind="structured_observation", data=observation)],
        side_effect=side_effect,
        undo_record_id=undo_record_id,
        started_at=started,
        finished_at=now_utc(),
    )


def verified_postcondition(**items: Any) -> dict[str, Any]:
    return {"verified": True, "inside_workspace": True, **items}


def list_directory(workspace_root: str, path: str = ".", limit: int = 100) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    target = policy.resolve_directory(path).absolute_path
    entries = []
    for child in sorted(target.iterdir(), key=lambda item: item.name.lower())[:limit]:
        rel = child.relative_to(policy.root).as_posix()
        entries.append({"path": rel, "type": "directory" if child.is_dir() else "file", "is_symlink": child.is_symlink()})
    return ok("Directory listed.", {"path": path, "entries": entries, "limit": limit})


def stat_path(workspace_root: str, path: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    target = policy.resolve_existing(path).absolute_path
    stat = target.lstat()
    return ok(
        "Path stat collected.",
        {
            "path": path,
            "type": "directory" if target.is_dir() else "file",
            "size": stat.st_size,
            "modified_at": stat.st_mtime,
            "is_symlink": target.is_symlink(),
            "is_junction_or_reparse": False,
        },
    )


def read_text(workspace_root: str, path: str, max_bytes: int = MAX_READ_BYTES) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    target = policy.resolve_existing(path).absolute_path
    if not target.is_file():
        raise ValueError("NOT_FILE")
    if target.stat().st_size > max_bytes:
        raise ValueError("READ_LIMIT_EXCEEDED")
    if is_binary(target):
        raise ValueError("BINARY_REJECTED")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("DECODE_FAILED") from exc
    return ok("Text file read.", {"path": path, "content": content, "bytes": len(content.encode("utf-8"))})


def search(workspace_root: str, path: str, query: str, *, search_content: bool, max_results: int, max_file_bytes: int, max_depth: int) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    root = policy.resolve_directory(path).absolute_path
    results = []
    for current, dirs, files in os.walk(root):
        rel_current = Path(current).relative_to(root)
        if len(rel_current.parts) >= max_depth:
            dirs[:] = []
        for name in files:
            candidate = Path(current) / name
            rel = candidate.relative_to(policy.root).as_posix()
            matched = query.lower() in name.lower()
            if search_content and candidate.stat().st_size <= max_file_bytes and not is_binary(candidate):
                try:
                    matched = matched or query.lower() in candidate.read_text(encoding="utf-8").lower()
                except UnicodeDecodeError:
                    matched = matched or False
            if matched:
                results.append({"path": rel})
            if len(results) >= max_results:
                return ok("Search completed with limit.", {"results": results, "limited": True})
    return ok("Search completed.", {"results": results, "limited": False})


def hash_file(workspace_root: str, path: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    target = policy.resolve_existing(path).absolute_path
    if not target.is_file():
        raise ValueError("NOT_FILE")
    return ok("SHA-256 calculated.", {"path": path, "sha256": sha256_file(target), "size": target.stat().st_size})


def find_duplicates(workspace_root: str, path: str = ".") -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    root = policy.resolve_directory(path).absolute_path
    by_size: dict[int, list[Path]] = {}
    for current, _, files in os.walk(root):
        for name in files:
            candidate = Path(current) / name
            by_size.setdefault(candidate.stat().st_size, []).append(candidate)
    duplicates: list[dict[str, Any]] = []
    for group in by_size.values():
        if len(group) < 2:
            continue
        by_hash: dict[str, list[str]] = {}
        for item in group:
            by_hash.setdefault(sha256_file(item), []).append(item.relative_to(policy.root).as_posix())
        duplicates.extend({"sha256": digest, "paths": paths} for digest, paths in by_hash.items() if len(paths) > 1)
    return ok("Duplicate report generated.", {"duplicates": duplicates})


def create_directory(workspace_root: str, path: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    target = policy.resolve_new_child(path).absolute_path
    existed = target.exists()
    target.mkdir(parents=True, exist_ok=True)
    verified = policy.resolve_directory(path).absolute_path
    if not verified.exists() or not verified.is_dir():
        raise ValueError("POSTCONDITION_DIRECTORY_MISSING")
    return ok(
        "Directory ensured.",
        {"path": path, "existed": existed, "postcondition": verified_postcondition(exists=True, is_directory=True)},
        side_effect=not existed,
    )


def write_new_text(workspace_root: str, path: str, content: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    target = policy.resolve_new_child(path).absolute_path
    if target.exists():
        raise ValueError("DESTINATION_EXISTS")
    atomic_write(target, content)
    verified = policy.resolve_existing(path).absolute_path
    if not verified.is_file():
        raise ValueError("POSTCONDITION_FILE_MISSING")
    digest = sha256_file(verified)
    return ok(
        "New text file written.",
        {"path": path, "sha256": digest, "postcondition": verified_postcondition(exists=True, is_file=True, sha256=digest)},
        side_effect=True,
    )


def copy_file(workspace_root: str, path: str, destination: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    source = policy.resolve_existing(path).absolute_path
    dest = policy.resolve_new_child(destination).absolute_path
    policy.ensure_distinct(source, dest)
    if dest.exists():
        raise ValueError("DESTINATION_EXISTS")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    verified = policy.resolve_existing(destination).absolute_path
    source_hash = sha256_file(source)
    dest_hash = sha256_file(verified) if verified.is_file() else ""
    if source.stat().st_size != verified.stat().st_size or source_hash != dest_hash:
        raise ValueError("COPY_SIZE_MISMATCH")
    return ok(
        "File copied.",
        {
            "source": path,
            "destination": destination,
            "sha256": dest_hash,
            "postcondition": verified_postcondition(exists=True, is_file=True, source_missing=False, sha256=dest_hash),
        },
        side_effect=True,
    )


def move_file(workspace_root: str, path: str, destination: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    source = policy.resolve_existing(path).absolute_path
    dest = policy.resolve_new_child(destination).absolute_path
    policy.ensure_distinct(source, dest)
    if dest.exists():
        raise ValueError("DESTINATION_EXISTS")
    dest.parent.mkdir(parents=True, exist_ok=True)
    before_hash = sha256_file(source) if source.is_file() else None
    shutil.move(str(source), str(dest))
    after = policy.resolve_existing(destination).absolute_path
    if source.exists():
        raise ValueError("POSTCONDITION_SOURCE_STILL_EXISTS")
    after_hash = sha256_file(after) if after.is_file() else None
    if before_hash and after_hash != before_hash:
        raise ValueError("MOVE_HASH_MISMATCH")
    return ok(
        "File moved.",
        {
            "source": path,
            "destination": destination,
            "sha256": before_hash,
            "postcondition": verified_postcondition(exists=True, source_missing=True, sha256=after_hash),
        },
        side_effect=True,
    )


def overwrite_text_with_backup(workspace_root: str, path: str, content: str, expected_sha256: str, backup_dir: Path) -> tuple[ToolResult, Path, str]:
    policy = WorkspacePathPolicy(workspace_root)
    target = policy.resolve_existing(path).absolute_path
    if not target.is_file():
        raise ValueError("NOT_FILE")
    current_hash = sha256_file(target)
    if current_hash != expected_sha256:
        raise ValueError("FILE_CHANGED_WHILE_WAITING")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{target.name}.{current_hash}.bak"
    shutil.copyfile(target, backup)
    atomic_write(target, content)
    verified = policy.resolve_existing(path).absolute_path
    if not verified.is_file():
        raise ValueError("POSTCONDITION_FILE_MISSING")
    new_hash = sha256_file(verified)
    return (
        ok(
            "Text file overwritten.",
            {"path": path, "previous_sha256": current_hash, "sha256": new_hash, "postcondition": verified_postcondition(exists=True, is_file=True, sha256=new_hash)},
            side_effect=True,
        ),
        backup,
        new_hash,
    )

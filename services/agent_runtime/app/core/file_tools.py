from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.path_policy import WorkspacePathPolicy
from app.core.tool_sdk import ToolEvidence, ToolResult, now_utc

MAX_READ_BYTES = 200 * 1024
SYSTEM_MAX_READ_BYTES = 1024 * 1024
MAX_WALK_ITEMS = 1000
MAX_ARCHIVE_ITEMS = 500
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
DEFAULT_RECOVERY_BIN_MAX_BYTES = 1024 * 1024 * 1024


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


def _iter_files(policy: WorkspacePathPolicy, root: Path, *, max_depth: int, limit: int) -> list[Path]:
    results: list[Path] = []
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        rel_current = current_path.relative_to(root)
        if len(rel_current.parts) >= max_depth:
            dirs[:] = []
            if rel_current.parts:
                continue
        dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]
        for name in files:
            candidate = current_path / name
            if candidate.is_symlink():
                continue
            resolved = candidate.resolve(strict=True)
            policy._ensure_inside(resolved)  # noqa: SLF001
            results.append(resolved)
            if len(results) >= limit:
                return results
    return results


def _resolve_new_descendant(policy: WorkspacePathPolicy, relative_path: str) -> Path:
    candidate_text = policy._validate_relative_text(relative_path)  # noqa: SLF001
    candidate = policy.root / candidate_text
    existing_parent = candidate.parent
    while not existing_parent.exists() and existing_parent != policy.root:
        existing_parent = existing_parent.parent
    policy._ensure_inside(existing_parent.resolve(strict=True))  # noqa: SLF001
    resolved = candidate.resolve(strict=False)
    policy._ensure_inside(resolved)  # noqa: SLF001
    return resolved


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


def walk(workspace_root: str, path: str = ".", *, max_depth: int = 5, limit: int = 200) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    root = policy.resolve_directory(path).absolute_path
    entries = []
    for item in _iter_files(policy, root, max_depth=max_depth, limit=min(limit, MAX_WALK_ITEMS)):
        stat = item.stat()
        entries.append({"path": item.relative_to(policy.root).as_posix(), "size": stat.st_size, "modified_at": stat.st_mtime})
    return ok("Workspace walk completed.", {"path": path, "entries": entries, "limited": len(entries) >= min(limit, MAX_WALK_ITEMS)})


def directory_summary(workspace_root: str, path: str = ".", *, max_depth: int = 5, limit: int = 1000) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    root = policy.resolve_directory(path).absolute_path
    files = _iter_files(policy, root, max_depth=max_depth, limit=min(limit, MAX_WALK_ITEMS))
    total_size = sum(item.stat().st_size for item in files)
    extensions = Counter((item.suffix.lower() or "(no extension)") for item in files)
    return ok(
        "Directory summary collected.",
        {"path": path, "file_count": len(files), "total_size": total_size, "extensions": dict(sorted(extensions.items()))},
    )


def find_large_files(workspace_root: str, path: str = ".", *, min_size_bytes: int, max_depth: int = 5, limit: int = 100) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    root = policy.resolve_directory(path).absolute_path
    matches = []
    for item in _iter_files(policy, root, max_depth=max_depth, limit=MAX_WALK_ITEMS):
        size = item.stat().st_size
        if size >= min_size_bytes:
            matches.append({"path": item.relative_to(policy.root).as_posix(), "size": size})
        if len(matches) >= limit:
            break
    return ok("Large files found.", {"path": path, "min_size_bytes": min_size_bytes, "files": matches, "total_size": sum(item["size"] for item in matches)})


def list_by_extension(workspace_root: str, path: str = ".", *, extension: str = "", max_depth: int = 5, limit: int = 200) -> ToolResult:
    wanted = extension.lower().strip()
    if wanted and not wanted.startswith("."):
        wanted = "." + wanted
    policy = WorkspacePathPolicy(workspace_root)
    root = policy.resolve_directory(path).absolute_path
    files = []
    for item in _iter_files(policy, root, max_depth=max_depth, limit=MAX_WALK_ITEMS):
        if not wanted or item.suffix.lower() == wanted:
            files.append({"path": item.relative_to(policy.root).as_posix(), "extension": item.suffix.lower(), "size": item.stat().st_size})
        if len(files) >= limit:
            break
    return ok("Files grouped by extension.", {"path": path, "extension": wanted, "files": files})


def compare_files(workspace_root: str, path: str, other_path: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    left = policy.resolve_existing(path).absolute_path
    right = policy.resolve_existing(other_path).absolute_path
    if not left.is_file() or not right.is_file():
        raise ValueError("NOT_FILE")
    left_hash = sha256_file(left)
    right_hash = sha256_file(right)
    return ok(
        "Files compared.",
        {"left": path, "right": other_path, "same": left_hash == right_hash, "left_sha256": left_hash, "right_sha256": right_hash},
    )


def preview_batch(workspace_root: str, items: list[dict[str, Any]], *, operation: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    preview = []
    for item in items[:MAX_WALK_ITEMS]:
        source_text = str(item.get("source") or item.get("path") or "")
        destination_text = str(item.get("destination") or "")
        source = policy.resolve_existing(source_text).absolute_path
        destination = _resolve_new_descendant(policy, destination_text) if destination_text else None
        preview.append(
            {
                "source": source.relative_to(policy.root).as_posix(),
                "destination": destination.relative_to(policy.root).as_posix() if destination else None,
                "size": source.stat().st_size,
                "sourceHash": sha256_file(source) if source.is_file() else None,
            }
        )
    return ok("Batch preview generated.", {"operation": operation, "items": preview, "count": len(preview)})


def create_directory(workspace_root: str, path: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    target = _resolve_new_descendant(policy, path)
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
    target = _resolve_new_descendant(policy, path)
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


def append_text(workspace_root: str, path: str, content: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    target = policy.resolve_existing(path).absolute_path
    if not target.is_file():
        raise ValueError("NOT_FILE")
    before_hash = sha256_file(target)
    before_size = target.stat().st_size
    with target.open("a", encoding="utf-8") as handle:
        handle.write(content)
    verified = policy.resolve_existing(path).absolute_path
    after_hash = sha256_file(verified)
    if after_hash == before_hash and content:
        raise ValueError("POSTCONDITION_APPEND_FAILED")
    return ok(
        "Text appended.",
        {"path": path, "previous_sha256": before_hash, "previous_size": before_size, "sha256": after_hash, "appended_bytes": len(content.encode("utf-8")), "postcondition": verified_postcondition(exists=True, is_file=True, sha256=after_hash)},
        side_effect=True,
    )


def copy_file(workspace_root: str, path: str, destination: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    source = policy.resolve_existing(path).absolute_path
    dest = _resolve_new_descendant(policy, destination)
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
    dest = _resolve_new_descendant(policy, destination)
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


def batch_copy(workspace_root: str, items: list[dict[str, Any]]) -> ToolResult:
    return _batch_transfer(workspace_root, items, move=False)


def batch_move(workspace_root: str, items: list[dict[str, Any]]) -> ToolResult:
    return _batch_transfer(workspace_root, items, move=True)


def batch_rename(workspace_root: str, items: list[dict[str, Any]]) -> ToolResult:
    return _batch_transfer(workspace_root, items, move=True)


def _batch_transfer(workspace_root: str, items: list[dict[str, Any]], *, move: bool) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    successes = []
    failures = []
    for item in items[:MAX_WALK_ITEMS]:
        source_text = str(item.get("source") or item.get("path") or "")
        destination_text = str(item.get("destination") or "")
        try:
            source = policy.resolve_existing(source_text).absolute_path
            destination = _resolve_new_descendant(policy, destination_text)
            policy.ensure_distinct(source, destination)
            if destination.exists():
                raise ValueError("DESTINATION_EXISTS")
            destination.parent.mkdir(parents=True, exist_ok=True)
            before_hash = sha256_file(source) if source.is_file() else None
            if move:
                shutil.move(str(source), str(destination))
            else:
                shutil.copyfile(source, destination)
            verified = policy.resolve_existing(destination_text).absolute_path
            after_hash = sha256_file(verified) if verified.is_file() else None
            if before_hash and after_hash != before_hash:
                raise ValueError("POSTCONDITION_HASH_MISMATCH")
            if move and source.exists():
                raise ValueError("POSTCONDITION_SOURCE_STILL_EXISTS")
            successes.append({"source": source_text, "destination": destination_text, "size": verified.stat().st_size, "sha256": after_hash})
        except Exception as exc:
            failures.append({"source": source_text, "destination": destination_text, "error": str(exc)})
    return ok(
        "Batch transfer completed.",
        {"successes": successes, "failures": failures, "postcondition": verified_postcondition(success_count=len(successes), failure_count=len(failures))},
        side_effect=bool(successes),
    )


def create_zip(workspace_root: str, path: str, items: list[str]) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    archive = _resolve_new_descendant(policy, path)
    if archive.exists():
        raise ValueError("DESTINATION_EXISTS")
    if archive.suffix.lower() != ".zip":
        raise ValueError("ARCHIVE_EXTENSION_REQUIRED")
    selected: list[Path] = []
    total = 0
    for item in items[:MAX_ARCHIVE_ITEMS]:
        resolved = policy.resolve_existing(item).absolute_path
        if resolved.is_dir():
            selected.extend(_iter_files(policy, resolved, max_depth=10, limit=MAX_ARCHIVE_ITEMS - len(selected)))
        elif resolved.is_file():
            selected.append(resolved)
        total = sum(candidate.stat().st_size for candidate in selected)
        if total > MAX_ARCHIVE_BYTES or len(selected) > MAX_ARCHIVE_ITEMS:
            raise ValueError("ARCHIVE_LIMIT_EXCEEDED")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for selected_file in selected:
            handle.write(selected_file, selected_file.relative_to(policy.root).as_posix())
    verified = policy.resolve_existing(path).absolute_path
    return ok(
        "Zip archive created.",
        {"path": path, "file_count": len(selected), "total_size": total, "postcondition": verified_postcondition(exists=True, is_file=True, sha256=sha256_file(verified))},
        side_effect=True,
    )


def extract_zip(workspace_root: str, path: str, destination: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    archive = policy.resolve_existing(path).absolute_path
    if not archive.is_file() or archive.suffix.lower() != ".zip":
        raise ValueError("NOT_ZIP")
    extracted = []
    total = 0
    with zipfile.ZipFile(archive) as handle:
        infos = handle.infolist()
        if len(infos) > MAX_ARCHIVE_ITEMS:
            raise ValueError("ARCHIVE_ITEM_LIMIT_EXCEEDED")
        for info in infos:
            name = info.filename.replace("/", "\\")
            if info.is_dir():
                continue
            if name.startswith("\\") or ":" in name or any(part == ".." for part in Path(name).parts):
                raise ValueError("ZIP_SLIP_REJECTED")
            if info.file_size > MAX_ARCHIVE_BYTES:
                raise ValueError("ARCHIVE_ITEM_TOO_LARGE")
            total += info.file_size
            if total > MAX_ARCHIVE_BYTES:
                raise ValueError("ARCHIVE_TOTAL_LIMIT_EXCEEDED")
            target_rel = str(Path(destination) / name)
            target = _resolve_new_descendant(policy, target_rel)
            if target.exists():
                raise ValueError("DESTINATION_EXISTS")
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            verified = policy.resolve_existing(target_rel).absolute_path
            extracted.append({"path": verified.relative_to(policy.root).as_posix(), "size": verified.stat().st_size, "sha256": sha256_file(verified)})
    return ok(
        "Zip archive extracted.",
        {"path": path, "destination": destination, "files": extracted, "postcondition": verified_postcondition(file_count=len(extracted), total_size=total)},
        side_effect=bool(extracted),
    )


def move_to_recovery_bin(workspace_root: str, path: str, recovery_root: str, recovery_item_id: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    source = policy.resolve_existing(path).absolute_path
    if not source.is_file():
        raise ValueError("NOT_FILE")
    recovery_dir = Path(recovery_root).resolve(strict=False)
    recovery_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = int(os.environ.get("CLM_RECOVERY_BIN_MAX_BYTES", str(DEFAULT_RECOVERY_BIN_MAX_BYTES)))
    current_bytes = sum(item.stat().st_size for item in recovery_dir.rglob("*") if item.is_file())
    if current_bytes + source.stat().st_size > max_bytes:
        raise ValueError("RECOVERY_BIN_QUOTA_EXCEEDED")
    destination = recovery_dir / recovery_item_id
    if destination.exists():
        raise ValueError("RECOVERY_ITEM_EXISTS")
    before_hash = sha256_file(source)
    shutil.move(str(source), str(destination))
    if source.exists() or not destination.is_file() or sha256_file(destination) != before_hash:
        raise ValueError("POSTCONDITION_RECOVERY_MOVE_FAILED")
    return ok(
        "File moved to recovery bin.",
        {"path": path, "recovery_item_id": recovery_item_id, "sha256": before_hash, "size": destination.stat().st_size, "postcondition": verified_postcondition(source_missing=True, recovery_exists=True, sha256=before_hash)},
        side_effect=True,
    )


def restore_from_recovery_bin(workspace_root: str, destination_path: str, recovery_root: str, recovery_item_id: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    destination = _resolve_new_descendant(policy, destination_path)
    if destination.exists():
        raise ValueError("DESTINATION_EXISTS")
    source = Path(recovery_root).resolve(strict=True) / recovery_item_id
    if not source.is_file():
        raise ValueError("RECOVERY_ITEM_NOT_FOUND")
    digest = sha256_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    verified = policy.resolve_existing(destination_path).absolute_path
    if not verified.is_file() or sha256_file(verified) != digest:
        raise ValueError("POSTCONDITION_RECOVERY_RESTORE_FAILED")
    return ok(
        "File restored from recovery bin.",
        {"path": destination_path, "recovery_item_id": recovery_item_id, "sha256": digest, "postcondition": verified_postcondition(exists=True, recovery_missing=True, sha256=digest)},
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

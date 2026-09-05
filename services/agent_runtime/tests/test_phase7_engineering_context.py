from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import get_engineering_project_context
from app.db.session import Base
from app.engineering.project_context import (
    MAX_SCAN_FILES,
    ProjectContextError,
    ProjectContextService,
)
from app.models import WorkspaceGrant


def grant(root: Path, *, enabled: bool = True) -> WorkspaceGrant:
    return WorkspaceGrant(
        id="workspace-1",
        display_name="測試工程專案",
        root_path=str(root),
        enabled=enabled,
        permission_profile="standard",
    )


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session


def test_detects_stack_commands_entrypoints_and_git_without_source_content(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest", "typecheck": "tsc", "build": "vite build"}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    (tmp_path / "services" / "runtime").mkdir(parents=True)
    (tmp_path / "services" / "runtime" / "pyproject.toml").write_text(
        "[project]\nname='demo'\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("const secret = 'not returned';\n", encoding="utf-8")
    (tmp_path / ".git" / "refs" / "heads").mkdir(parents=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    commit = "a" * 40
    (tmp_path / ".git" / "refs" / "heads" / "main").write_text(commit, encoding="utf-8")

    result = ProjectContextService().inspect(grant(tmp_path))

    assert result.workspaceId == "workspace-1"
    assert result.projectName == "測試工程專案"
    assert result.stacks == ["node", "python", "typescript"]
    assert "services/runtime/pyproject.toml" in result.markers
    assert result.entrypoints == ["src/main.ts"]
    assert result.testCommands == ["npm test", "npm run typecheck", "python -m pytest"]
    assert result.buildCommands == ["npm run build"]
    assert result.git.detected is True
    assert result.git.branch == "main"
    assert result.git.commit == commit
    assert result.git.dirty is None
    assert "not returned" not in result.model_dump_json()


def test_scan_skips_dependency_directories(tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    for index in range(20):
        (tmp_path / "node_modules" / f"large-{index}.js").write_text("x", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")

    result = ProjectContextService().inspect(grant(tmp_path))

    assert result.scan.fileCount == 1
    assert result.scan.fileCount < MAX_SCAN_FILES


def test_disabled_workspace_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProjectContextError, match="WORKSPACE_DISABLED"):
        ProjectContextService().inspect(grant(tmp_path, enabled=False))


def test_missing_workspace_root_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ProjectContextError, match="WORKSPACE_UNAVAILABLE"):
        ProjectContextService().inspect(grant(missing))


def test_engineering_context_api_uses_persisted_workspace(tmp_path: Path, db: Session) -> None:
    (tmp_path / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")
    workspace = grant(tmp_path)
    db.add(workspace)
    db.commit()

    result = get_engineering_project_context(workspace.id, db)

    assert result.workspaceId == workspace.id
    assert result.stacks == ["go"]


def test_engineering_context_api_rejects_unknown_workspace(db: Session) -> None:
    with pytest.raises(HTTPException) as raised:
        get_engineering_project_context("missing", db)
    assert raised.value.status_code == 404
    assert raised.value.detail == "WORKSPACE_NOT_FOUND"

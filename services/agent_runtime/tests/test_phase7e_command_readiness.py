from __future__ import annotations

import json
from pathlib import Path

from app.engineering.command_catalog import ProjectCommandCatalog


def resolver(*available: str):
    def resolve(name: str) -> str | None:
        return f"C:\\Tools\\{name}.cmd" if name in available else None

    return resolve


def test_python_marker_is_not_runnable_without_pytest(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    catalog = ProjectCommandCatalog(
        executable_resolver=resolver("python"),
        python_probe=lambda executable: False,
    )

    availability, candidate = catalog.inspect(tmp_path, "test")

    assert availability.status == "MISSING_DEPENDENCY"
    assert availability.reasonCode == "ENGINEERING_PYTEST_UNAVAILABLE"
    assert availability.displayCommand == "python -m pytest"
    assert candidate is None


def test_pnpm_manifest_is_not_runnable_when_pnpm_is_missing(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@10.0.0",
                "scripts": {"test": "vitest", "build": "vite build"},
            }
        ),
        encoding="utf-8",
    )
    catalog = ProjectCommandCatalog(executable_resolver=resolver("npm"))

    availability, candidate = catalog.inspect(tmp_path, "test")

    assert availability.status == "MISSING_TOOL"
    assert availability.reasonCode == "ENGINEERING_PACKAGE_MANAGER_UNAVAILABLE"
    assert availability.displayCommand == "pnpm run test"
    assert candidate is None


def test_nested_package_manifest_becomes_a_project_unit(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        '{"scripts":{"test":"vitest","build":"vite build"}}',
        encoding="utf-8",
    )
    catalog = ProjectCommandCatalog(executable_resolver=resolver("npm"))

    availability, candidate = catalog.inspect(tmp_path, "build")

    assert availability.status == "READY"
    assert availability.projectRelativePath == "frontend"
    assert availability.displayCommand == "npm run build"
    assert candidate is not None
    assert candidate.source_relative_path == "frontend/package.json"


def test_node_script_is_not_ready_before_dependencies_are_installed(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest"},"devDependencies":{"vitest":"1.0.0"}}',
        encoding="utf-8",
    )
    catalog = ProjectCommandCatalog(executable_resolver=resolver("npm"))

    availability, candidate = catalog.inspect(tmp_path, "test")

    assert availability.status == "MISSING_DEPENDENCY"
    assert availability.reasonCode == "ENGINEERING_NODE_DEPENDENCIES_UNAVAILABLE"
    assert candidate is None


def test_multiple_ready_nested_units_fail_closed_as_ambiguous(tmp_path: Path) -> None:
    for name in ("frontend", "admin"):
        unit = tmp_path / name
        unit.mkdir()
        (unit / "package.json").write_text(
            '{"scripts":{"test":"vitest"}}', encoding="utf-8"
        )
    catalog = ProjectCommandCatalog(executable_resolver=resolver("npm"))

    availability, candidate = catalog.inspect(tmp_path, "test")

    assert availability.status == "AMBIGUOUS"
    assert availability.candidateCount == 2
    assert candidate is None


def test_root_script_is_authoritative_over_nested_units(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest --root"}}', encoding="utf-8"
    )
    nested = tmp_path / "frontend"
    nested.mkdir()
    (nested / "package.json").write_text(
        '{"scripts":{"test":"vitest"}}', encoding="utf-8"
    )
    catalog = ProjectCommandCatalog(executable_resolver=resolver("npm"))

    availability, candidate = catalog.inspect(tmp_path, "test")

    assert availability.status == "READY"
    assert availability.projectRelativePath == "."
    assert candidate is not None
    assert candidate.source_relative_path == "package.json"

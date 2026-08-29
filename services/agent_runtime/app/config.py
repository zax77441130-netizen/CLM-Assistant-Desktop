from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeSettings:
    desktop_token: str
    data_dir: Path
    resource_dir: Path
    state_file: Path

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'clm_assistant.sqlite3'}"


def get_settings() -> RuntimeSettings:
    data_dir = Path(os.environ.get("CLM_DATA_DIR", Path.cwd() / ".runtime-data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return RuntimeSettings(
        desktop_token=os.environ.get("CLM_DESKTOP_TOKEN", "development-token"),
        data_dir=data_dir,
        resource_dir=Path(os.environ.get("CLM_RESOURCE_DIR", Path.cwd())).resolve(),
        state_file=Path(os.environ.get("CLM_RUNTIME_STATE_FILE", data_dir / "runtime-state.json")),
    )

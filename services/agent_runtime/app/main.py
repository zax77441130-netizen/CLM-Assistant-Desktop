from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI

from app.api.errors import DATABASE_EXCEPTIONS, database_exception_handler, unhandled_exception_handler
from app.api.routes import router
from app.config import get_settings
from app.core.diagnostics import configure_runtime_logging
from app.db.migration_manager import assert_database_ready, migrate_to_head
from app.db.session import engine
from app.models import entities as _entities  # noqa: F401

app = FastAPI(title="CLM Assistant Agent Runtime", version="0.1.0")
app.include_router(router, prefix="/api")
for exception_class in DATABASE_EXCEPTIONS:
    app.add_exception_handler(exception_class, database_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "bind": "127.0.0.1"}


def initialize_database() -> None:
    migrate_to_head()
    assert_database_ready(engine)


def reserve_random_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_state_file(port: int) -> None:
    settings = get_settings()
    payload = {
        "host": "127.0.0.1",
        "port": port,
        "pid": os.getpid(),
        "state": "running",
        "tokenExposedToRenderer": False,
        "databaseReady": True,
        "startedAt": datetime.now(UTC).isoformat(),
    }
    settings.state_file.parent.mkdir(parents=True, exist_ok=True)
    settings.state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run() -> None:
    configure_runtime_logging()
    initialize_database()
    port = reserve_random_port()
    os.environ["CLM_RUNTIME_PORT"] = str(port)
    write_state_file(port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    run()

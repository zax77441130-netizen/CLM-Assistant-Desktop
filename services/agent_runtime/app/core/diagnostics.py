from __future__ import annotations

import logging
import re
from pathlib import Path

from app.config import get_settings

SENSITIVE_PATTERN = re.compile(
    r"(token|secret|password|api[_-]?key|authorization|cookie|sqlite:///[^\\s]+|[A-Z]:\\\\[^\\r\\n\\t ]+)",
    re.IGNORECASE,
)


def redact_diagnostic(value: object) -> str:
    return SENSITIVE_PATTERN.sub("[redacted]", str(value))


def configure_runtime_logging() -> None:
    settings = get_settings()
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=Path(log_dir / "runtime.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )

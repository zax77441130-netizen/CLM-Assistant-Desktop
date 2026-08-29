from __future__ import annotations

from typing import Any

SECRET_MARKERS = ("token", "secret", "password", "api_key", "apikey", "authorization", "cookie")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(marker in key.lower() for marker in SECRET_MARKERS):
                redacted[key] = "***REDACTED***"
            elif key.lower() in {"root_path", "absolute_path"}:
                redacted[key] = "***LOCAL_PATH***"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value

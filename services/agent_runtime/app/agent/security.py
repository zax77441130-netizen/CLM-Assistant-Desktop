from __future__ import annotations

import re

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+"),
]


def redact_sensitive_text(value: str) -> str:
    clean = value
    for pattern in SECRET_PATTERNS:
        clean = pattern.sub("[已遮罩]", clean)
    return clean


def contains_prompt_injection(value: str) -> bool:
    lower = value.lower()
    markers = ["忽略之前", "忽略以上", "ignore previous", "ignore above", "system prompt", "developer message"]
    return any(marker in lower for marker in markers)

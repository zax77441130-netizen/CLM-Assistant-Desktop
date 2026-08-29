from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_desktop_token(x_desktop_token: str | None = Header(default=None)) -> None:
    expected = get_settings().desktop_token
    if not expected or x_desktop_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid desktop session token")

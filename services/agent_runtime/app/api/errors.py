from __future__ import annotations

import logging
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.diagnostics import redact_diagnostic
from app.db.migration_manager import MigrationError

LOGGER = logging.getLogger(__name__)


def correlation_id(request: Request) -> str:
    candidate = request.headers.get("X-Request-ID")
    return candidate if candidate else uuid.uuid4().hex


def safe_error_response(code: str, message: str, correlation: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": False,
                "correlationId": correlation,
            }
        },
    )


async def database_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    corr = correlation_id(request)
    LOGGER.exception("correlation_id=%s database_error=%s", corr, redact_diagnostic(exc))
    message = "本機資料庫需要更新，請重新啟動程式；若問題持續，請查看系統診斷紀錄。"
    return safe_error_response("DATABASE_MIGRATION_REQUIRED", message, corr)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    corr = correlation_id(request)
    LOGGER.exception("correlation_id=%s unhandled_error=%s", corr, redact_diagnostic(exc))
    return safe_error_response("RUNTIME_INTERNAL_ERROR", "任務暫時無法完成，請重新整理或重新啟動 Runtime。", corr)


DATABASE_EXCEPTIONS = (SQLAlchemyError, MigrationError)

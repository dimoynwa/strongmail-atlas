from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def api_error(
    status_code: int,
    error: str,
    message: str,
    *,
    detail: Any = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": error, "message": message, "detail": detail},
    )

from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from service_orchestrator.shared.domain.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationFailed,
)
from service_orchestrator.shared.domain.validation import FieldError, to_pointer
from service_orchestrator.shared.presentation.schemas import error_body

logger = logging.getLogger(__name__)

_STATUS_BY_CATEGORY: list[tuple[type[DomainError], int]] = [
    (NotFoundError, 404),
    (ConflictError, 409),
    (ValidationFailed, 422),
]
_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def _response(
    status: int, code: str, message: str, errors: Sequence[FieldError] = ()
) -> JSONResponse:
    logger.info(
        "request rejected",
        extra={"code": code, "errors": [f"{e.path or '/'}:{e.code}" for e in errors[:20]]},
    )
    return JSONResponse(status_code=status, content=error_body(code, message, errors))


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    status = next((s for category, s in _STATUS_BY_CATEGORY if isinstance(exc, category)), 400)
    errors = exc.errors if isinstance(exc, ValidationFailed) else ()
    return _response(status, exc.code, exc.message, errors)


async def _request_invalid(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        FieldError(
            to_pointer(error["loc"][1:] if error["loc"][:1] == ("body",) else error["loc"]),
            error["type"],
            error["msg"],
        )
        for error in exc.errors()
    ]
    return _response(422, "request_invalid", "The request is malformed", errors)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    return _response(exc.status_code, code, str(exc.detail))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _request_invalid)
    app.add_exception_handler(StarletteHTTPException, _http_error)

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from service_orchestrator.shared.domain.ids import new_id
from service_orchestrator.shared.infrastructure.log_config import request_id_var
from service_orchestrator.shared.presentation.schemas import error_body

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER: Final = "x-request-id"
_REQUEST_ID: Final = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


async def send_json(send: Send, status: int, body: dict[str, Any]) -> None:
    payload = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await self._reject(send)

    async def _reject(self, send: Send) -> None:
        await send_json(
            send,
            413,
            error_body("payload_too_large", f"Request body exceeds {self.max_bytes} bytes"),
        )


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID.match(incoming) else new_id().hex
        token = request_id_var.set(request_id)
        request = {"method": scope["method"], "path": scope["path"]}
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                headers = [*message.get("headers", []), (b"x-request-id", request_id.encode())]
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception("unhandled error", extra=request)
            if response_started:
                raise
            await send_json(
                send_with_request_id,
                500,
                error_body(
                    "internal_error", "Unexpected error; quote the request id when reporting it"
                ),
            )
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            level = (
                logging.ERROR
                if status >= 500
                else logging.WARNING
                if status >= 400
                else logging.INFO
            )
            logger.log(
                level,
                "request completed",
                extra={**request, "status": status, "duration_ms": duration_ms},
            )
            request_id_var.reset(token)

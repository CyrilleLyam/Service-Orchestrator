from __future__ import annotations

from typing import Any

import httpx


def data(response: httpx.Response, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"] is False, body
    return body["data"]


def error(response: httpx.Response, status: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"] is True, body
    assert body["pagination"] is None
    return body["data"]


def error_paths(response: httpx.Response, status: int = 422) -> list[tuple[str, str]]:
    return [(e["path"], e["code"]) for e in error(response, status)["errors"]]

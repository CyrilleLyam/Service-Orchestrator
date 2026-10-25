from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from service_orchestrator.application_processing.application.queries.list_applications import (
    ApplicationSummary,
    ListApplications,
)
from service_orchestrator.application_processing.domain.value_objects import ApplicationStatus
from service_orchestrator.application_processing.presentation.router import router
from service_orchestrator.shared.application.pagination import Page, PageRequest


class RecordingReader:
    def __init__(self) -> None:
        self.calls = []
        self.summary = ApplicationSummary(
            id=uuid4(),
            service_code="delivery",
            service_version=2,
            status=ApplicationStatus.DRAFT,
            created_at=datetime(2026, 10, 26, tzinfo=UTC),
            updated_at=datetime(2026, 10, 26, tzinfo=UTC),
            submitted_at=None,
        )

    def list(self, page, *, service_code, status):
        self.calls.append((page, service_code, status))
        return Page((self.summary,), 5, page)


@pytest.fixture
def api():
    reader = RecordingReader()
    app = FastAPI()
    app.state.container = SimpleNamespace(list_applications=lambda: ListApplications(reader))
    app.include_router(router)
    with TestClient(app) as client:
        yield client, reader


def test_list_endpoint_forwards_filters_and_returns_summary_envelope(api) -> None:
    client, reader = api
    response = client.get("/v1/applications?serviceCode=delivery&status=draft&page=2&pageSize=2")
    assert response.status_code == 200
    assert reader.calls == [(PageRequest(2, 2), "delivery", ApplicationStatus.DRAFT)]
    body = response.json()
    assert body["error"] is False
    assert body["pagination"] == {"page": 2, "pageSize": 2, "total": 5, "totalPages": 3}
    assert body["data"] == [
        {
            "id": str(reader.summary.id),
            "serviceCode": "delivery",
            "serviceVersion": 2,
            "status": "draft",
            "createdAt": "2026-10-26T00:00:00Z",
            "updatedAt": "2026-10-26T00:00:00Z",
            "submittedAt": None,
        }
    ]


def test_list_defaults_and_submitted_filter(api) -> None:
    client, reader = api
    assert client.get("/v1/applications").status_code == 200
    assert reader.calls[-1] == (PageRequest(), None, None)
    assert client.get("/v1/applications?status=submitted").status_code == 200
    assert reader.calls[-1] == (PageRequest(), None, ApplicationStatus.SUBMITTED)


@pytest.mark.parametrize(
    "query",
    [
        "status=unknown",
        "page=0",
        "page=100001",
        "pageSize=0",
        "pageSize=101",
        "serviceCode=",
        f"serviceCode={'x' * 65}",
    ],
)
def test_invalid_list_parameters_do_not_query_storage(api, query: str) -> None:
    client, reader = api
    assert client.get(f"/v1/applications?{query}").status_code == 422
    assert reader.calls == []

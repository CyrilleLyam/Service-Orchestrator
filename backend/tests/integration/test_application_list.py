from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from service_orchestrator.application_processing.infrastructure.models import ApplicationModel
from tests.integration.api import data, error
from tests.integration.test_api_lifecycle import create_and_publish


def test_list_is_empty_and_validates_filters(client: TestClient) -> None:
    response = client.get("/v1/applications").json()
    assert response == {
        "error": False,
        "data": [],
        "pagination": {"page": 1, "pageSize": 20, "total": 0, "totalPages": 0},
    }
    for query in ("status=invalid", "page=0", "pageSize=101", "serviceCode="):
        error(client.get(f"/v1/applications?{query}"), 422)


def test_list_paginates_filters_and_keeps_pinned_versions(
    client: TestClient, container, delivery, event_registration
) -> None:
    create_and_publish(client, delivery)
    create_and_publish(client, event_registration)

    def create(code: str, payload: dict | None = None) -> dict:
        return data(
            client.post("/v1/applications", json={"serviceCode": code, "data": payload or {}}),
            201,
        )

    submitted = create("delivery", {"distanceKm": 12, "weightKg": 2, "express": False})
    data(client.post(f"/v1/applications/{submitted['id']}/submit"))
    first_draft = create("delivery")
    registration = create("event-registration")
    data(client.post("/v1/services/delivery/versions", json={}), 201)
    data(client.post("/v1/services/delivery/versions/2/publish"))
    latest_draft = create("delivery")

    first_page = client.get("/v1/applications?pageSize=2").json()
    assert [item["id"] for item in first_page["data"]] == [latest_draft["id"], registration["id"]]
    assert first_page["pagination"] == {"page": 1, "pageSize": 2, "total": 4, "totalPages": 2}
    second_page = data(client.get("/v1/applications?pageSize=2&page=2"))
    assert [item["id"] for item in second_page] == [first_draft["id"], submitted["id"]]
    assert "data" not in second_page[0]
    assert "fees" not in second_page[0]
    assert "events" not in second_page[0]

    drafts = client.get("/v1/applications?serviceCode=delivery&status=draft&pageSize=1").json()
    assert drafts["pagination"]["total"] == 2
    assert drafts["data"][0]["id"] == latest_draft["id"]
    assert drafts["data"][0]["serviceVersion"] == 2
    older = data(client.get("/v1/applications?serviceCode=delivery&status=draft&pageSize=1&page=2"))
    assert older[0]["id"] == first_draft["id"]
    assert older[0]["serviceVersion"] == 1
    results = data(client.get("/v1/applications?status=submitted"))
    assert [item["id"] for item in results] == [submitted["id"]]
    assert results[0]["submittedAt"] is not None
    assert data(client.get("/v1/applications?serviceCode=unknown")) == []
    beyond = client.get("/v1/applications?page=5&pageSize=2").json()
    assert beyond["data"] == []
    assert beyond["pagination"]["total"] == 4

    # Equal timestamps still have deterministic ordering across pages.
    with container.engine.begin() as connection:
        connection.execute(
            update(ApplicationModel)
            .where(ApplicationModel.status == "draft")
            .values(created_at=datetime(2030, 1, 1, tzinfo=UTC))
        )
    draft_ids = [first_draft["id"], registration["id"], latest_draft["id"]]
    expected = sorted(draft_ids, key=UUID, reverse=True)
    actual = [
        data(client.get(f"/v1/applications?status=draft&pageSize=1&page={page}"))[0]["id"]
        for page in range(1, 4)
    ]
    assert actual == expected


@pytest.mark.parametrize("status", ["draft", "submitted"])
def test_combined_filters_do_not_match_another_service(
    client: TestClient, delivery, event_registration, status: str
) -> None:
    create_and_publish(client, delivery)
    create_and_publish(client, event_registration)
    data(client.post("/v1/applications", json={"serviceCode": "delivery"}), 201)
    assert (
        data(client.get(f"/v1/applications?serviceCode=event-registration&status={status}")) == []
    )

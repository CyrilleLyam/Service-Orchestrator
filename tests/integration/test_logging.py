from __future__ import annotations

import json
import logging
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from service_orchestrator.main import create_app
from tests.integration.api import data, error
from tests.integration.test_api_lifecycle import create_and_publish


def records(caplog: pytest.LogCaptureFixture, message: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == message]


class TestRequestIds:
    def test_generated_request_ids_are_uuid_v7(self, client: TestClient) -> None:
        request_id = client.get("/health").headers["x-request-id"]
        assert UUID(hex=request_id).version == 7

    def test_caller_request_id_is_kept(self, client: TestClient) -> None:
        response = client.get("/health", headers={"X-Request-ID": "trace-42"})
        assert response.headers["x-request-id"] == "trace-42"

    def test_unsafe_request_id_is_replaced(self, client: TestClient) -> None:
        response = client.get("/health", headers={"X-Request-ID": "bad id\n"})
        assert response.headers["x-request-id"] != "bad id\n"

    def test_error_bodies_carry_the_request_id(self, client: TestClient) -> None:
        response = client.get("/v1/services/ghost", headers={"X-Request-ID": "trace-7"})
        assert error(response, 404)["requestId"] == "trace-7"


def test_every_request_is_logged(client: TestClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="service_orchestrator")
    client.get("/v1/services/ghost", headers={"X-Request-ID": "trace-1"})

    [record] = records(caplog, "request completed")
    assert (record.method, record.path, record.status) == ("GET", "/v1/services/ghost", 404)
    assert record.levelno == logging.WARNING
    assert record.request_id == "trace-1"
    assert record.duration_ms >= 0


def test_use_case_events_are_logged_with_the_request_id(
    client: TestClient, caplog, delivery
) -> None:
    caplog.set_level(logging.INFO, logger="service_orchestrator")
    create_and_publish(client, delivery)
    application = data(
        client.post(
            "/v1/applications",
            json={"serviceCode": "delivery", "data": {"distanceKm": 1, "weightKg": 1}},
            headers={"X-Request-ID": "create-1"},
        ),
        201,
    )
    data(client.post(f"/v1/applications/{application['id']}/submit"))

    [published] = records(caplog, "version published")
    assert (published.service, published.version) == ("delivery", 1)
    [created] = records(caplog, "application created")
    assert (created.application_id, created.request_id) == (application["id"], "create-1")
    [submitted] = records(caplog, "application submitted")
    assert (submitted.total, submitted.currency) == (5000, "KHR")


def test_rejections_log_paths_and_codes_but_not_submitted_values(
    client: TestClient, caplog, delivery
) -> None:
    create_and_publish(client, delivery)
    caplog.set_level(logging.DEBUG, logger="service_orchestrator")
    application = data(
        client.post(
            "/v1/applications",
            json={"serviceCode": "delivery", "data": {"distanceKm": 1, "notes": 42}},
        ),
        201,
    )
    error(client.post(f"/v1/applications/{application['id']}/submit"), 422)

    [rejected] = records(caplog, "request rejected")
    assert rejected.code == "submission_rejected"
    assert rejected.errors == ["/notes:type", "/weightKg:required"]
    assert records(caplog, "submission rejected")[0].application_id == application["id"]
    assert not any("42 is not of type" in json.dumps(vars(r), default=str) for r in caplog.records)


def test_unhandled_errors_return_an_enveloped_500_and_are_logged(container, caplog) -> None:
    app = create_app(container=container)

    def explode() -> None:
        raise RuntimeError("database on fire")

    app.add_api_route("/explode", explode)
    caplog.set_level(logging.INFO, logger="service_orchestrator")

    response = TestClient(app).get("/explode", headers={"X-Request-ID": "trace-500"})

    problem = error(response, 500)
    assert (problem["code"], problem["requestId"]) == ("internal_error", "trace-500")
    assert "database on fire" not in response.text
    [logged] = records(caplog, "unhandled error")
    assert logged.levelno == logging.ERROR
    assert logged.exc_info[1].args == ("database on fire",)
    assert records(caplog, "request completed")[0].status == 500

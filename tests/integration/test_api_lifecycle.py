from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from tests.integration.api import data, error, error_paths


def create_and_publish(client: TestClient, example: dict) -> dict:
    data(
        client.post("/v1/services", json={k: example[k] for k in ("code", "name", "description")}),
        201,
    )
    code = example["code"]
    draft = data(
        client.post(f"/v1/services/{code}/versions", json={"definition": example["definition"]}),
        201,
    )
    assert draft["status"] == "draft"
    return data(client.post(f"/v1/services/{code}/versions/{draft['version']}/publish"))


def test_every_response_uses_the_envelope(client: TestClient, delivery) -> None:
    create_and_publish(client, delivery)
    body = client.get("/v1/services/delivery").json()
    assert set(body) == {"error", "data", "pagination"}
    assert (body["error"], body["pagination"]) == (False, None)

    failure = client.get("/v1/services/ghost").json()
    assert set(failure) == {"error", "data", "pagination"}
    assert failure["error"] is True
    assert set(failure["data"]) == {"code", "message", "errors", "requestId"}


def test_two_unrelated_services_share_one_engine(
    client: TestClient, delivery, event_registration
) -> None:
    create_and_publish(client, delivery)
    create_and_publish(client, event_registration)

    services = data(client.get("/v1/services"))
    assert [(s["code"], s["currentVersion"]) for s in services] == [
        ("delivery", 1),
        ("event-registration", 1),
    ]

    detail = data(client.get("/v1/services/event-registration"))
    assert detail["published"]["definition"]["uiSchema"]["steps"][0]["id"] == "attendee"

    parcel = data(
        client.post(
            "/v1/applications", json={"serviceCode": "delivery", "data": {"distanceKm": 12}}
        ),
        201,
    )
    data(
        client.patch(
            f"/v1/applications/{parcel['id']}",
            content=json.dumps({"data": {"weightKg": 2.5, "express": True}}),
            headers={"Content-Type": "application/merge-patch+json"},
        )
    )
    submitted = data(client.post(f"/v1/applications/{parcel['id']}/submit"))
    assert submitted["status"] == "submitted"
    assert submitted["fees"] == {
        "currency": "KHR",
        "items": [
            {
                "code": "BASE",
                "amount": 5000,
                "label": {"en": "Delivery"},
                "quantity": None,
                "unitAmount": None,
            },
            {
                "code": "EXPRESS",
                "amount": 3000,
                "label": {"en": "Express surcharge"},
                "quantity": None,
                "unitAmount": None,
            },
        ],
        "total": 8000,
    }

    registration = data(
        client.post(
            "/v1/applications",
            json={
                "serviceCode": "event-registration",
                "data": {
                    "fullName": "Sokha",
                    "email": "sokha@example.com",
                    "attendeeType": "corporate",
                    "companyName": "Acme",
                    "sessions": ["keynote", "workshop-a"],
                },
            },
        ),
        201,
    )
    result = data(client.post(f"/v1/applications/{registration['id']}/submit"))
    assert [i["code"] for i in result["fees"]["items"]] == ["CORPORATE", "WORKSHOP_A"]
    assert result["fees"]["total"] == 100000


def test_new_version_without_redeploy_and_old_applications_keep_their_version(
    client: TestClient, delivery
) -> None:
    create_and_publish(client, delivery)
    old = data(
        client.post(
            "/v1/applications", json={"serviceCode": "delivery", "data": {"distanceKm": 5}}
        ),
        201,
    )
    assert old["serviceVersion"] == 1

    v2 = copy.deepcopy(delivery["definition"])
    v2["dataSchema"]["properties"]["fragile"] = {"type": "boolean"}
    v2["fees"][1]["amount"] = 4500
    v2["fees"].append(
        {"code": "FRAGILE", "amount": 2000, "currency": "KHR", "when": {"var": "fragile"}}
    )
    draft = data(client.post("/v1/services/delivery/versions", json={"definition": v2}), 201)
    assert draft["version"] == 2
    data(client.post("/v1/services/delivery/versions/2/publish"))

    new = data(
        client.post(
            "/v1/applications",
            json={
                "serviceCode": "delivery",
                "data": {"distanceKm": 5, "weightKg": 1, "express": True, "fragile": True},
            },
        ),
        201,
    )
    assert new["serviceVersion"] == 2
    assert data(client.post(f"/v1/applications/{new['id']}/submit"))["fees"]["total"] == 11500

    data(
        client.patch(
            f"/v1/applications/{old['id']}", json={"data": {"weightKg": 1, "fragile": True}}
        )
    )
    rejected = client.post(f"/v1/applications/{old['id']}/submit")
    assert error_paths(rejected) == [("/fragile", "additional_property")]
    data(
        client.patch(
            f"/v1/applications/{old['id']}", json={"data": {"fragile": None, "express": True}}
        )
    )
    accepted = data(client.post(f"/v1/applications/{old['id']}/submit"))
    assert (accepted["serviceVersion"], accepted["fees"]["total"]) == (1, 8000)

    v1 = data(client.get("/v1/services/delivery/versions/1"))
    assert v1["definition"] == delivery["definition"]
    assert data(client.get("/v1/services/delivery"))["published"]["version"] == 2


def test_invalid_submission_returns_field_errors_and_changes_nothing(
    client: TestClient, delivery
) -> None:
    create_and_publish(client, delivery)
    payload = {"distanceKm": 80, "weightKg": -1, "express": True, "colour": "red"}
    application = data(
        client.post("/v1/applications", json={"serviceCode": "delivery", "data": payload}), 201
    )
    before = data(client.get(f"/v1/applications/{application['id']}"))

    response = client.post(f"/v1/applications/{application['id']}/submit")

    assert error(response, 422)["code"] == "submission_rejected"
    assert error_paths(response) == [
        ("/colour", "additional_property"),
        ("/weightKg", "exclusiveMinimum"),
    ]
    assert data(client.get(f"/v1/applications/{application['id']}")) == before

    data(
        client.patch(
            f"/v1/applications/{application['id']}",
            json={"data": {"weightKg": 1, "colour": None}},
        )
    )
    response = client.post(f"/v1/applications/{application['id']}/submit")
    assert error(response, 422)["errors"] == [
        {
            "path": "/distanceKm",
            "code": "assertion_failed",
            "message": "Express delivery is only available up to 50 km.",
            "ruleId": "express-max-distance",
        }
    ]


def test_validate_and_quote(client: TestClient, delivery) -> None:
    create_and_publish(client, delivery)

    invalid = data(client.post("/v1/services/delivery/validate", json={"data": {"distanceKm": 1}}))
    assert invalid["valid"] is False
    assert invalid["errors"][0]["path"] == "/weightKg"

    valid = data(
        client.post(
            "/v1/services/delivery/validate", json={"data": {"distanceKm": 1, "weightKg": 1}}
        )
    )
    assert valid == {"serviceCode": "delivery", "version": 1, "valid": True, "errors": []}

    quote = data(
        client.post(
            "/v1/services/delivery/quote",
            json={"data": {"distanceKm": 1, "weightKg": 1, "express": True}},
        )
    )
    assert quote["fees"]["total"] == 8000
    error(client.post("/v1/services/delivery/quote", json={"data": {}}), 422)


def test_dynamic_fees_are_quoted_and_captured_at_submission(
    client: TestClient, equipment_rental
) -> None:
    create_and_publish(client, equipment_rental)
    payload = {"equipmentCategory": "camera", "durationDays": 10, "startDate": "2026-11-02"}

    quote = data(client.post("/v1/services/equipment-rental/quote", json={"data": payload}))
    assert [
        (i["code"], i["quantity"], i["unitAmount"], i["amount"]) for i in quote["fees"]["items"]
    ] == [("CAMERA", 10, 60000, 600000), ("SERVICE", 10, 1000, 10000)]

    application = data(
        client.post("/v1/applications", json={"serviceCode": "equipment-rental", "data": payload}),
        201,
    )
    data(client.patch(f"/v1/applications/{application['id']}", json={"data": {"durationDays": 12}}))
    submitted = data(client.post(f"/v1/applications/{application['id']}/submit"))
    assert submitted["fees"]["total"] == 12 * 60000 + 12 * 1000
    stored = data(client.get(f"/v1/applications/{application['id']}"))
    assert stored["fees"] == submitted["fees"]


def test_application_audit_trail(client: TestClient, delivery) -> None:
    create_and_publish(client, delivery)
    application = data(
        client.post(
            "/v1/applications", json={"serviceCode": "delivery", "data": {"distanceKm": 1}}
        ),
        201,
    )
    data(client.patch(f"/v1/applications/{application['id']}", json={"data": {"weightKg": 1}}))
    data(client.post(f"/v1/applications/{application['id']}/submit"))

    events = data(client.get(f"/v1/applications/{application['id']}"))["events"]
    assert [(e["type"], e["metadata"]) for e in events] == [
        ("application.created", {"serviceVersionId": events[0]["metadata"]["serviceVersionId"]}),
        ("application.data_updated", {"fields": ["weightKg"]}),
        ("application.submitted", {"feeTotal": 5000, "currency": "KHR"}),
    ]


def test_submitted_application_is_final(client: TestClient, delivery) -> None:
    create_and_publish(client, delivery)
    application = data(
        client.post(
            "/v1/applications",
            json={"serviceCode": "delivery", "data": {"distanceKm": 1, "weightKg": 1}},
        ),
        201,
    )
    data(client.post(f"/v1/applications/{application['id']}/submit"))

    patch = client.patch(f"/v1/applications/{application['id']}", json={"data": {"weightKg": 9}})
    again = client.post(f"/v1/applications/{application['id']}/submit")
    assert error(patch, 409)["code"] == "application_not_draft"
    assert error(again, 409)["code"] == "application_not_draft"


def test_idempotent_application_creation(client: TestClient, delivery) -> None:
    create_and_publish(client, delivery)
    request = {"serviceCode": "delivery", "data": {"distanceKm": 1}}
    headers = {"Idempotency-Key": "order-42"}

    first = data(client.post("/v1/applications", json=request, headers=headers), 201)
    second = data(client.post("/v1/applications", json=request, headers=headers), 200)

    assert first["id"] == second["id"]


class TestPagination:
    @pytest.fixture
    def five_services(self, client: TestClient) -> None:
        for code in ("alpha", "bravo", "charlie", "delta", "echo"):
            data(client.post("/v1/services", json={"code": code, "name": code.title()}), 201)

    def test_services_are_paged(self, client: TestClient, five_services) -> None:
        body = client.get("/v1/services", params={"page": 2, "pageSize": 2}).json()
        assert [s["code"] for s in body["data"]] == ["charlie", "delta"]
        assert body["pagination"] == {"page": 2, "pageSize": 2, "total": 5, "totalPages": 3}

    def test_page_past_the_end_is_empty(self, client: TestClient, five_services) -> None:
        body = client.get("/v1/services", params={"page": 9, "pageSize": 2}).json()
        assert (body["data"], body["pagination"]["total"]) == ([], 5)

    def test_default_page(self, client: TestClient, five_services) -> None:
        body = client.get("/v1/services").json()
        assert body["pagination"] == {"page": 1, "pageSize": 20, "total": 5, "totalPages": 1}

    def test_versions_are_paged(self, client: TestClient, delivery) -> None:
        create_and_publish(client, delivery)
        data(client.post("/v1/services/delivery/versions", json={}), 201)
        body = client.get("/v1/services/delivery/versions", params={"pageSize": 1}).json()
        assert [v["version"] for v in body["data"]] == [1]
        assert body["pagination"] == {"page": 1, "pageSize": 1, "total": 2, "totalPages": 2}

    @pytest.mark.parametrize("params", [{"page": 0}, {"pageSize": 0}, {"pageSize": 101}])
    def test_invalid_page_parameters(self, client: TestClient, params) -> None:
        assert error(client.get("/v1/services", params=params), 422)["code"] == "request_invalid"


class TestCatalogErrors:
    def test_invalid_definition_is_not_published(self, client: TestClient) -> None:
        data(client.post("/v1/services", json={"code": "broken", "name": "Broken"}), 201)
        definition = {
            "dataSchema": {"type": "object", "properties": {"a": {"$ref": "http://x/y"}}},
            "rules": [{"id": "r", "type": "require", "when": {"exec": "x"}, "fields": ["a"]}],
        }
        data(client.post("/v1/services/broken/versions", json={"definition": definition}), 201)

        response = client.post("/v1/services/broken/versions/1/publish")

        problem = error(response, 422)
        assert problem["code"] == "definition_invalid"
        assert problem["errors"][0]["path"] == "/dataSchema/properties/a/$ref"
        assert data(client.get("/v1/services/broken/versions/1"))["status"] == "draft"

    def test_published_version_cannot_be_edited(self, client: TestClient, delivery) -> None:
        create_and_publish(client, delivery)
        response = client.put(
            "/v1/services/delivery/versions/1", json={"definition": {"dataSchema": {}}}
        )
        assert error(response, 409)["code"] == "version_not_draft"

    def test_drafts_can_be_edited_before_publishing(self, client: TestClient, delivery) -> None:
        create_and_publish(client, delivery)
        data(client.post("/v1/services/delivery/versions", json={}), 201)
        changed = copy.deepcopy(delivery["definition"])
        changed["fees"][0]["amount"] = 6000
        edited = data(client.put("/v1/services/delivery/versions/2", json={"definition": changed}))
        assert edited["definition"]["fees"][0]["amount"] == 6000

    @pytest.mark.parametrize(
        ("method", "path", "body", "status", "code"),
        [
            ("get", "/v1/services/nope", None, 404, "service_not_found"),
            ("get", "/v1/services/delivery/versions/9", None, 404, "version_not_found"),
            ("post", "/v1/services", {"code": "delivery", "name": "x"}, 409, "service_code_taken"),
            (
                "post",
                "/v1/services",
                {"code": "Bad Code", "name": "x"},
                422,
                "invalid_service_code",
            ),
            ("post", "/v1/services", {"name": "x"}, 422, "request_invalid"),
            (
                "get",
                "/v1/applications/019a0000-0000-7000-8000-000000000000",
                None,
                404,
                "application_not_found",
            ),
            ("post", "/v1/applications", {"serviceCode": "ghost"}, 404, "service_not_found"),
            ("get", "/v1/nowhere", None, 404, "not_found"),
            ("delete", "/v1/services", None, 405, "method_not_allowed"),
        ],
    )
    def test_error_responses(self, client, delivery, method, path, body, status, code) -> None:
        create_and_publish(client, delivery)
        response = getattr(client, method)(path, **({"json": body} if body is not None else {}))
        assert error(response, status)["code"] == code

    def test_application_for_unpublished_service(self, client: TestClient) -> None:
        data(client.post("/v1/services", json={"code": "soon", "name": "Coming soon"}), 201)
        response = client.post("/v1/applications", json={"serviceCode": "soon"})
        assert error(response, 409)["code"] == "service_not_published"

    def test_request_errors_use_json_pointers(self, client: TestClient) -> None:
        response = client.post("/v1/services", json={"code": "x" * 100, "name": ""})
        assert {path for path, _ in error_paths(response)} == {"/code", "/name"}

    def test_oversized_request_body(self, client: TestClient) -> None:
        response = client.post(
            "/v1/services",
            content=b'{"pad": "' + b"x" * (2 * 1024 * 1024) + b'"}',
            headers={"Content-Type": "application/json"},
        )
        assert error(response, 413)["code"] == "payload_too_large"

from __future__ import annotations

import copy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from service_orchestrator.application_processing.application.commands.create_draft import (
    CreateApplicationDraft,
    CreateApplicationDraftCommand,
)
from service_orchestrator.application_processing.application.commands.submit_application import (
    SubmitApplication,
)
from service_orchestrator.application_processing.application.ports import PinnedServiceVersion
from service_orchestrator.application_processing.application.queries.evaluate_application import (
    QuoteApplication,
    ValidateApplication,
)
from service_orchestrator.application_processing.domain.exceptions import (
    ApplicationNotDraft,
    ApplicationNotFound,
)
from service_orchestrator.application_processing.presentation.router import router
from service_orchestrator.shared.application.limits import DocumentLimits
from service_orchestrator.shared.domain.exceptions import ValidationFailed
from service_orchestrator.shared.domain.ids import new_id
from service_orchestrator.shared.presentation.errors import register_error_handlers
from tests.payloads import PAYLOADS
from tests.unit.fakes import FakeApplicationUnitOfWork, FakeCatalogGateway

NOW = datetime(2026, 10, 26, tzinfo=UTC)


@pytest.fixture
def preview(delivery_definition, payload_checker):
    uow = FakeApplicationUnitOfWork()
    catalog = FakeCatalogGateway()
    catalog.publish(PinnedServiceVersion(new_id(), "delivery", 1, delivery_definition))
    created = CreateApplicationDraft(uow, catalog, DocumentLimits(), lambda: NOW).execute(
        CreateApplicationDraftCommand("delivery", PAYLOADS["delivery"])
    )
    validate = ValidateApplication(uow, catalog, payload_checker, DocumentLimits())
    return uow, catalog, created.view.application.id, validate


@pytest.mark.parametrize("example_name", list(PAYLOADS))
def test_previews_and_submission_agree_after_a_new_version_is_published(
    request, example_name, payload_checker
) -> None:
    example = request.getfixturevalue(example_name)
    uow = FakeApplicationUnitOfWork()
    catalog = FakeCatalogGateway()
    original = PinnedServiceVersion(new_id(), example["code"], 1, example["definition"])
    catalog.publish(original)
    created = CreateApplicationDraft(uow, catalog, DocumentLimits(), lambda: NOW).execute(
        CreateApplicationDraftCommand(example["code"], PAYLOADS[example_name])
    )
    application_id = created.view.application.id
    replacement = copy.deepcopy(example["definition"])
    replacement["dataSchema"]["required"].append("newRequiredField")
    catalog.publish(PinnedServiceVersion(new_id(), example["code"], 2, replacement))
    validate = ValidateApplication(uow, catalog, payload_checker, DocumentLimits())
    before_events = copy.deepcopy(uow.events)
    before_data = copy.deepcopy(uow.committed[application_id].data)
    result = validate.execute(application_id)
    quote = QuoteApplication(validate).execute(application_id)
    assert result.version == quote.version == 1
    assert result.evaluation.valid
    assert quote.fees.total.amount > 0
    assert uow.committed[application_id].data == before_data
    assert uow.events == before_events
    submitted = SubmitApplication(uow, catalog, payload_checker, lambda: NOW).execute(
        application_id
    )
    assert submitted.application.fee_snapshot == quote.fees.to_snapshot()


def test_unsaved_preview_uses_replacement_data_and_never_persists(preview) -> None:
    uow, _, application_id, validate = preview
    saved = QuoteApplication(validate).execute(application_id)
    edited = {"distanceKm": 10, "weightKg": 1, "express": False}
    proposed = QuoteApplication(validate).execute(application_id, edited)
    assert saved.fees.total.amount == 8000
    assert proposed.fees.total.amount == 5000
    assert uow.committed[application_id].data == PAYLOADS["delivery"]
    assert len(uow.events) == 1
    empty = validate.execute(application_id, {})
    assert not empty.evaluation.valid
    assert {error.path for error in empty.evaluation.errors} >= {"/distanceKm", "/weightKg"}


def test_assertion_errors_remain_field_addressable(preview) -> None:
    _, _, application_id, validate = preview
    invalid = {"distanceKm": 100, "weightKg": 1, "express": True}
    result = validate.execute(application_id, invalid)
    assert not result.evaluation.valid
    assert result.evaluation.errors[0].path == "/distanceKm"
    with pytest.raises(ValidationFailed):
        QuoteApplication(validate).execute(application_id, invalid)


def test_limits_apply_before_schema_evaluation(preview, payload_checker) -> None:
    uow, catalog, application_id, _ = preview
    validate = ValidateApplication(
        uow, catalog, payload_checker, DocumentLimits(max_payload_bytes=10)
    )
    assert not validate.execute(application_id).evaluation.valid
    assert not validate.execute(application_id, {"notes": "x" * 100}).evaluation.valid


def test_missing_and_submitted_applications_are_rejected(preview, payload_checker) -> None:
    uow, catalog, application_id, validate = preview
    with pytest.raises(ApplicationNotFound):
        validate.execute(new_id())
    SubmitApplication(uow, catalog, payload_checker, lambda: NOW).execute(application_id)
    with pytest.raises(ApplicationNotDraft):
        validate.execute(application_id)
    with pytest.raises(ApplicationNotDraft):
        QuoteApplication(validate).execute(application_id)


def test_http_preview_envelopes_and_request_validation(preview) -> None:
    _, _, application_id, validate = preview
    app = FastAPI()
    app.state.container = SimpleNamespace(
        validate_application=lambda: validate, quote_application=lambda: QuoteApplication(validate)
    )
    app.include_router(router)
    register_error_handlers(app)
    with TestClient(app) as client:
        base = f"/v1/applications/{application_id}"
        response = client.post(f"{base}/validate")
        assert response.status_code == 200
        assert response.json()["data"] == {
            "serviceCode": "delivery",
            "version": 1,
            "valid": True,
            "errors": [],
        }
        quote = client.post(f"{base}/quote", json={"data": PAYLOADS["delivery"]})
        assert quote.status_code == 200
        assert quote.json()["data"]["fees"]["total"] == 8000
        empty = client.post(f"{base}/validate", json={"data": {}})
        assert empty.status_code == 200
        assert empty.json()["data"]["valid"] is False
        rejected = client.post(f"{base}/quote", json={"data": {}})
        assert rejected.status_code == 422
        assert rejected.json()["error"] is True
        assert rejected.json()["data"]["errors"]
        for body in ({"data": []}, {"data": None}, {}):
            assert client.post(f"{base}/validate", json=body).status_code == 422
        assert client.post(f"/v1/applications/{new_id()}/quote").status_code == 404

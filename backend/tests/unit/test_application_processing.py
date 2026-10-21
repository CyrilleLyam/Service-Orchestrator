from __future__ import annotations

from datetime import UTC, datetime

import pytest

from service_orchestrator.application_processing.application.commands.create_draft import (
    CreateApplicationDraft,
    CreateApplicationDraftCommand,
)
from service_orchestrator.application_processing.application.commands.submit_application import (
    SubmitApplication,
)
from service_orchestrator.application_processing.application.commands.update_draft import (
    UpdateApplicationDraft,
    UpdateApplicationDraftCommand,
)
from service_orchestrator.application_processing.application.ports import PinnedServiceVersion
from service_orchestrator.application_processing.domain.entities import Application
from service_orchestrator.application_processing.domain.exceptions import (
    ApplicationDataInvalid,
    ApplicationNotDraft,
    IdempotencyKeyReused,
    SubmissionRejected,
)
from service_orchestrator.application_processing.domain.merge_patch import merge_patch
from service_orchestrator.application_processing.domain.value_objects import (
    ApplicationStatus,
    EventType,
)
from service_orchestrator.fee_policy.calculator import calculate_fees
from service_orchestrator.shared.application.limits import DocumentLimits
from service_orchestrator.shared.domain.ids import new_id
from tests.unit.fakes import FakeApplicationUnitOfWork, FakeCatalogGateway

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
FEES = calculate_fees(
    [{"code": "BASE", "amount": 5000, "currency": "KHR"}], lambda _: True, lambda _: None
)


@pytest.mark.parametrize(
    ("target", "patch", "expected"),
    [
        ({"a": "b"}, {"a": "c"}, {"a": "c"}),
        ({"a": "b"}, {"b": "c"}, {"a": "b", "b": "c"}),
        ({"a": "b"}, {"a": None}, {}),
        ({"a": "b", "b": "c"}, {"a": None}, {"b": "c"}),
        ({"a": ["b"]}, {"a": "c"}, {"a": "c"}),
        ({"a": {"b": "c"}}, {"a": {"b": "d", "c": None}}, {"a": {"b": "d"}}),
        ({"a": [{"b": "c"}]}, {"a": [1]}, {"a": [1]}),
        ({}, {"a": {"bb": {"ccc": None}}}, {"a": {"bb": {}}}),
    ],
)
def test_json_merge_patch(target, patch, expected) -> None:
    assert merge_patch(target, patch) == expected


class TestApplicationAggregate:
    def test_start_records_created_event(self) -> None:
        version_id = new_id()
        application = Application.start(service_version_id=version_id, data={}, now=NOW)
        assert application.status is ApplicationStatus.DRAFT
        [event] = application.pull_events()
        assert event.event_type is EventType.CREATED
        assert event.metadata == {"serviceVersionId": str(version_id)}
        assert application.pull_events() == []

    def test_patch_merges_and_records_changed_fields(self) -> None:
        application = Application.start(service_version_id=new_id(), data={"a": 1, "b": 2}, now=NOW)
        application.apply_patch({"b": None, "c": 3}, now=NOW)
        assert application.data == {"a": 1, "c": 3}
        assert application.pull_events()[-1].metadata == {"fields": ["b", "c"]}

    def test_submit_captures_fees_and_freezes_the_application(self) -> None:
        application = Application.start(service_version_id=new_id(), data={}, now=NOW)
        application.submit(FEES, now=NOW)
        assert application.status is ApplicationStatus.SUBMITTED
        assert application.submitted_at == NOW
        assert application.fee_snapshot["total"] == 5000
        with pytest.raises(ApplicationNotDraft):
            application.apply_patch({"a": 1}, now=NOW)
        with pytest.raises(ApplicationNotDraft):
            application.submit(FEES, now=NOW)

    def test_pinned_version_cannot_be_reassigned(self) -> None:
        application = Application.start(service_version_id=new_id(), data={}, now=NOW)
        with pytest.raises(AttributeError):
            application.service_version_id = new_id()


class TestApplicationUseCases:
    @pytest.fixture
    def uow(self) -> FakeApplicationUnitOfWork:
        return FakeApplicationUnitOfWork()

    @pytest.fixture
    def catalog(self, delivery_definition) -> FakeCatalogGateway:
        gateway = FakeCatalogGateway()
        gateway.publish(PinnedServiceVersion(new_id(), "delivery", 1, delivery_definition))
        return gateway

    def create(self, uow, catalog, data=None, key=None, code="delivery"):
        use_case = CreateApplicationDraft(uow, catalog, DocumentLimits(), lambda: NOW)
        return use_case.execute(CreateApplicationDraftCommand(code, data or {}, key))

    def test_draft_is_pinned_to_current_version(self, uow, catalog) -> None:
        view = self.create(uow, catalog, {"distanceKm": 5}).view
        assert (view.service_code, view.service_version) == ("delivery", 1)
        assert view.application.service_version_id == catalog.current["delivery"].service_version_id

    def test_idempotent_creation(self, uow, catalog) -> None:
        first = self.create(uow, catalog, key="k-1")
        again = self.create(uow, catalog, key="k-1")
        assert again.replayed and not first.replayed
        assert again.view.application.id == first.view.application.id
        assert len(uow.committed) == 1

    def test_idempotency_key_reused_for_other_service(self, uow, catalog) -> None:
        catalog.publish(PinnedServiceVersion(new_id(), "other", 1, {"dataSchema": {}}))
        self.create(uow, catalog, key="k-1")
        with pytest.raises(IdempotencyKeyReused):
            self.create(uow, catalog, key="k-1", code="other")

    def test_oversized_data_is_rejected(self, uow, catalog) -> None:
        use_case = CreateApplicationDraft(uow, catalog, DocumentLimits(max_payload_bytes=50))
        with pytest.raises(ApplicationDataInvalid) as raised:
            use_case.execute(CreateApplicationDraftCommand("delivery", {"notes": "x" * 100}))
        assert raised.value.errors[0].path == "/data"

    def test_submit_validates_prices_and_records_audit_trail(self, uow, catalog) -> None:
        application_id = self.create(uow, catalog, {"distanceKm": 5}).view.application.id
        UpdateApplicationDraft(uow, catalog, DocumentLimits(), lambda: NOW).execute(
            UpdateApplicationDraftCommand(application_id, {"weightKg": 1.5, "express": True})
        )
        view = SubmitApplication(uow, catalog, self.checker, lambda: NOW).execute(application_id)
        assert view.application.status is ApplicationStatus.SUBMITTED
        assert view.application.fee_snapshot["total"] == 8000
        assert [e.event_type for e in uow.events] == [
            EventType.CREATED,
            EventType.DATA_UPDATED,
            EventType.SUBMITTED,
        ]

    def test_invalid_submission_changes_nothing(self, uow, catalog) -> None:
        application_id = self.create(uow, catalog, {"distanceKm": 5}).view.application.id
        before = (uow.committed[application_id].data, len(uow.events))
        with pytest.raises(SubmissionRejected) as raised:
            SubmitApplication(uow, catalog, self.checker).execute(application_id)
        assert [(e.path, e.code) for e in raised.value.errors] == [("/weightKg", "required")]
        stored = uow.committed[application_id]
        assert stored.status is ApplicationStatus.DRAFT
        assert (stored.data, len(uow.events)) == before

    def test_submitted_application_cannot_be_updated(self, uow, catalog) -> None:
        data = {"distanceKm": 5, "weightKg": 1}
        application_id = self.create(uow, catalog, data).view.application.id
        SubmitApplication(uow, catalog, self.checker).execute(application_id)
        with pytest.raises(ApplicationNotDraft):
            UpdateApplicationDraft(uow, catalog, DocumentLimits()).execute(
                UpdateApplicationDraftCommand(application_id, {"weightKg": 2})
            )

    @pytest.fixture(autouse=True)
    def _checker(self, payload_checker) -> None:
        self.checker = payload_checker

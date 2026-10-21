from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from service_orchestrator.application_processing.application.commands.create_draft import (
    CreateApplicationDraftCommand,
)
from service_orchestrator.service_catalog.application.commands.create_version import (
    CreateDraftVersionCommand,
)
from service_orchestrator.service_catalog.domain.value_objects import VersionStatus
from service_orchestrator.shared.domain.ids import new_id


def test_service_aggregate_round_trip(container, publish, delivery_definition) -> None:
    published = publish("delivery", delivery_definition)
    container.create_draft_version().execute(
        CreateDraftVersionCommand(service_code="delivery", definition={"dataSchema": {}})
    )
    with container.catalog_uow() as uow:
        service = uow.services.get_by_code("delivery")
    assert [(v.version, v.status) for v in service.versions] == [
        (1, VersionStatus.PUBLISHED),
        (2, VersionStatus.DRAFT),
    ]
    assert service.current_version_id == published.id
    assert service.version(1).definition == delivery_definition
    with container.catalog_uow() as uow:
        assert uow.services.get_by_version_id(published.id).id == service.id


def test_version_numbers_are_unique_per_service(container, publish, delivery_definition) -> None:
    version = publish("delivery", delivery_definition)
    with (
        pytest.raises(IntegrityError, match="uq_service_versions_service_id_version"),
        container.engine.begin() as connection,
    ):
        connection.execute(
            text(
                "INSERT INTO service_versions (id, service_id, version, status, definition, "
                "created_at, updated_at, published_at) "
                "VALUES (:id, :service_id, 1, 'published', '{}', now(), now(), now())"
            ),
            {"id": new_id(), "service_id": version.service_id},
        )


def test_only_one_draft_per_service(container, publish, delivery_definition) -> None:
    version = publish("delivery", delivery_definition)
    insert = text(
        "INSERT INTO service_versions "
        "(id, service_id, version, status, definition, created_at, updated_at) "
        "VALUES (:id, :service_id, :version, 'draft', '{}', now(), now())"
    )
    with (
        pytest.raises(IntegrityError, match="uq_service_versions_one_draft"),
        container.engine.begin() as connection,
    ):
        connection.execute(insert, {"id": new_id(), "service_id": version.service_id, "version": 2})
        connection.execute(insert, {"id": new_id(), "service_id": version.service_id, "version": 3})


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE service_versions SET definition = '{}' WHERE id = :id",
        "UPDATE service_versions SET status = 'draft', published_at = NULL WHERE id = :id",
        "DELETE FROM service_versions WHERE id = :id",
    ],
)
def test_published_versions_are_immutable_in_the_database(
    container, publish, delivery_definition, statement
) -> None:
    version = publish("delivery", delivery_definition)
    with (
        pytest.raises(DBAPIError, match="published and immutable"),
        container.engine.begin() as connection,
    ):
        connection.execute(text(statement), {"id": version.id})


def test_current_version_must_belong_to_the_service(
    container, publish, delivery_definition, event_registration
) -> None:
    publish("delivery", delivery_definition)
    other = publish("event-registration", event_registration["definition"])
    with (
        pytest.raises(IntegrityError, match="fk_services_current_version"),
        container.engine.begin() as connection,
    ):
        connection.execute(
            text("UPDATE services SET current_version_id = :id WHERE code = 'delivery'"),
            {"id": other.id},
        )


@pytest.fixture
def submitted_application(container, publish, delivery_definition):
    publish("delivery", delivery_definition)
    created = container.create_application_draft().execute(
        CreateApplicationDraftCommand("delivery", {"distanceKm": 3, "weightKg": 1})
    )
    return container.submit_application().execute(created.view.application.id).application


@pytest.mark.parametrize(
    ("statement", "message"),
    [
        ("UPDATE applications SET data = '{}' WHERE id = :id", "submitted and cannot change"),
        ("DELETE FROM applications WHERE id = :id", "submitted and cannot change"),
        ("UPDATE application_events SET metadata = '{}' WHERE application_id = :id", "append-only"),
        ("DELETE FROM application_events WHERE application_id = :id", "append-only"),
    ],
)
def test_submitted_applications_and_audit_log_are_protected(
    container, submitted_application, statement, message
) -> None:
    with pytest.raises(DBAPIError, match=message), container.engine.begin() as connection:
        connection.execute(text(statement), {"id": submitted_application.id})


def test_pinned_version_cannot_change_even_for_drafts(
    container, publish, delivery_definition
) -> None:
    older = publish("delivery", delivery_definition)
    publish("delivery", delivery_definition)
    draft = container.create_application_draft().execute(
        CreateApplicationDraftCommand("delivery", {})
    )
    with (
        pytest.raises(DBAPIError, match="pinned service version"),
        container.engine.begin() as connection,
    ):
        connection.execute(
            text("UPDATE applications SET service_version_id = :v WHERE id = :id"),
            {"v": older.id, "id": draft.view.application.id},
        )


def test_application_round_trip_with_events(container, submitted_application) -> None:
    with container.application_uow() as uow:
        stored = uow.applications.get(submitted_application.id)
        events = uow.applications.events_for(submitted_application.id)
    assert stored.data == {"distanceKm": 3, "weightKg": 1}
    assert stored.fee_snapshot == submitted_application.fee_snapshot
    assert [e.event_type.value for e in events] == ["application.created", "application.submitted"]
    assert events[0].id < events[1].id

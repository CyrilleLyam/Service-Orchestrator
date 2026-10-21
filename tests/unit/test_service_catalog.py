from __future__ import annotations

from datetime import UTC, datetime

import pytest

from service_orchestrator.service_catalog.application.commands.create_service import (
    CreateService,
    CreateServiceCommand,
)
from service_orchestrator.service_catalog.application.commands.create_version import (
    CreateDraftVersion,
    CreateDraftVersionCommand,
)
from service_orchestrator.service_catalog.application.commands.publish_version import (
    PublishVersion,
    PublishVersionCommand,
)
from service_orchestrator.service_catalog.application.commands.update_version import (
    EditDraftVersion,
    EditDraftVersionCommand,
)
from service_orchestrator.service_catalog.domain.entities import Service
from service_orchestrator.service_catalog.domain.exceptions import (
    DefinitionInvalid,
    DraftAlreadyExists,
    InvalidServiceCode,
    ServiceCodeTaken,
    VersionNotDraft,
    VersionNotFound,
)
from service_orchestrator.service_catalog.domain.value_objects import VersionStatus
from service_orchestrator.shared.domain.validation import FieldError
from tests.unit.fakes import FakeCatalogUnitOfWork

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)


def ok(_definition) -> list[FieldError]:
    return []


def broken(_definition) -> list[FieldError]:
    return [FieldError("/dataSchema", "invalid_schema", "nope")]


def new_service() -> Service:
    return Service.register(code="delivery", name="Delivery", description="", now=NOW)


class TestServiceAggregate:
    def test_versions_are_numbered_sequentially(self) -> None:
        service = new_service()
        assert service.create_draft({"v": 1}, now=NOW).version == 1
        service.publish(1, check=ok, now=NOW)
        assert service.create_draft({"v": 2}, now=NOW).version == 2

    def test_only_one_draft_at_a_time(self) -> None:
        service = new_service()
        service.create_draft({}, now=NOW)
        with pytest.raises(DraftAlreadyExists):
            service.create_draft({}, now=NOW)

    def test_drafts_are_editable(self) -> None:
        service = new_service()
        service.create_draft({"v": 1}, now=NOW)
        assert service.edit_draft(1, {"v": 2}, now=NOW).definition == {"v": 2}

    def test_publish_freezes_version_and_moves_pointer(self) -> None:
        service = new_service()
        service.create_draft({"v": 1}, now=NOW)
        version = service.publish(1, check=ok, now=NOW)
        assert version.status is VersionStatus.PUBLISHED
        assert version.published_at == NOW
        assert service.current_version is version

    def test_published_versions_are_immutable(self) -> None:
        service = new_service()
        service.create_draft({"v": 1}, now=NOW)
        service.publish(1, check=ok, now=NOW)
        with pytest.raises(VersionNotDraft):
            service.edit_draft(1, {"v": 2}, now=NOW)
        with pytest.raises(VersionNotDraft):
            service.publish(1, check=ok, now=NOW)
        assert service.version(1).definition == {"v": 1}

    def test_definition_cannot_be_mutated_through_the_entity(self) -> None:
        service = new_service()
        service.create_draft({"fees": [1]}, now=NOW)
        service.publish(1, check=ok, now=NOW)
        service.version(1).definition["fees"].append(2)
        assert service.version(1).definition == {"fees": [1]}

    def test_publish_requires_a_passing_check(self) -> None:
        service = new_service()
        service.create_draft({}, now=NOW)
        with pytest.raises(DefinitionInvalid) as raised:
            service.publish(1, check=broken, now=NOW)
        assert raised.value.errors[0].path == "/dataSchema"
        assert service.version(1).is_draft
        assert service.current_version is None

    def test_new_version_keeps_old_published_version(self) -> None:
        service = new_service()
        service.create_draft({"v": 1}, now=NOW)
        service.publish(1, check=ok, now=NOW)
        service.create_draft({"v": 2}, now=NOW)
        service.publish(2, check=ok, now=NOW)
        assert service.current_version.version == 2
        assert service.version(1).definition == {"v": 1}
        assert service.version(1).status is VersionStatus.PUBLISHED

    def test_unknown_version(self) -> None:
        with pytest.raises(VersionNotFound):
            new_service().version(3)

    @pytest.mark.parametrize("code", ["D", "Delivery", "-x", "a--b", "a_b", "x" * 65])
    def test_service_code_format(self, code: str) -> None:
        with pytest.raises(InvalidServiceCode):
            Service.register(code=code, name="x", description="", now=NOW)


class TestCatalogUseCases:
    @pytest.fixture
    def uow(self) -> FakeCatalogUnitOfWork:
        return FakeCatalogUnitOfWork()

    def test_create_draft_publish_lifecycle(self, uow, definition_checker, delivery) -> None:
        CreateService(uow, lambda: NOW).execute(CreateServiceCommand("delivery", "Delivery"))
        CreateDraftVersion(uow, definition_checker, lambda: NOW).execute(
            CreateDraftVersionCommand("delivery", delivery["definition"])
        )
        published = PublishVersion(uow, definition_checker, lambda: NOW).execute(
            PublishVersionCommand("delivery", 1)
        )
        assert published.status is VersionStatus.PUBLISHED
        with uow:
            stored = uow.services.get_by_code("delivery")
        assert stored.current_version.definition == delivery["definition"]

    def test_duplicate_service_code(self, uow) -> None:
        CreateService(uow).execute(CreateServiceCommand("delivery", "Delivery"))
        with pytest.raises(ServiceCodeTaken):
            CreateService(uow).execute(CreateServiceCommand("delivery", "Again"))

    def test_invalid_definition_is_not_published(self, uow, definition_checker) -> None:
        CreateService(uow).execute(CreateServiceCommand("delivery", "Delivery"))
        CreateDraftVersion(uow, definition_checker).execute(
            CreateDraftVersionCommand("delivery", {"dataSchema": {"type": "array"}})
        )
        commits = uow.commits
        with pytest.raises(DefinitionInvalid):
            PublishVersion(uow, definition_checker).execute(PublishVersionCommand("delivery", 1))
        assert uow.commits == commits
        with uow:
            assert uow.services.get_by_code("delivery").version(1).is_draft

    def test_new_draft_copies_current_definition(self, uow, definition_checker, delivery) -> None:
        CreateService(uow).execute(CreateServiceCommand("delivery", "Delivery"))
        CreateDraftVersion(uow, definition_checker).execute(
            CreateDraftVersionCommand("delivery", delivery["definition"])
        )
        PublishVersion(uow, definition_checker).execute(PublishVersionCommand("delivery", 1))
        draft = CreateDraftVersion(uow, definition_checker).execute(
            CreateDraftVersionCommand("delivery")
        )
        assert (draft.version, draft.definition) == (2, delivery["definition"])

    def test_first_draft_needs_a_definition(self, uow, definition_checker) -> None:
        CreateService(uow).execute(CreateServiceCommand("delivery", "Delivery"))
        with pytest.raises(DefinitionInvalid):
            CreateDraftVersion(uow, definition_checker).execute(
                CreateDraftVersionCommand("delivery")
            )

    def test_editing_published_version_is_rejected(self, uow, definition_checker, delivery) -> None:
        CreateService(uow).execute(CreateServiceCommand("delivery", "Delivery"))
        CreateDraftVersion(uow, definition_checker).execute(
            CreateDraftVersionCommand("delivery", delivery["definition"])
        )
        PublishVersion(uow, definition_checker).execute(PublishVersionCommand("delivery", 1))
        with pytest.raises(VersionNotDraft):
            EditDraftVersion(uow, definition_checker).execute(
                EditDraftVersionCommand("delivery", 1, {"dataSchema": {}})
            )

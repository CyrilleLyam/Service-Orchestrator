from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from service_orchestrator.application_processing.application.commands.create_draft import (
    CreateApplicationDraft,
)
from service_orchestrator.application_processing.application.commands.submit_application import (
    SubmitApplication,
)
from service_orchestrator.application_processing.application.commands.update_draft import (
    UpdateApplicationDraft,
)
from service_orchestrator.application_processing.application.queries.evaluate_application import (
    QuoteApplication,
    ValidateApplication,
)
from service_orchestrator.application_processing.application.queries.get_application import (
    GetApplication,
)
from service_orchestrator.application_processing.application.queries.list_applications import (
    ListApplications,
)
from service_orchestrator.application_processing.infrastructure.application_list import (
    SqlAlchemyApplicationListReader,
)
from service_orchestrator.application_processing.infrastructure.catalog_gateway import (
    CatalogGateway,
)
from service_orchestrator.application_processing.infrastructure.repositories import (
    SqlAlchemyApplicationUnitOfWork,
)
from service_orchestrator.config import Settings
from service_orchestrator.service_catalog.application.commands.create_service import CreateService
from service_orchestrator.service_catalog.application.commands.create_version import (
    CreateDraftVersion,
)
from service_orchestrator.service_catalog.application.commands.publish_version import (
    PublishVersion,
)
from service_orchestrator.service_catalog.application.commands.update_version import (
    EditDraftVersion,
)
from service_orchestrator.service_catalog.application.definition_checker import DefinitionChecker
from service_orchestrator.service_catalog.application.queries.evaluate_payload import (
    QuoteFees,
    ValidatePayload,
)
from service_orchestrator.service_catalog.application.queries.get_service import (
    GetService,
    GetServiceVersion,
    ListServices,
)
from service_orchestrator.service_catalog.application.queries.published_versions import (
    PublishedVersions,
)
from service_orchestrator.service_catalog.infrastructure.repositories import (
    SqlAlchemyCatalogUnitOfWork,
)
from service_orchestrator.shared.application.clock import Clock, utc_now
from service_orchestrator.shared.application.limits import DocumentLimits
from service_orchestrator.shared.application.payload_checker import PayloadChecker
from service_orchestrator.shared.infrastructure.database import (
    create_db_engine,
    create_session_factory,
)
from service_orchestrator.shared.infrastructure.rule_evaluator import JsonLogicEvaluator
from service_orchestrator.shared.infrastructure.schema_validator import JsonSchemaValidator


@dataclass
class Container:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    limits: DocumentLimits
    definition_checker: DefinitionChecker
    payload_checker: PayloadChecker
    clock: Clock = field(default=utc_now)

    def catalog_uow(self) -> SqlAlchemyCatalogUnitOfWork:
        return SqlAlchemyCatalogUnitOfWork(self.session_factory)

    def application_uow(self) -> SqlAlchemyApplicationUnitOfWork:
        return SqlAlchemyApplicationUnitOfWork(self.session_factory)

    def published_versions(self) -> PublishedVersions:
        return PublishedVersions(self.catalog_uow())

    def catalog_gateway(self) -> CatalogGateway:
        return CatalogGateway(self.published_versions())

    def create_service(self) -> CreateService:
        return CreateService(self.catalog_uow(), self.clock)

    def list_services(self) -> ListServices:
        return ListServices(self.catalog_uow())

    def get_service(self) -> GetService:
        return GetService(self.catalog_uow())

    def get_service_version(self) -> GetServiceVersion:
        return GetServiceVersion(self.catalog_uow())

    def create_draft_version(self) -> CreateDraftVersion:
        return CreateDraftVersion(self.catalog_uow(), self.definition_checker, self.clock)

    def edit_draft_version(self) -> EditDraftVersion:
        return EditDraftVersion(self.catalog_uow(), self.definition_checker, self.clock)

    def publish_version(self) -> PublishVersion:
        return PublishVersion(self.catalog_uow(), self.definition_checker, self.clock)

    def validate_payload(self) -> ValidatePayload:
        return ValidatePayload(self.published_versions(), self.payload_checker, self.limits)

    def quote_fees(self) -> QuoteFees:
        return QuoteFees(self.validate_payload())

    def create_application_draft(self) -> CreateApplicationDraft:
        return CreateApplicationDraft(
            self.application_uow(), self.catalog_gateway(), self.limits, self.clock
        )

    def update_application_draft(self) -> UpdateApplicationDraft:
        return UpdateApplicationDraft(
            self.application_uow(), self.catalog_gateway(), self.limits, self.clock
        )

    def submit_application(self) -> SubmitApplication:
        return SubmitApplication(
            self.application_uow(), self.catalog_gateway(), self.payload_checker, self.clock
        )

    def list_applications(self) -> ListApplications:
        return ListApplications(SqlAlchemyApplicationListReader(self.session_factory))

    def validate_application(self) -> ValidateApplication:
        return ValidateApplication(
            self.application_uow(), self.catalog_gateway(), self.payload_checker, self.limits
        )

    def quote_application(self) -> QuoteApplication:
        return QuoteApplication(self.validate_application())

    def get_application(self) -> GetApplication:
        return GetApplication(self.application_uow(), self.catalog_gateway())


def build_container(settings: Settings) -> Container:
    engine = create_db_engine(settings.database_url)
    limits = DocumentLimits(
        max_definition_bytes=settings.max_definition_bytes,
        max_definition_depth=settings.max_definition_depth,
        max_payload_bytes=settings.max_payload_bytes,
        max_payload_depth=settings.max_payload_depth,
    )
    schema_validator = JsonSchemaValidator(
        max_depth=settings.max_schema_depth,
        max_nodes=settings.max_schema_nodes,
        max_pattern_length=settings.max_pattern_length,
    )
    rule_evaluator = JsonLogicEvaluator(
        max_depth=settings.max_rule_depth,
        max_nodes=settings.max_rule_nodes,
        max_steps=settings.max_rule_steps,
    )
    return Container(
        settings=settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        limits=limits,
        definition_checker=DefinitionChecker(schema_validator, rule_evaluator, limits),
        payload_checker=PayloadChecker(schema_validator, rule_evaluator),
    )


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]

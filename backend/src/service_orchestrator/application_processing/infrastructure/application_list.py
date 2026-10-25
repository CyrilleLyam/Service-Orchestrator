from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from service_orchestrator.application_processing.application.queries.list_applications import (
    ApplicationSummary,
)
from service_orchestrator.application_processing.domain.value_objects import ApplicationStatus
from service_orchestrator.application_processing.infrastructure.models import ApplicationModel
from service_orchestrator.service_catalog.infrastructure.models import (
    ServiceModel,
    ServiceVersionModel,
)
from service_orchestrator.shared.application.pagination import Page, PageRequest


class SqlAlchemyApplicationListReader:
    """Read projection: filter and paginate in SQL without loading payloads or definitions."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list(
        self,
        page: PageRequest,
        *,
        service_code: str | None,
        status: ApplicationStatus | None,
    ) -> Page[ApplicationSummary]:
        statement = (
            select(
                ApplicationModel.id,
                ServiceModel.code.label("service_code"),
                ServiceVersionModel.version.label("service_version"),
                ApplicationModel.status,
                ApplicationModel.created_at,
                ApplicationModel.updated_at,
                ApplicationModel.submitted_at,
            )
            .join(
                ServiceVersionModel, ApplicationModel.service_version_id == ServiceVersionModel.id
            )
            .join(ServiceModel, ServiceVersionModel.service_id == ServiceModel.id)
        )
        if service_code is not None:
            statement = statement.where(ServiceModel.code == service_code)
        if status is not None:
            statement = statement.where(ApplicationModel.status == status.value)
        with self._session_factory() as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
            rows = session.execute(
                statement.order_by(ApplicationModel.created_at.desc(), ApplicationModel.id.desc())
                .offset(page.offset)
                .limit(page.size)
            ).mappings()
            items = tuple(
                ApplicationSummary(**{**row, "status": ApplicationStatus(row["status"])})
                for row in rows
            )
        return Page(items, total, page)

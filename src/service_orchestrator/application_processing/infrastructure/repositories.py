from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from service_orchestrator.application_processing.domain.entities import (
    Application,
    ApplicationEvent,
)
from service_orchestrator.application_processing.domain.value_objects import (
    ApplicationStatus,
    EventType,
)
from service_orchestrator.application_processing.infrastructure.models import (
    ApplicationEventModel,
    ApplicationModel,
)
from service_orchestrator.shared.infrastructure.database import SqlAlchemyUnitOfWork


class SqlAlchemyApplicationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, application: Application) -> None:
        self._session.add(
            ApplicationModel(
                id=application.id,
                service_version_id=application.service_version_id,
                status=application.status.value,
                data=application.data,
                fee_snapshot=application.fee_snapshot,
                idempotency_key=application.idempotency_key,
                created_at=application.created_at,
                updated_at=application.updated_at,
                submitted_at=application.submitted_at,
            )
        )
        self._session.flush()
        self._append_events(application)

    def save(self, application: Application) -> None:
        row = self._session.get_one(ApplicationModel, application.id)
        row.status = application.status.value
        row.data = application.data
        row.fee_snapshot = application.fee_snapshot
        row.updated_at = application.updated_at
        row.submitted_at = application.submitted_at
        self._session.flush()
        self._append_events(application)

    def get(self, application_id: UUID, *, for_update: bool = False) -> Application | None:
        statement = select(ApplicationModel).where(ApplicationModel.id == application_id)
        if for_update:
            statement = statement.with_for_update()
        row = self._session.scalars(statement).one_or_none()
        return _to_domain(row) if row else None

    def get_by_idempotency_key(self, key: str) -> Application | None:
        statement = select(ApplicationModel).where(ApplicationModel.idempotency_key == key)
        row = self._session.scalars(statement).one_or_none()
        return _to_domain(row) if row else None

    def events_for(self, application_id: UUID) -> list[ApplicationEvent]:
        statement = (
            select(ApplicationEventModel)
            .where(ApplicationEventModel.application_id == application_id)
            .order_by(ApplicationEventModel.id)
        )
        return [
            ApplicationEvent(
                application_id=row.application_id,
                event_type=EventType(row.event_type),
                metadata=row.event_metadata,
                created_at=row.created_at,
                id=row.id,
            )
            for row in self._session.scalars(statement)
        ]

    def _append_events(self, application: Application) -> None:
        self._session.add_all(
            ApplicationEventModel(
                application_id=event.application_id,
                event_type=event.event_type.value,
                event_metadata=dict(event.metadata),
                created_at=event.created_at,
            )
            for event in application.pull_events()
        )
        self._session.flush()


def _to_domain(row: ApplicationModel) -> Application:
    return Application(
        id=row.id,
        service_version_id=row.service_version_id,
        status=ApplicationStatus(row.status),
        data=row.data,
        created_at=row.created_at,
        updated_at=row.updated_at,
        submitted_at=row.submitted_at,
        fee_snapshot=row.fee_snapshot,
        idempotency_key=row.idempotency_key,
    )


class SqlAlchemyApplicationUnitOfWork(SqlAlchemyUnitOfWork):
    applications: SqlAlchemyApplicationRepository

    def _bind_repositories(self, session: Session) -> None:
        self.applications = SqlAlchemyApplicationRepository(session)

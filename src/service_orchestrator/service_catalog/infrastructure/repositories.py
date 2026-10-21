from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from service_orchestrator.service_catalog.domain.entities import Service, ServiceVersion
from service_orchestrator.service_catalog.domain.value_objects import ServiceCode, VersionStatus
from service_orchestrator.service_catalog.infrastructure.models import (
    ServiceModel,
    ServiceVersionModel,
)
from service_orchestrator.shared.infrastructure.database import SqlAlchemyUnitOfWork


class SqlAlchemyServiceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, service: Service) -> None:
        self._session.add(
            ServiceModel(
                id=service.id,
                code=str(service.code),
                name=service.name,
                description=service.description,
                created_at=service.created_at,
            )
        )
        self._session.flush()
        self.save(service)

    def save(self, service: Service) -> None:
        row = self._session.get_one(ServiceModel, service.id)
        row.name = service.name
        row.description = service.description
        self._sync_versions(service)
        self._session.flush()
        row.current_version_id = service.current_version_id
        self._session.flush()

    def get_by_code(self, code: str, *, for_update: bool = False) -> Service | None:
        statement = select(ServiceModel).where(ServiceModel.code == code)
        if for_update:
            statement = statement.with_for_update()
        row = self._session.scalars(statement).one_or_none()
        return self._to_domain([row])[0] if row else None

    def get_by_version_id(self, version_id: UUID) -> Service | None:
        statement = (
            select(ServiceModel)
            .join(ServiceVersionModel, ServiceVersionModel.service_id == ServiceModel.id)
            .where(ServiceVersionModel.id == version_id)
        )
        row = self._session.scalars(statement).one_or_none()
        return self._to_domain([row])[0] if row else None

    def list_page(self, offset: int, limit: int) -> list[Service]:
        statement = select(ServiceModel).order_by(ServiceModel.code).offset(offset).limit(limit)
        return self._to_domain(self._session.scalars(statement).all())

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(ServiceModel)) or 0

    def _sync_versions(self, service: Service) -> None:
        rows = {
            row.id: row
            for row in self._session.scalars(
                select(ServiceVersionModel).where(ServiceVersionModel.service_id == service.id)
            )
        }
        for version in service.versions:
            row = rows.get(version.id)
            if row is None:
                self._session.add(_version_row(version))
            elif row.status == VersionStatus.DRAFT:
                row.definition = version.definition
                row.status = version.status.value
                row.updated_at = version.updated_at
                row.published_at = version.published_at

    def _to_domain(self, rows: Iterable[ServiceModel]) -> list[Service]:
        rows = list(rows)
        versions: dict[UUID, list[ServiceVersion]] = defaultdict(list)
        statement = (
            select(ServiceVersionModel)
            .where(ServiceVersionModel.service_id.in_([row.id for row in rows]))
            .order_by(ServiceVersionModel.version)
        )
        for version_row in self._session.scalars(statement):
            versions[version_row.service_id].append(
                ServiceVersion(
                    id=version_row.id,
                    service_id=version_row.service_id,
                    version=version_row.version,
                    status=VersionStatus(version_row.status),
                    definition=version_row.definition,
                    created_at=version_row.created_at,
                    updated_at=version_row.updated_at,
                    published_at=version_row.published_at,
                )
            )
        return [
            Service(
                id=row.id,
                code=ServiceCode(row.code),
                name=row.name,
                description=row.description,
                created_at=row.created_at,
                current_version_id=row.current_version_id,
                versions=versions[row.id],
            )
            for row in rows
        ]


def _version_row(version: ServiceVersion) -> ServiceVersionModel:
    return ServiceVersionModel(
        id=version.id,
        service_id=version.service_id,
        version=version.version,
        status=version.status.value,
        definition=version.definition,
        created_at=version.created_at,
        updated_at=version.updated_at,
        published_at=version.published_at,
    )


class SqlAlchemyCatalogUnitOfWork(SqlAlchemyUnitOfWork):
    services: SqlAlchemyServiceRepository

    def _bind_repositories(self, session: Session) -> None:
        self.services = SqlAlchemyServiceRepository(session)

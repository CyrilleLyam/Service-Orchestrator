from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from service_orchestrator.service_catalog.application.unit_of_work import CatalogUnitOfWork
from service_orchestrator.service_catalog.domain.entities import Service, ServiceVersion
from service_orchestrator.service_catalog.domain.exceptions import (
    PublishedVersionNotFound,
    ServiceNotFound,
    ServiceNotPublished,
)


@dataclass(frozen=True, slots=True)
class PublishedVersion:
    service_code: str
    version_id: UUID
    version: int
    definition: dict[str, Any]
    published_at: datetime


class PublishedVersions:
    def __init__(self, uow: CatalogUnitOfWork) -> None:
        self._uow = uow

    def current(self, service_code: str) -> PublishedVersion:
        with self._uow as uow:
            service = uow.services.get_by_code(service_code)
        if service is None:
            raise ServiceNotFound(service_code)
        if service.current_version is None:
            raise ServiceNotPublished(service_code)
        return _published(service, service.current_version)

    def by_id(self, version_id: UUID) -> PublishedVersion:
        with self._uow as uow:
            service = uow.services.get_by_version_id(version_id)
        version = (
            next((v for v in service.versions if v.id == version_id), None) if service else None
        )
        if service is None or version is None or version.is_draft:
            raise PublishedVersionNotFound(version_id)
        return _published(service, version)


def _published(service: Service, version: ServiceVersion) -> PublishedVersion:
    assert version.published_at is not None
    return PublishedVersion(
        service_code=str(service.code),
        version_id=version.id,
        version=version.version,
        definition=version.definition,
        published_at=version.published_at,
    )

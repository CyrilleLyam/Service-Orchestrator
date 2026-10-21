from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Self
from uuid import UUID

from service_orchestrator.application_processing.domain.repositories import ApplicationRepository


@dataclass(frozen=True, slots=True)
class PinnedServiceVersion:
    service_version_id: UUID
    service_code: str
    version: int
    definition: dict[str, Any]


class ServiceCatalogGateway(Protocol):
    def current_published(self, service_code: str) -> PinnedServiceVersion: ...

    def published_version(self, service_version_id: UUID) -> PinnedServiceVersion: ...


class ApplicationUnitOfWork(Protocol):
    applications: ApplicationRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, *exc_info: object) -> None: ...

    def commit(self) -> None: ...

from __future__ import annotations

from typing import Protocol, Self

from service_orchestrator.service_catalog.domain.repositories import ServiceRepository


class CatalogUnitOfWork(Protocol):
    services: ServiceRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, *exc_info: object) -> None: ...

    def commit(self) -> None: ...

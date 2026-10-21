from __future__ import annotations

from typing import Protocol
from uuid import UUID

from service_orchestrator.service_catalog.domain.entities import Service


class ServiceRepository(Protocol):
    def add(self, service: Service) -> None: ...

    def save(self, service: Service) -> None: ...

    def get_by_code(self, code: str, *, for_update: bool = False) -> Service | None: ...

    def get_by_version_id(self, version_id: UUID) -> Service | None: ...

    def list_page(self, offset: int, limit: int) -> list[Service]: ...

    def count(self) -> int: ...

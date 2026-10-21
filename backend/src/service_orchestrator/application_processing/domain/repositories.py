from __future__ import annotations

from typing import Protocol
from uuid import UUID

from service_orchestrator.application_processing.domain.entities import (
    Application,
    ApplicationEvent,
)


class ApplicationRepository(Protocol):
    def add(self, application: Application) -> None: ...

    def save(self, application: Application) -> None: ...

    def get(self, application_id: UUID, *, for_update: bool = False) -> Application | None: ...

    def get_by_idempotency_key(self, key: str) -> Application | None: ...

    def events_for(self, application_id: UUID) -> list[ApplicationEvent]: ...

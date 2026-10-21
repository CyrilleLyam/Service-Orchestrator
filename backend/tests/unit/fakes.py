from __future__ import annotations

import copy
from typing import Self
from uuid import UUID

from service_orchestrator.application_processing.application.ports import PinnedServiceVersion
from service_orchestrator.application_processing.domain.entities import (
    Application,
    ApplicationEvent,
)
from service_orchestrator.service_catalog.domain.entities import Service
from service_orchestrator.shared.domain.exceptions import ConflictError, NotFoundError


class InMemoryServiceRepository:
    def __init__(self, committed: dict[UUID, Service]) -> None:
        self._committed = committed
        self.staged: dict[UUID, Service] = {}

    def add(self, service: Service) -> None:
        self.staged[service.id] = copy.deepcopy(service)

    save = add

    def get_by_code(self, code: str, *, for_update: bool = False) -> Service | None:
        return next((s for s in self._all() if str(s.code) == code), None)

    def get_by_version_id(self, version_id: UUID) -> Service | None:
        return next((s for s in self._all() if any(v.id == version_id for v in s.versions)), None)

    def list_page(self, offset: int, limit: int) -> list[Service]:
        return sorted(self._all(), key=lambda s: str(s.code))[offset : offset + limit]

    def count(self) -> int:
        return len(self._all())

    def _all(self) -> list[Service]:
        merged = {**self._committed, **self.staged}
        return [copy.deepcopy(service) for service in merged.values()]


class FakeCatalogUnitOfWork:
    def __init__(self) -> None:
        self.committed: dict[UUID, Service] = {}
        self.commits = 0

    def __enter__(self) -> Self:
        self.services = InMemoryServiceRepository(self.committed)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.services.staged.clear()

    def commit(self) -> None:
        self.committed.update(self.services.staged)
        self.services.staged.clear()
        self.commits += 1


class InMemoryApplicationRepository:
    def __init__(self, committed: dict[UUID, Application], events: list[ApplicationEvent]) -> None:
        self._committed = committed
        self._events = events
        self.staged: dict[UUID, Application] = {}
        self.staged_events: list[ApplicationEvent] = []

    def add(self, application: Application) -> None:
        self.staged_events.extend(application.pull_events())
        self.staged[application.id] = copy.deepcopy(application)

    save = add

    def get(self, application_id: UUID, *, for_update: bool = False) -> Application | None:
        found = self.staged.get(application_id) or self._committed.get(application_id)
        return copy.deepcopy(found)

    def get_by_idempotency_key(self, key: str) -> Application | None:
        merged = {**self._committed, **self.staged}
        found = next((a for a in merged.values() if a.idempotency_key == key), None)
        return copy.deepcopy(found)

    def events_for(self, application_id: UUID) -> list[ApplicationEvent]:
        return [e for e in self._events if e.application_id == application_id]


class FakeApplicationUnitOfWork:
    def __init__(self) -> None:
        self.committed: dict[UUID, Application] = {}
        self.events: list[ApplicationEvent] = []

    def __enter__(self) -> Self:
        self.applications = InMemoryApplicationRepository(self.committed, self.events)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.applications.staged.clear()
        self.applications.staged_events.clear()

    def commit(self) -> None:
        self.committed.update(self.applications.staged)
        self.events.extend(self.applications.staged_events)
        self.applications.staged.clear()
        self.applications.staged_events.clear()


class FakeCatalogGateway:
    def __init__(self) -> None:
        self.current: dict[str, PinnedServiceVersion] = {}
        self.by_id: dict[UUID, PinnedServiceVersion] = {}

    def publish(self, pinned: PinnedServiceVersion) -> None:
        self.current[pinned.service_code] = pinned
        self.by_id[pinned.service_version_id] = pinned

    def current_published(self, service_code: str) -> PinnedServiceVersion:
        if service_code not in self.current:
            raise ConflictError(f"{service_code} is not published")
        return self.current[service_code]

    def published_version(self, service_version_id: UUID) -> PinnedServiceVersion:
        if service_version_id not in self.by_id:
            raise NotFoundError(f"{service_version_id} not found")
        return self.by_id[service_version_id]

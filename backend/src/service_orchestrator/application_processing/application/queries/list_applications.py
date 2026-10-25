from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from service_orchestrator.application_processing.domain.value_objects import ApplicationStatus
from service_orchestrator.shared.application.pagination import Page, PageRequest


@dataclass(frozen=True, slots=True)
class ApplicationSummary:
    id: UUID
    service_code: str
    service_version: int
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None


class ApplicationListReader(Protocol):
    def list(
        self,
        page: PageRequest,
        *,
        service_code: str | None,
        status: ApplicationStatus | None,
    ) -> Page[ApplicationSummary]: ...


class ListApplications:
    def __init__(self, reader: ApplicationListReader) -> None:
        self._reader = reader

    def execute(
        self,
        page: PageRequest,
        *,
        service_code: str | None = None,
        status: ApplicationStatus | None = None,
    ) -> Page[ApplicationSummary]:
        return self._reader.list(page, service_code=service_code, status=status)

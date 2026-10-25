from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from service_orchestrator.application_processing.application.queries.list_applications import (
    ApplicationSummary,
)
from service_orchestrator.application_processing.application.views import ApplicationView
from service_orchestrator.application_processing.domain.entities import ApplicationEvent
from service_orchestrator.application_processing.domain.value_objects import ApplicationStatus
from service_orchestrator.shared.presentation.schemas import ApiModel, FeeBreakdownOut


class CreateApplicationRequest(ApiModel):
    service_code: str = Field(min_length=1, max_length=64)
    data: dict[str, Any] = Field(
        default_factory=dict, description="Initial, possibly partial data."
    )


class PatchApplicationRequest(ApiModel):
    data: dict[str, Any]


class EventOut(ApiModel):
    id: int | None
    type: str
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def of(cls, event: ApplicationEvent) -> EventOut:
        return cls(
            id=event.id,
            type=event.event_type.value,
            metadata=dict(event.metadata),
            created_at=event.created_at,
        )


class ApplicationOut(ApiModel):
    id: UUID
    service_code: str
    service_version: int
    status: str
    data: dict[str, Any]
    fees: FeeBreakdownOut | None = Field(description="Fee breakdown captured at submission.")
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None

    @classmethod
    def of(cls, view: ApplicationView) -> ApplicationOut:
        return cls(**_fields(view))


class ApplicationDetailOut(ApplicationOut):
    events: list[EventOut]

    @classmethod
    def of(cls, view: ApplicationView) -> ApplicationDetailOut:
        return cls(**_fields(view), events=[EventOut.of(e) for e in view.events])


def _fields(view: ApplicationView) -> dict[str, Any]:
    application = view.application
    snapshot = application.fee_snapshot
    return {
        "id": application.id,
        "service_code": view.service_code,
        "service_version": view.service_version,
        "status": application.status.value,
        "data": application.data,
        "fees": FeeBreakdownOut.from_snapshot(snapshot) if snapshot else None,
        "created_at": application.created_at,
        "updated_at": application.updated_at,
        "submitted_at": application.submitted_at,
    }


class ApplicationSummaryOut(ApiModel):
    id: UUID
    service_code: str
    service_version: int
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None

    @classmethod
    def of(cls, summary: ApplicationSummary) -> ApplicationSummaryOut:
        return cls(
            id=summary.id,
            service_code=summary.service_code,
            service_version=summary.service_version,
            status=summary.status,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            submitted_at=summary.submitted_at,
        )

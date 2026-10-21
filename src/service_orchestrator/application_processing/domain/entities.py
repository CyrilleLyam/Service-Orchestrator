from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from service_orchestrator.application_processing.domain.exceptions import ApplicationNotDraft
from service_orchestrator.application_processing.domain.merge_patch import merge_patch
from service_orchestrator.application_processing.domain.value_objects import (
    ApplicationStatus,
    EventType,
)
from service_orchestrator.fee_policy.calculator import FeeBreakdown
from service_orchestrator.shared.domain.ids import new_id


@dataclass(frozen=True, slots=True)
class ApplicationEvent:
    application_id: UUID
    event_type: EventType
    metadata: Mapping[str, Any]
    created_at: datetime
    id: int | None = field(default=None, compare=False)


class Application:
    def __init__(
        self,
        *,
        id: UUID,
        service_version_id: UUID,
        status: ApplicationStatus,
        data: Mapping[str, Any],
        created_at: datetime,
        updated_at: datetime,
        submitted_at: datetime | None = None,
        fee_snapshot: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        self.id = id
        self.created_at = created_at
        self.idempotency_key = idempotency_key
        self._service_version_id = service_version_id
        self._status = status
        self._data = copy.deepcopy(dict(data))
        self._updated_at = updated_at
        self._submitted_at = submitted_at
        self._fee_snapshot = copy.deepcopy(dict(fee_snapshot)) if fee_snapshot is not None else None
        self._pending_events: list[ApplicationEvent] = []

    @classmethod
    def start(
        cls,
        *,
        service_version_id: UUID,
        data: Mapping[str, Any],
        now: datetime,
        idempotency_key: str | None = None,
    ) -> Application:
        application = cls(
            id=new_id(),
            service_version_id=service_version_id,
            status=ApplicationStatus.DRAFT,
            data=data,
            created_at=now,
            updated_at=now,
            idempotency_key=idempotency_key,
        )
        application._record(EventType.CREATED, {"serviceVersionId": str(service_version_id)}, now)
        return application

    @property
    def service_version_id(self) -> UUID:
        return self._service_version_id

    @property
    def status(self) -> ApplicationStatus:
        return self._status

    @property
    def is_draft(self) -> bool:
        return self._status is ApplicationStatus.DRAFT

    @property
    def data(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    @property
    def fee_snapshot(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._fee_snapshot)

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def submitted_at(self) -> datetime | None:
        return self._submitted_at

    def ensure_draft(self) -> None:
        if not self.is_draft:
            raise ApplicationNotDraft(self.id)

    def apply_patch(self, patch: Mapping[str, Any], *, now: datetime) -> None:
        self.ensure_draft()
        self._data = merge_patch(self._data, dict(patch))
        self._updated_at = now
        self._record(EventType.DATA_UPDATED, {"fields": sorted(patch)}, now)

    def submit(self, fees: FeeBreakdown, *, now: datetime) -> None:
        self.ensure_draft()
        self._status = ApplicationStatus.SUBMITTED
        self._submitted_at = now
        self._updated_at = now
        self._fee_snapshot = fees.to_snapshot()
        self._record(
            EventType.SUBMITTED,
            {"feeTotal": self._fee_snapshot["total"], "currency": self._fee_snapshot["currency"]},
            now,
        )

    def pull_events(self) -> list[ApplicationEvent]:
        events, self._pending_events = self._pending_events, []
        return events

    def _record(self, event_type: EventType, metadata: Mapping[str, Any], now: datetime) -> None:
        self._pending_events.append(ApplicationEvent(self.id, event_type, dict(metadata), now))

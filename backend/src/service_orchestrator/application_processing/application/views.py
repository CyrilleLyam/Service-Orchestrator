from __future__ import annotations

from dataclasses import dataclass

from service_orchestrator.application_processing.domain.entities import (
    Application,
    ApplicationEvent,
)


@dataclass(frozen=True, slots=True)
class ApplicationView:
    application: Application
    service_code: str
    service_version: int
    events: tuple[ApplicationEvent, ...] = ()

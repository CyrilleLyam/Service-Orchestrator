from __future__ import annotations

from enum import StrEnum


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"


class EventType(StrEnum):
    CREATED = "application.created"
    DATA_UPDATED = "application.data_updated"
    SUBMITTED = "application.submitted"

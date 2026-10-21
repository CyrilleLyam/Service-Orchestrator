from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from service_orchestrator.shared.domain.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationFailed,
)
from service_orchestrator.shared.domain.validation import FieldError


class ApplicationNotFound(NotFoundError):
    code = "application_not_found"

    def __init__(self, application_id: UUID) -> None:
        super().__init__(f"Application {application_id} does not exist")


class ApplicationNotDraft(ConflictError):
    code = "application_not_draft"

    def __init__(self, application_id: UUID) -> None:
        super().__init__(f"Application {application_id} was submitted and can no longer change")


class IdempotencyKeyReused(ConflictError):
    code = "idempotency_key_reused"

    def __init__(self) -> None:
        super().__init__("This Idempotency-Key was already used for a different request")


class ApplicationDataInvalid(ValidationFailed):
    code = "application_data_invalid"

    def __init__(self, errors: Sequence[FieldError]) -> None:
        super().__init__("The application data is not acceptable", errors)


class SubmissionRejected(ValidationFailed):
    code = "submission_rejected"

    def __init__(self, errors: Sequence[FieldError]) -> None:
        super().__init__("The application failed validation and was not submitted", errors)

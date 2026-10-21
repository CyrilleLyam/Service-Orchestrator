from __future__ import annotations

from collections.abc import Sequence

from service_orchestrator.shared.domain.validation import FieldError


class RuleEvaluationError(Exception):
    pass


class DomainError(Exception):
    code = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    code = "not_found"


class ConflictError(DomainError):
    code = "conflict"


class ValidationFailed(DomainError):
    code = "validation_failed"

    def __init__(self, message: str, errors: Sequence[FieldError]) -> None:
        super().__init__(message)
        self.errors = tuple(errors)


class ConcurrentModification(ConflictError):
    code = "concurrent_modification"

    def __init__(self) -> None:
        super().__init__("The resource was changed by a concurrent request; retry the operation")

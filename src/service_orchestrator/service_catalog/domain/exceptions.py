from __future__ import annotations

from collections.abc import Sequence

from service_orchestrator.shared.domain.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationFailed,
)
from service_orchestrator.shared.domain.validation import FieldError


class ServiceNotFound(NotFoundError):
    code = "service_not_found"

    def __init__(self, service_code: str) -> None:
        super().__init__(f"Service {service_code!r} does not exist")


class VersionNotFound(NotFoundError):
    code = "version_not_found"

    def __init__(self, service_code: str, version: int | str) -> None:
        super().__init__(f"Service {service_code!r} has no version {version}")


class PublishedVersionNotFound(NotFoundError):
    code = "version_not_found"

    def __init__(self, version_id: object) -> None:
        super().__init__(f"No published service version has id {version_id}")


class ServiceCodeTaken(ConflictError):
    code = "service_code_taken"

    def __init__(self, service_code: str) -> None:
        super().__init__(f"A service with code {service_code!r} already exists")


class DraftAlreadyExists(ConflictError):
    code = "draft_already_exists"

    def __init__(self, service_code: str, version: int) -> None:
        super().__init__(
            f"Service {service_code!r} already has draft version {version}; "
            "edit or publish it first"
        )


class VersionNotDraft(ConflictError):
    code = "version_not_draft"

    def __init__(self, version: int) -> None:
        super().__init__(f"Version {version} is published; published versions are immutable")


class ServiceNotPublished(ConflictError):
    code = "service_not_published"

    def __init__(self, service_code: str) -> None:
        super().__init__(f"Service {service_code!r} has no published version yet")


class InvalidServiceCode(ValidationFailed):
    code = "invalid_service_code"

    def __init__(self, value: str) -> None:
        super().__init__(
            "Invalid service code",
            [
                FieldError(
                    "/code",
                    "pattern",
                    "Use 2-64 lowercase letters, digits and single hyphens, starting with a letter",
                )
            ],
        )


class DefinitionInvalid(ValidationFailed):
    code = "definition_invalid"

    def __init__(self, errors: Sequence[FieldError]) -> None:
        super().__init__("The service definition is not valid", errors)

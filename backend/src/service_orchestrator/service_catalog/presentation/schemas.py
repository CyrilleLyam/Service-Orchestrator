from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from service_orchestrator.service_catalog.application.queries.evaluate_payload import (
    FeeQuote,
    PayloadCheckResult,
)
from service_orchestrator.service_catalog.domain.entities import Service, ServiceVersion
from service_orchestrator.shared.presentation.schemas import (
    ApiModel,
    FeeBreakdownOut,
    FieldErrorOut,
)


class CreateServiceRequest(ApiModel):
    code: str = Field(min_length=2, max_length=64, examples=["delivery"])
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class CreateVersionRequest(ApiModel):
    definition: dict[str, Any] | None = Field(
        default=None, description="Omit to start from the current published definition."
    )


class UpdateVersionRequest(ApiModel):
    definition: dict[str, Any]


class PayloadRequest(ApiModel):
    data: dict[str, Any]


class VersionSummaryOut(ApiModel):
    version: int
    status: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None

    @classmethod
    def of(cls, version: ServiceVersion) -> VersionSummaryOut:
        return cls(
            version=version.version,
            status=version.status.value,
            created_at=version.created_at,
            updated_at=version.updated_at,
            published_at=version.published_at,
        )


class VersionOut(VersionSummaryOut):
    service_code: str
    definition: dict[str, Any]

    @classmethod
    def of_version(cls, service_code: str, version: ServiceVersion) -> VersionOut:
        return cls(
            **VersionSummaryOut.of(version).model_dump(),
            service_code=service_code,
            definition=version.definition,
        )


class ServiceSummaryOut(ApiModel):
    code: str
    name: str
    description: str
    created_at: datetime
    current_version: int | None

    @classmethod
    def of(cls, service: Service) -> ServiceSummaryOut:
        current = service.current_version
        return cls(
            code=str(service.code),
            name=service.name,
            description=service.description,
            created_at=service.created_at,
            current_version=current.version if current else None,
        )


class ServiceOut(ApiModel):
    code: str
    name: str
    description: str
    created_at: datetime
    published: VersionOut | None = Field(description="The current published version, if any.")
    versions: list[VersionSummaryOut]

    @classmethod
    def of(cls, service: Service) -> ServiceOut:
        code = str(service.code)
        current = service.current_version
        return cls(
            code=code,
            name=service.name,
            description=service.description,
            created_at=service.created_at,
            published=VersionOut.of_version(code, current) if current else None,
            versions=[VersionSummaryOut.of(v) for v in service.versions],
        )


class ValidationResultOut(ApiModel):
    service_code: str
    version: int
    valid: bool
    errors: list[FieldErrorOut]

    @classmethod
    def of(cls, result: PayloadCheckResult) -> ValidationResultOut:
        return cls(
            service_code=result.service_code,
            version=result.version,
            valid=result.evaluation.valid,
            errors=[FieldErrorOut.of(e) for e in result.evaluation.errors],
        )


class QuoteOut(ApiModel):
    service_code: str
    version: int
    fees: FeeBreakdownOut

    @classmethod
    def of(cls, quote: FeeQuote) -> QuoteOut:
        return cls(
            service_code=quote.service_code,
            version=quote.version,
            fees=FeeBreakdownOut.of(quote.fees),
        )

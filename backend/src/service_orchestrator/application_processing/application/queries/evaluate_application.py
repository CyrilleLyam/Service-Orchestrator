from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from service_orchestrator.application_processing.application.ports import (
    ApplicationUnitOfWork,
    ServiceCatalogGateway,
)
from service_orchestrator.application_processing.domain.exceptions import ApplicationNotFound
from service_orchestrator.fee_policy.calculator import FeeBreakdown
from service_orchestrator.shared.application.limits import DocumentLimits
from service_orchestrator.shared.application.payload_checker import (
    PayloadChecker,
    PayloadEvaluation,
)
from service_orchestrator.shared.domain.exceptions import ValidationFailed
from service_orchestrator.shared.domain.json_limits import check_json_document


@dataclass(frozen=True, slots=True)
class ApplicationCheckResult:
    service_code: str
    version: int
    evaluation: PayloadEvaluation


@dataclass(frozen=True, slots=True)
class ApplicationFeeQuote:
    service_code: str
    version: int
    fees: FeeBreakdown


class ValidateApplication:
    """Preview saved or replacement data against the pinned version without changing the draft."""

    def __init__(
        self,
        uow: ApplicationUnitOfWork,
        catalog: ServiceCatalogGateway,
        checker: PayloadChecker,
        limits: DocumentLimits,
    ) -> None:
        self._uow = uow
        self._catalog = catalog
        self._checker = checker
        self._limits = limits

    def execute(
        self, application_id: UUID, data: dict[str, Any] | None = None
    ) -> ApplicationCheckResult:
        with self._uow as uow:
            application = uow.applications.get(application_id)
            if application is None:
                raise ApplicationNotFound(application_id)
            application.ensure_draft()
        pinned = self._catalog.published_version(application.service_version_id)
        payload = application.data if data is None else data
        if errors := check_json_document(
            payload,
            max_bytes=self._limits.max_payload_bytes,
            max_depth=self._limits.max_payload_depth,
        ):
            evaluation = PayloadEvaluation(tuple(errors), None)
        else:
            evaluation = self._checker.evaluate(pinned.definition, payload)
        return ApplicationCheckResult(pinned.service_code, pinned.version, evaluation)


class QuoteApplication:
    def __init__(self, validate: ValidateApplication) -> None:
        self._validate = validate

    def execute(
        self, application_id: UUID, data: dict[str, Any] | None = None
    ) -> ApplicationFeeQuote:
        result = self._validate.execute(application_id, data)
        if result.evaluation.fees is None:
            raise ValidationFailed(
                "Fees can only be quoted for a valid payload", result.evaluation.errors
            )
        return ApplicationFeeQuote(result.service_code, result.version, result.evaluation.fees)

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from service_orchestrator.fee_policy.calculator import FeeBreakdown
from service_orchestrator.service_catalog.application.queries.published_versions import (
    PublishedVersions,
)
from service_orchestrator.shared.application.limits import DocumentLimits
from service_orchestrator.shared.application.payload_checker import (
    PayloadChecker,
    PayloadEvaluation,
)
from service_orchestrator.shared.domain.exceptions import ValidationFailed
from service_orchestrator.shared.domain.json_limits import check_json_document


@dataclass(frozen=True, slots=True)
class PayloadCheckResult:
    service_code: str
    version: int
    evaluation: PayloadEvaluation


@dataclass(frozen=True, slots=True)
class FeeQuote:
    service_code: str
    version: int
    fees: FeeBreakdown


class ValidatePayload:
    def __init__(
        self, published: PublishedVersions, checker: PayloadChecker, limits: DocumentLimits
    ) -> None:
        self._published = published
        self._checker = checker
        self._limits = limits

    def execute(self, service_code: str, data: Any) -> PayloadCheckResult:
        version = self._published.current(service_code)
        if errors := check_json_document(
            data, max_bytes=self._limits.max_payload_bytes, max_depth=self._limits.max_payload_depth
        ):
            evaluation = PayloadEvaluation(tuple(errors), None)
        else:
            evaluation = self._checker.evaluate(version.definition, data)
        return PayloadCheckResult(service_code, version.version, evaluation)


class QuoteFees:
    def __init__(self, validate: ValidatePayload) -> None:
        self._validate = validate

    def execute(self, service_code: str, data: Any) -> FeeQuote:
        result = self._validate.execute(service_code, data)
        if result.evaluation.fees is None:
            raise ValidationFailed(
                "Fees can only be quoted for a valid payload", result.evaluation.errors
            )
        return FeeQuote(result.service_code, result.version, result.evaluation.fees)

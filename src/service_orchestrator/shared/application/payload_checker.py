from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from service_orchestrator.fee_policy.calculator import (
    FeeBreakdown,
    FeeCalculationError,
    calculate_fees,
)
from service_orchestrator.shared.application.ports import RuleEvaluator, SchemaValidator
from service_orchestrator.shared.domain.exceptions import RuleEvaluationError
from service_orchestrator.shared.domain.field_path import MISSING, get_value, to_field_pointer
from service_orchestrator.shared.domain.validation import FieldError, dedupe

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PayloadEvaluation:
    errors: tuple[FieldError, ...]
    fees: FeeBreakdown | None

    @property
    def valid(self) -> bool:
        return not self.errors


def localized(text: Any, default: str) -> str:
    if isinstance(text, str):
        return text
    if isinstance(text, Mapping) and text:
        return str(text.get("en") or next(iter(text.values())))
    return default


class PayloadChecker:
    def __init__(self, schema_validator: SchemaValidator, rule_evaluator: RuleEvaluator) -> None:
        self._schema_validator = schema_validator
        self._rules = rule_evaluator

    def evaluate(self, definition: Mapping[str, Any], data: Any) -> PayloadEvaluation:
        schema_errors = self._schema_validator.validate(definition["dataSchema"], data)
        rule_errors = self._check_rules(
            definition.get("rules", []), data, run_assertions=not schema_errors
        )
        errors = dedupe([*schema_errors, *rule_errors])
        logger.debug(
            "payload checked",
            extra={"errors": [f"{e.path or '/'}:{e.code}" for e in errors[:20]]},
        )
        if errors:
            return PayloadEvaluation(tuple(errors), None)
        try:
            fees = calculate_fees(
                definition.get("fees", []),
                lambda condition: self._rules.test(condition, data),
                lambda expression: self._rules.evaluate(expression, data),
            )
        except FeeCalculationError as exc:
            logger.warning(
                "fee calculation failed", extra={"fee": exc.fee_code, "reason": str(exc)}
            )
            return PayloadEvaluation((FieldError("", "fee_calculation_failed", str(exc)),), None)
        logger.debug(
            "fees calculated",
            extra={"fees": [f"{line.code}={line.amount.amount}" for line in fees.lines]},
        )
        return PayloadEvaluation((), fees)

    def _check_rules(
        self, rules: Sequence[Mapping[str, Any]], data: Any, *, run_assertions: bool
    ) -> list[FieldError]:
        errors: list[FieldError] = []
        for rule in rules:
            kind, rule_id = rule["type"], rule["id"]
            if kind == "assert" and not run_assertions:
                continue
            try:
                applies = self._rules.test(rule["when"], data) if "when" in rule else True
                if kind == "require" and applies:
                    errors.extend(self._missing_fields(rule, data))
                elif kind == "visible" and not applies:
                    errors.extend(self._hidden_fields_present(rule, data))
                elif kind == "assert" and applies and not self._rules.test(rule["assert"], data):
                    message = localized(rule.get("message"), f"Rule {rule_id!r} failed")
                    errors.append(
                        FieldError(rule.get("path", ""), "assertion_failed", message, rule_id)
                    )
            except RuleEvaluationError as exc:
                if run_assertions:
                    errors.append(
                        FieldError(
                            rule.get("path", ""), "rule_evaluation_failed", str(exc), rule_id
                        )
                    )
        return errors

    @staticmethod
    def _missing_fields(rule: Mapping[str, Any], data: Any) -> list[FieldError]:
        return [
            FieldError(
                to_field_pointer(field),
                "required",
                localized(rule.get("message"), "This field is required"),
                rule["id"],
            )
            for field in rule["fields"]
            if get_value(data, field) in (MISSING, None, "", [])
        ]

    @staticmethod
    def _hidden_fields_present(rule: Mapping[str, Any], data: Any) -> list[FieldError]:
        return [
            FieldError(
                to_field_pointer(field),
                "not_applicable",
                localized(rule.get("message"), "This field does not apply to the current answers"),
                rule["id"],
            )
            for field in rule["fields"]
            if get_value(data, field) not in (MISSING, None)
        ]

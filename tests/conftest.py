from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from service_orchestrator.service_catalog.application.definition_checker import DefinitionChecker
from service_orchestrator.shared.application.limits import DocumentLimits
from service_orchestrator.shared.application.payload_checker import PayloadChecker
from service_orchestrator.shared.infrastructure.rule_evaluator import JsonLogicEvaluator
from service_orchestrator.shared.infrastructure.schema_validator import JsonSchemaValidator

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def load_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text())


@pytest.fixture
def delivery() -> dict[str, Any]:
    return load_example("delivery_service.json")


@pytest.fixture
def event_registration() -> dict[str, Any]:
    return load_example("event_registration.json")


@pytest.fixture
def equipment_rental() -> dict[str, Any]:
    return load_example("equipment_rental.json")


@pytest.fixture
def delivery_definition(delivery: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(delivery["definition"])


@pytest.fixture
def schema_validator() -> JsonSchemaValidator:
    return JsonSchemaValidator()


@pytest.fixture
def rule_evaluator() -> JsonLogicEvaluator:
    return JsonLogicEvaluator()


@pytest.fixture
def definition_checker(
    schema_validator: JsonSchemaValidator, rule_evaluator: JsonLogicEvaluator
) -> DefinitionChecker:
    return DefinitionChecker(schema_validator, rule_evaluator, DocumentLimits())


@pytest.fixture
def payload_checker(
    schema_validator: JsonSchemaValidator, rule_evaluator: JsonLogicEvaluator
) -> PayloadChecker:
    return PayloadChecker(schema_validator, rule_evaluator)

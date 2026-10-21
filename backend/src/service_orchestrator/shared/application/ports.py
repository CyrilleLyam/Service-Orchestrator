from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from service_orchestrator.shared.domain.validation import FieldError


class SchemaValidator(Protocol):
    def validate(self, schema: Mapping[str, Any], instance: Any) -> list[FieldError]: ...

    def check_schema(self, schema: Any) -> list[FieldError]: ...


class RuleEvaluator(Protocol):
    def evaluate(self, expression: Any, data: Any) -> Any: ...

    def test(self, expression: Any, data: Any) -> bool: ...

    def check(self, expression: Any, field_exists: Callable[[str], bool]) -> list[FieldError]: ...

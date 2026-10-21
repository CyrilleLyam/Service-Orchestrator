from __future__ import annotations

import math
import operator
from collections.abc import Callable
from itertools import pairwise
from typing import Any, Final

from service_orchestrator.shared.domain.exceptions import RuleEvaluationError
from service_orchestrator.shared.domain.field_path import FIELD_PATH_PATTERN, MISSING, get_value
from service_orchestrator.shared.domain.validation import FieldError, escape_token

_ARITY: Final[dict[str, tuple[int, int | None]]] = {
    "if": (1, None),
    "and": (1, None),
    "or": (1, None),
    "!": (1, 1),
    "!!": (1, 1),
    "==": (2, 2),
    "!=": (2, 2),
    "<": (2, 3),
    "<=": (2, 3),
    ">": (2, 2),
    ">=": (2, 2),
    "+": (1, None),
    "-": (1, 2),
    "*": (1, None),
    "/": (2, 2),
    "%": (2, 2),
    "min": (1, None),
    "max": (1, None),
    "in": (2, 2),
}
SUPPORTED_OPERATORS: Final = frozenset({"var", *_ARITY})


def truthy(value: Any) -> bool:
    if isinstance(value, dict):
        return True
    return bool(value)


def strict_equals(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _is_number(a) and _is_number(b):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(strict_equals(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(strict_equals(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number(value: Any) -> int | float:
    if not _is_number(value):
        raise RuleEvaluationError(f"Expected a number, got {_type_name(value)}")
    return value


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    return {bool: "boolean", str: "string", list: "array", dict: "object"}.get(
        type(value), "number"
    )


def _ordered(values: list[Any], compare: Callable[[Any, Any], bool]) -> bool:
    comparable = all(_is_number(v) for v in values) or all(isinstance(v, str) for v in values)
    return comparable and all(compare(a, b) for a, b in pairwise(values))


def _divide(values: list[Any]) -> float:
    dividend, divisor = _number(values[0]), _number(values[1])
    if divisor == 0:
        raise RuleEvaluationError("Division by zero")
    return dividend / divisor


def _modulo(values: list[Any]) -> int | float:
    dividend, divisor = _number(values[0]), _number(values[1])
    if divisor == 0:
        raise RuleEvaluationError("Modulo by zero")
    return dividend % divisor


def _contains(values: list[Any]) -> bool:
    needle, haystack = values
    if isinstance(haystack, list):
        return any(strict_equals(needle, item) for item in haystack)
    if isinstance(haystack, str) and isinstance(needle, str):
        return needle in haystack
    return False


def _finite(result: int | float) -> int | float:
    if isinstance(result, float) and not math.isfinite(result):
        raise RuleEvaluationError("Arithmetic result is not a finite number")
    return result


_STRICT_OPERATIONS: Final[dict[str, Callable[[list[Any]], Any]]] = {
    "!": lambda v: not truthy(v[0]),
    "!!": lambda v: truthy(v[0]),
    "==": lambda v: strict_equals(v[0], v[1]),
    "!=": lambda v: not strict_equals(v[0], v[1]),
    "<": lambda v: _ordered(v, operator.lt),
    "<=": lambda v: _ordered(v, operator.le),
    ">": lambda v: _ordered(v, operator.gt),
    ">=": lambda v: _ordered(v, operator.ge),
    "+": lambda v: _finite(sum(_number(x) for x in v)),
    "-": lambda v: _finite(-_number(v[0]) if len(v) == 1 else _number(v[0]) - _number(v[1])),
    "*": lambda v: _finite(math.prod(_number(x) for x in v)),
    "/": lambda v: _finite(_divide(v)),
    "%": _modulo,
    "min": lambda v: min(_number(x) for x in v),
    "max": lambda v: max(_number(x) for x in v),
    "in": _contains,
}


class JsonLogicEvaluator:
    def __init__(
        self,
        *,
        max_depth: int = 16,
        max_nodes: int = 200,
        max_steps: int = 10_000,
        max_string_length: int = 1_000,
    ) -> None:
        self._max_depth = max_depth
        self._max_nodes = max_nodes
        self._max_steps = max_steps
        self._max_string_length = max_string_length

    def check(self, expression: Any, field_exists: Callable[[str], bool]) -> list[FieldError]:
        errors: list[FieldError] = []
        nodes = 0

        def visit(node: Any, path: str, depth: int) -> None:
            nonlocal nodes
            nodes += 1
            if nodes > self._max_nodes:
                return
            if depth > self._max_depth:
                errors.append(
                    FieldError(path, "too_deep", f"Expression nesting exceeds {self._max_depth}")
                )
                return
            if isinstance(node, list):
                for index, item in enumerate(node):
                    visit(item, f"{path}/{index}", depth + 1)
            elif isinstance(node, str):
                if len(node) > self._max_string_length:
                    errors.append(FieldError(path, "too_long", "String literal is too long"))
            elif isinstance(node, dict):
                visit_operation(node, path, depth)
            elif not (node is None or isinstance(node, bool | int | float)):
                errors.append(FieldError(path, "invalid_expression", "Unsupported literal"))

        def visit_operation(node: dict[str, Any], path: str, depth: int) -> None:
            if len(node) != 1:
                errors.append(
                    FieldError(
                        path, "invalid_expression", "An operation must have exactly one operator"
                    )
                )
                return
            ((op, raw_args),) = node.items()
            op_path = f"{path}/{escape_token(op)}"
            if op == "var":
                self._check_var(raw_args, op_path, field_exists, errors)
                return
            if op not in _ARITY:
                errors.append(
                    FieldError(op_path, "unsupported_operator", f"Operator {op!r} is not supported")
                )
                return
            args = raw_args if isinstance(raw_args, list) else [raw_args]
            low, high = _ARITY[op]
            if len(args) < low or (high is not None and len(args) > high):
                expected = f"{low}" if low == high else f"at least {low}"
                if high is not None and high != low:
                    expected = f"{low} to {high}"
                errors.append(
                    FieldError(
                        op_path,
                        "invalid_arity",
                        f"{op!r} takes {expected} arguments, got {len(args)}",
                    )
                )
            if isinstance(raw_args, list):
                for index, arg in enumerate(args):
                    visit(arg, f"{op_path}/{index}", depth + 1)
            else:
                visit(raw_args, op_path, depth + 1)

        visit(expression, "", 1)
        if nodes > self._max_nodes:
            errors.append(
                FieldError("", "too_complex", f"Expression has more than {self._max_nodes} nodes")
            )
        return errors

    @staticmethod
    def _check_var(
        args: Any, path: str, field_exists: Callable[[str], bool], errors: list[FieldError]
    ) -> None:
        if isinstance(args, list):
            if not 1 <= len(args) <= 2:
                errors.append(
                    FieldError(
                        path, "invalid_var", "'var' takes a field path and an optional default"
                    )
                )
                return
            if len(args) == 2 and isinstance(args[1], dict | list):
                errors.append(
                    FieldError(path, "invalid_var", "'var' defaults must be scalar values")
                )
            name = args[0]
        else:
            name = args
        if not isinstance(name, str) or not FIELD_PATH_PATTERN.match(name):
            errors.append(
                FieldError(
                    path,
                    "invalid_var",
                    "'var' must name a field with a dot path, e.g. 'contact.email'",
                )
            )
        elif not field_exists(name):
            errors.append(
                FieldError(path, "unknown_field", f"Field {name!r} is not defined in dataSchema")
            )

    def evaluate(self, expression: Any, data: Any) -> Any:
        return _Evaluation(data, self._max_depth, self._max_steps).run(expression, 1)

    def test(self, expression: Any, data: Any) -> bool:
        return truthy(self.evaluate(expression, data))


class _Evaluation:
    def __init__(self, data: Any, max_depth: int, max_steps: int) -> None:
        self._data = data
        self._max_depth = max_depth
        self._steps_left = max_steps

    def run(self, node: Any, depth: int) -> Any:
        self._steps_left -= 1
        if self._steps_left < 0:
            raise RuleEvaluationError("Rule evaluation exceeded its step budget")
        if depth > self._max_depth:
            raise RuleEvaluationError("Rule expression is nested too deeply")
        if isinstance(node, list):
            return [self.run(item, depth + 1) for item in node]
        if not isinstance(node, dict):
            return node
        if len(node) != 1:
            raise RuleEvaluationError("An operation must have exactly one operator")

        ((op, raw_args),) = node.items()
        if op == "var":
            return self._var(raw_args)
        args = raw_args if isinstance(raw_args, list) else [raw_args]
        if op == "if":
            return self._if(args, depth)
        if op in ("and", "or"):
            return self._short_circuit(op, args, depth)
        operation = _STRICT_OPERATIONS.get(op)
        if operation is None:
            raise RuleEvaluationError(f"Operator {op!r} is not supported")
        return operation([self.run(arg, depth + 1) for arg in args])

    def _var(self, args: Any) -> Any:
        if isinstance(args, list):
            name, default = (args[0] if args else None), (args[1] if len(args) > 1 else None)
        else:
            name, default = args, None
        if not isinstance(name, str):
            raise RuleEvaluationError("'var' must name a field")
        value = get_value(self._data, name)
        return default if value is MISSING or value is None else value

    def _if(self, args: list[Any], depth: int) -> Any:
        index = 0
        while index + 1 < len(args):
            if truthy(self.run(args[index], depth + 1)):
                return self.run(args[index + 1], depth + 1)
            index += 2
        return self.run(args[index], depth + 1) if index < len(args) else None

    def _short_circuit(self, op: str, args: list[Any], depth: int) -> Any:
        result: Any = None
        for arg in args:
            result = self.run(arg, depth + 1)
            if truthy(result) == (op == "or"):
                return result
        return result

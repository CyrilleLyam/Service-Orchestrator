from __future__ import annotations

import pytest

from service_orchestrator.shared.domain.exceptions import RuleEvaluationError
from service_orchestrator.shared.infrastructure.rule_evaluator import JsonLogicEvaluator

DATA = {
    "express": True,
    "distanceKm": 40,
    "sessions": ["keynote", "workshop-a"],
    "count": 1,
    "contact": {"email": "a@example.com"},
    "empty": "",
}


def known(path: str) -> bool:
    return path.split(".")[0] in DATA


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ({"==": [{"var": "express"}, True]}, True),
        ({"==": [{"var": "count"}, True]}, False),
        ({"==": [{"var": "count"}, 1.0]}, True),
        ({"!=": [{"var": "count"}, "1"]}, True),
        ({"<=": [{"var": "distanceKm"}, 50]}, True),
        ({"<": [0, {"var": "distanceKm"}, 40]}, False),
        ({"<": [None, 1]}, False),
        ({">=": ["b", "a"]}, True),
        ({"in": ["workshop-a", {"var": "sessions"}]}, True),
        ({"in": ["work", "workshop"]}, True),
        ({"if": [{"var": "express"}, "fast", "slow"]}, "fast"),
        ({"if": [False, 1, False, 2, 3]}, 3),
        ({"and": [True, 0, {"/": [1, 0]}]}, 0),
        ({"or": [0, "", "x"]}, "x"),
        ({"!": [{"var": "empty"}]}, True),
        ({"!!": [[]]}, False),
        ({"+": [1, 2.5]}, 3.5),
        ({"-": [5]}, -5),
        ({"*": [2, 3, 4]}, 24),
        ({"%": [7, 4]}, 3),
        ({"min": [3, 1, 2]}, 1),
        ({"var": "contact.email"}, "a@example.com"),
        ({"var": "sessions.1"}, "workshop-a"),
        ({"var": ["missing", 7]}, 7),
        ({"var": "missing"}, None),
    ],
)
def test_evaluates_supported_operators(expression, expected) -> None:
    assert JsonLogicEvaluator().evaluate(expression, DATA) == expected


@pytest.mark.parametrize(
    "expression",
    [{"/": [1, 0]}, {"%": [1, 0]}, {"+": ["a", 1]}, {"*": [True, 2]}, {"*": [1e308, 1e308]}],
)
def test_runtime_errors_are_reported_not_raised_as_python_errors(expression) -> None:
    with pytest.raises(RuleEvaluationError):
        JsonLogicEvaluator().evaluate(expression, DATA)


def test_step_budget_bounds_evaluation() -> None:
    evaluator = JsonLogicEvaluator(max_steps=10)
    with pytest.raises(RuleEvaluationError, match="step budget"):
        evaluator.evaluate({"+": list(range(20))}, {})


def test_depth_limit_applies_at_runtime_too() -> None:
    expression: object = True
    for _ in range(30):
        expression = {"!": [expression]}
    with pytest.raises(RuleEvaluationError, match="nested too deeply"):
        JsonLogicEvaluator(max_depth=16).evaluate(expression, {})


def test_check_accepts_valid_expression() -> None:
    expression = {"and": [{"==": [{"var": "express"}, True]}, {"<": [{"var": "distanceKm"}, 50]}]}
    assert JsonLogicEvaluator().check(expression, known) == []


@pytest.mark.parametrize(
    ("expression", "code", "path"),
    [
        ({"eval": ["1+1"]}, "unsupported_operator", "/eval"),
        ({"==": [1]}, "invalid_arity", "/=="),
        ({"==": [1, 2], "!=": [1, 2]}, "invalid_expression", ""),
        ({"var": "nope"}, "unknown_field", "/var"),
        ({"var": ""}, "invalid_var", "/var"),
        ({"var": ["express", {"a": 1}]}, "invalid_var", "/var"),
        ({"and": [True, {"var": "../etc"}]}, "invalid_var", "/and/1/var"),
    ],
)
def test_check_rejects_unsupported_or_invalid_expressions(expression, code, path) -> None:
    errors = JsonLogicEvaluator().check(expression, known)
    assert (path, code) in [(e.path, e.code) for e in errors]


def test_check_rejects_deeply_nested_rules() -> None:
    expression: object = True
    for _ in range(20):
        expression = {"!": [expression]}
    errors = JsonLogicEvaluator(max_depth=16).check(expression, known)
    assert [e.code for e in errors] == ["too_deep"]


def test_check_rejects_overly_complex_rules() -> None:
    expression = {"+": list(range(300))}
    errors = JsonLogicEvaluator(max_nodes=200).check(expression, known)
    assert "too_complex" in [e.code for e in errors]

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "service_orchestrator"
FRAMEWORKS = ("fastapi", "starlette", "sqlalchemy", "pydantic", "alembic", "psycopg", "jsonschema")


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def modules_in(*parts: str) -> list[Path]:
    return sorted(PACKAGE.joinpath(*parts).rglob("*.py"))


INNER_LAYERS = [
    *modules_in("shared", "domain"),
    *modules_in("shared", "application"),
    *modules_in("fee_policy"),
    *modules_in("service_catalog", "domain"),
    *modules_in("service_catalog", "application"),
    *modules_in("application_processing", "domain"),
    *modules_in("application_processing", "application"),
]


@pytest.mark.parametrize("module", INNER_LAYERS, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_inner_layers_do_not_depend_on_frameworks_or_outer_layers(module: Path) -> None:
    for name in imports_of(module):
        assert not name.startswith(FRAMEWORKS), f"{module.name} imports {name}"
        assert ".infrastructure" not in name, f"{module.name} imports {name}"
        assert ".presentation" not in name, f"{module.name} imports {name}"
        assert "bootstrap" not in name, f"{module.name} imports {name}"


@pytest.mark.parametrize(
    "module",
    modules_in("application_processing", "domain")
    + modules_in("application_processing", "application"),
    ids=lambda p: str(p.relative_to(PACKAGE)),
)
def test_application_processing_core_does_not_reach_into_the_catalog(module: Path) -> None:
    for name in imports_of(module):
        assert "service_catalog" not in name, f"{module.name} imports {name}"

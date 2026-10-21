from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from service_orchestrator.bootstrap.dependencies import Container, build_container
from service_orchestrator.config import Settings
from service_orchestrator.main import create_app
from service_orchestrator.service_catalog.application.commands.create_service import (
    CreateServiceCommand,
)
from service_orchestrator.service_catalog.application.commands.create_version import (
    CreateDraftVersionCommand,
)
from service_orchestrator.service_catalog.application.commands.publish_version import (
    PublishVersionCommand,
)
from service_orchestrator.service_catalog.domain.entities import ServiceVersion
from service_orchestrator.service_catalog.domain.exceptions import ServiceNotFound

ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://orchestrator:orchestrator@localhost:5433/service_orchestrator_test",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if Path(str(item.fspath)).is_relative_to(Path(__file__).parent):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def database_url() -> str:
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL is not reachable ({exc.orig}); run `docker compose up -d db`")
    finally:
        admin.dispose()

    rendered = url.render_as_string(hide_password=False)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", rendered.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return rendered


@pytest.fixture(scope="session")
def container(database_url: str) -> Iterator[Container]:
    container = build_container(Settings(database_url=database_url))
    yield container
    container.engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(container: Container) -> None:
    with container.engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE application_events, applications, service_versions, services "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def client(container: Container) -> TestClient:
    return TestClient(create_app(container=container))


@pytest.fixture
def publish(container: Container) -> Callable[..., ServiceVersion]:

    def _publish(code: str, definition: dict[str, Any]) -> ServiceVersion:
        try:
            container.get_service().execute(code)
        except ServiceNotFound:
            container.create_service().execute(CreateServiceCommand(code=code, name=code.title()))
        draft = container.create_draft_version().execute(
            CreateDraftVersionCommand(service_code=code, definition=definition)
        )
        return container.publish_version().execute(
            PublishVersionCommand(service_code=code, version=draft.version)
        )

    return _publish

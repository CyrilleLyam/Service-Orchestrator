from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from service_orchestrator.application_processing.application.commands.create_draft import (
    CreateApplicationDraftCommand,
)
from service_orchestrator.service_catalog.application.commands.create_service import (
    CreateServiceCommand,
)
from service_orchestrator.service_catalog.application.commands.create_version import (
    CreateDraftVersionCommand,
)
from service_orchestrator.service_catalog.application.commands.publish_version import (
    PublishVersionCommand,
)
from service_orchestrator.shared.domain.exceptions import ConflictError

RACERS = 8


def race(action: Callable[[], object]) -> list[str]:
    barrier = threading.Barrier(RACERS)

    def attempt(_: int) -> str:
        barrier.wait()
        try:
            action()
        except ConflictError as exc:
            return exc.code
        return "ok"

    with ThreadPoolExecutor(RACERS) as pool:
        return sorted(pool.map(attempt, range(RACERS)))


def test_concurrent_publish_publishes_exactly_once(container, delivery_definition) -> None:
    container.create_service().execute(CreateServiceCommand("delivery", "Delivery"))
    container.create_draft_version().execute(
        CreateDraftVersionCommand("delivery", delivery_definition)
    )

    results = race(
        lambda: container.publish_version().execute(PublishVersionCommand("delivery", 1))
    )

    assert results == ["ok"] + ["version_not_draft"] * (RACERS - 1)
    service = container.get_service().execute("delivery")
    assert service.current_version.version == 1


def test_concurrent_drafts_create_exactly_one_version(container, publish, delivery_definition):
    publish("delivery", delivery_definition)

    results = race(
        lambda: container.create_draft_version().execute(CreateDraftVersionCommand("delivery"))
    )

    assert results == ["draft_already_exists"] * (RACERS - 1) + ["ok"]
    versions = container.get_service().execute("delivery").versions
    assert [v.version for v in versions] == [1, 2]


def test_concurrent_service_creation_with_the_same_code(container) -> None:
    results = race(
        lambda: container.create_service().execute(CreateServiceCommand("delivery", "Delivery"))
    )

    assert results.count("ok") == 1
    assert set(results) - {"ok"} <= {"service_code_taken", "concurrent_modification"}
    assert container.list_services().execute().total == 1


def test_concurrent_submissions_submit_exactly_once(container, publish, delivery_definition):
    publish("delivery", delivery_definition)
    created = container.create_application_draft().execute(
        CreateApplicationDraftCommand("delivery", {"distanceKm": 3, "weightKg": 1})
    )
    application_id = created.view.application.id

    results = race(lambda: container.submit_application().execute(application_id))

    assert results == ["application_not_draft"] * (RACERS - 1) + ["ok"]
    view = container.get_application().execute(application_id)
    assert [e.event_type.value for e in view.events].count("application.submitted") == 1

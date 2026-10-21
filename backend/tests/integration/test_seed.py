from __future__ import annotations

from pathlib import Path

from service_orchestrator.seed import apply_sql
from tests.integration.api import data

SEED = Path(__file__).resolve().parents[2] / "seeds" / "services.sql"


def test_sql_seed_publishes_the_example_services(
    container, client, definition_checker, delivery, event_registration, equipment_rental
) -> None:
    apply_sql(container.engine, SEED)
    apply_sql(container.engine, SEED)

    services = data(client.get("/v1/services"))
    assert [(s["code"], s["currentVersion"]) for s in services] == [
        ("delivery", 1),
        ("equipment-rental", 1),
        ("event-registration", 1),
    ]
    for example in (delivery, event_registration, equipment_rental):
        detail = data(client.get(f"/v1/services/{example['code']}"))
        assert [v["version"] for v in detail["versions"]] == [1]
        assert detail["published"]["definition"] == example["definition"]
        assert definition_checker.check(detail["published"]["definition"]) == []


def test_seeded_service_accepts_applications(container, client) -> None:
    apply_sql(container.engine, SEED)
    application = data(
        client.post(
            "/v1/applications",
            json={"serviceCode": "delivery", "data": {"distanceKm": 4, "weightKg": 1}},
        ),
        201,
    )
    submitted = data(client.post(f"/v1/applications/{application['id']}/submit"))
    assert submitted["fees"]["total"] == 5000


def test_sql_seed_leaves_existing_services_alone(container, client, publish, delivery) -> None:
    changed = dict(delivery["definition"], fees=[])
    publish("delivery", changed)
    apply_sql(container.engine, SEED)
    detail = data(client.get("/v1/services/delivery"))
    assert detail["published"]["definition"]["fees"] == []

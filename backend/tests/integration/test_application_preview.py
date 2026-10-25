from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from tests.integration.api import data, error
from tests.integration.test_api_lifecycle import create_and_publish
from tests.payloads import PAYLOADS


@pytest.mark.parametrize("example_name", list(PAYLOADS))
def test_preview_stays_pinned_and_does_not_change_saved_data(
    client: TestClient, request, example_name: str
) -> None:
    example = request.getfixturevalue(example_name)
    create_and_publish(client, example)
    application = data(
        client.post(
            "/v1/applications",
            json={"serviceCode": example["code"], "data": PAYLOADS[example_name]},
        ),
        201,
    )
    base = f"/v1/applications/{application['id']}"
    before = data(client.get(base))
    definition = copy.deepcopy(example["definition"])
    definition["fees"] = [{"code": "NEW", "amount": 1, "currency": "KHR"}]
    version = data(
        client.post(f"/v1/services/{example['code']}/versions", json={"definition": definition}),
        201,
    )
    data(client.post(f"/v1/services/{example['code']}/versions/{version['version']}/publish"))
    pinned = data(client.get(f"/v1/services/{example['code']}/versions/1"))
    assert pinned["definition"] == example["definition"]
    checked = data(client.post(f"{base}/validate"))
    assert checked["valid"] is True
    assert checked["version"] == 1
    preview = data(client.post(f"{base}/quote", json={"data": PAYLOADS[example_name]}))
    latest = data(
        client.post(f"/v1/services/{example['code']}/quote", json={"data": PAYLOADS[example_name]})
    )
    assert preview["version"] == 1
    assert latest["version"] == 2
    assert latest["fees"]["total"] == 1
    assert preview["fees"]["total"] > 1
    assert data(client.get(base)) == before
    assert data(client.post(f"{base}/validate", json={"data": {}}))["valid"] is False
    error(client.post(f"{base}/quote", json={"data": {}}), 422)
    assert data(client.get(base)) == before
    submitted = data(client.post(f"{base}/submit"))
    assert submitted["fees"] == preview["fees"]
    error(client.post(f"{base}/quote"), 409)

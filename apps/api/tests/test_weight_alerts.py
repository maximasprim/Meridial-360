"""Dashboard follow-up of daily-gain alerts: list, mark reviewed. Needs the test database."""
import pathlib

import pytest

from tests.test_feedlot_export import _import, _org

pytestmark = pytest.mark.asyncio
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sahara_oasis_second_cycle.xlsx"


async def test_alerts_list_and_mark_reviewed(client, engine):
    h = await _org(client, engine, "alerts1@example.com")
    await _import(client, h, FIXTURE.read_bytes(), "v1.xlsx")
    r = await client.get("/api/v1/weights/alerts", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["threshold"] == 2.0 and body["count"] == len(body["alerts"])
    if not body["alerts"]:
        pytest.skip("the fixture has no animal with a daily gain outside +/-2 among live animals")
    assert all(abs(a["adg"]) > 2.0 for a in body["alerts"])
    first = body["alerts"][0]
    done = await client.post(f"/api/v1/weights/alerts/{first['animal_id']}/review", headers=h, json={"alert_date": first["to_date"]})
    assert done.status_code == 200
    after = (await client.get("/api/v1/weights/alerts", headers=h)).json()
    assert after["count"] == body["count"] - 1 and all(a["animal_id"] != first["animal_id"] for a in after["alerts"])
    again = await client.post(f"/api/v1/weights/alerts/{first['animal_id']}/review", headers=h, json={"alert_date": first["to_date"]})
    assert again.status_code == 200                                                       # marking twice is harmless

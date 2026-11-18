"""Worksheet version history, weight corrections (void + append), restore and unpost. Needs the test database."""
import io
import pathlib

import openpyxl
import pytest

from tests.test_feedlot_export import _import, _org

pytestmark = pytest.mark.asyncio
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sahara_oasis_second_cycle.xlsx"


def _changed_workbook(new_kg: float) -> bytes:
    wb = openpyxl.load_workbook(io.BytesIO(FIXTURE.read_bytes()))
    ws = wb["BATCH 5"]
    row = next(r for r in range(3, ws.max_row + 1) if str(ws.cell(r, 1).value).strip() == "B081")
    ws.cell(row, 2).value = new_kg                                      # the sheet's 23 Oct weight for B081
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


async def _kg(client, h, tag):
    ov = (await client.get("/api/v1/weights/overview", headers=h)).json()
    return next(a["current_kg"] for a in ov["animals"] if a["tag"] == tag)


async def test_corrections_versions_restore_and_unpost(client, engine):
    h = await _org(client, engine, "versions1@example.com")
    first = await _import(client, h, FIXTURE.read_bytes(), "v1.xlsx")
    assert first["version"]["version_no"] == 1
    old_kg = await _kg(client, h, "B081")

    again = await _import(client, h, FIXTURE.read_bytes(), "v1-again.xlsx")                # identical file: no new version
    assert again["version"]["new"] is False and again["updated"].get("weights_voided", 0) == 0

    fixed = await _import(client, h, _changed_workbook(old_kg + 31), "v2.xlsx")           # the sheet changed one weight
    assert fixed["version"]["version_no"] == 2
    assert fixed["updated"]["weights_voided"] == 1 and fixed["created"]["weight_records"] == 1
    assert await _kg(client, h, "B081") == old_kg + 31

    versions = (await client.get("/api/v1/feedlot/worksheet/versions", headers=h)).json()
    assert [v["version_no"] for v in versions] == [2, 1] and versions[0]["is_latest"] and versions[1]["has_file"]
    dl = await client.get(f"/api/v1/feedlot/worksheet/versions/{versions[1]['id']}/download", headers=h)
    assert dl.status_code == 200 and dl.content[:2] == b"PK"

    preview = (await client.post(f"/api/v1/feedlot/worksheet/versions/{versions[1]['id']}/restore?dry_run=true", headers=h)).json()
    assert preview["dry_run"] is True and await _kg(client, h, "B081") == old_kg + 31      # a preview saves nothing
    done = (await client.post(f"/api/v1/feedlot/worksheet/versions/{versions[1]['id']}/restore?dry_run=false", headers=h)).json()
    assert done["updated"]["weights_voided"] == 1 and done["updated"]["weights_restored"] == 1
    assert await _kg(client, h, "B081") == old_kg and done["version"]["version_no"] == 3

    no_confirm = await client.post("/api/v1/feedlot/worksheet/unpost?dry_run=false", headers=h)
    assert no_confirm.status_code == 422
    dry = (await client.post("/api/v1/feedlot/worksheet/unpost?dry_run=true", headers=h)).json()
    assert dry["updated"]["weights_voided"] > 100
    real = (await client.post("/api/v1/feedlot/worksheet/unpost?dry_run=false&confirm=UNPOST", headers=h)).json()
    assert real["updated"]["weights_voided"] == dry["updated"]["weights_voided"]
    back = (await client.post(f"/api/v1/feedlot/worksheet/versions/{versions[1]['id']}/restore?dry_run=false", headers=h)).json()
    assert back["updated"]["weights_restored"] > 100 and await _kg(client, h, "B081") == old_kg   # unpost is reversible


async def _moved_workbook() -> bytes:
    wb = openpyxl.load_workbook(io.BytesIO(FIXTURE.read_bytes()))
    ws6, ws5 = wb["BATCH 6"], wb["BATCH 5"]
    row = next(r for r in range(3, ws6.max_row + 1) if str(ws6.cell(r, 1).value).strip() == "B0102")
    tag_cells = [(ws6.cell(row, c).value) for c in (1, 2)]
    ws6.delete_rows(row)                                                # B0102 leaves batch 6 ...
    ws5.append(tag_cells)                                               # ... and is now listed under batch 5
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


async def test_a_tag_the_sheet_moved_to_another_batch_follows_the_sheet(client, engine):
    h = await _org(client, engine, "versions3@example.com")
    await _import(client, h, FIXTURE.read_bytes(), "v1.xlsx")
    rep = await _import(client, h, await _moved_workbook(), "moved.xlsx")
    assert rep["conflicts"] == [] and [m["tag"] for m in rep["moved"]] == ["B0102"]
    assert rep["moved"][0]["system_batch"] == 6 and rep["moved"][0]["sheet_batch"] == 5
    assert any(w["code"] == "animals_moved" for w in rep["warnings"])


async def test_a_tag_that_moved_to_another_batch_can_be_left_alone(client, engine):
    h = await _org(client, engine, "versions2@example.com")
    await _import(client, h, FIXTURE.read_bytes(), "v1.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(FIXTURE.read_bytes()))
    ws6, ws5 = wb["BATCH 6"], wb["BATCH 5"]
    row = next(r for r in range(3, ws6.max_row + 1) if str(ws6.cell(r, 1).value).strip() == "B0102")
    tag_cells = [(ws6.cell(row, c).value) for c in (1, 2)]
    ws6.delete_rows(row)                                                # B0102 leaves batch 6 ...
    ws5.append(tag_cells)                                               # ... and is now listed under batch 5
    buf = io.BytesIO(); wb.save(buf)
    r = await client.post("/api/v1/feedlot/worksheet/import?dry_run=false&move_batches=false", headers=h,
                          files={"file": ("moved.xlsx", io.BytesIO(buf.getvalue()), "application/octet-stream")})
    rep = r.json()
    assert [c["tag"] for c in rep["conflicts"]] == ["B0102"] and rep["conflicts"][0]["system_batch"] == 6
    assert any(w["code"] == "tag_batch_mismatch" for w in rep["warnings"])


async def test_finance_align_adds_adjusting_entries_once(client, engine):
    h = await _org(client, engine, "versions4@example.com")
    await _import(client, h, FIXTURE.read_bytes(), "v1.xlsx")
    await _import(client, h, await _moved_workbook(), "moved.xlsx")                       # B0102 now follows batch 5
    preview = (await client.post("/api/v1/feedlot/finance-align?dry_run=true", headers=h)).json()
    assert preview["dry_run"] is True and preview["entries"] >= 1 and any(i["tag"] == "B0102" for i in preview["items"])
    done = (await client.post("/api/v1/feedlot/finance-align?dry_run=false", headers=h)).json()
    assert done["entries"] == preview["entries"]
    again = (await client.post("/api/v1/feedlot/finance-align?dry_run=true", headers=h)).json()
    assert again["entries"] == 0                                                          # idempotent

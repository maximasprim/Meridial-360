"""Animal tags: where a scanned QR code lands and what the public tag page is told."""
import uuid

import pytest

from app.modules.livestock.service import animal_tag_url
from tests.test_platform_admin import _make_platform_admin, _platform_login
from tests.test_public_qr import _setup_animal

ANIMAL = uuid.UUID("b2c57022-631c-4b76-bf23-0bfe75937288")


def test_tag_url_uses_the_farms_verified_own_domain():
    url = animal_tag_url(base_url="https://terra-mus.vercel.app", org_slug="sahara", animal_id=ANIMAL,
                         custom_domain="saharaoasis.co.ke", domain_verified=True)
    assert url == f"https://saharaoasis.co.ke/tag/sahara/{ANIMAL}"


def test_tag_url_ignores_an_unverified_domain_and_falls_back_to_the_platform():
    for domain in ("saharaoasis.co.ke", None, "", "  "):
        url = animal_tag_url(base_url="https://terra-mus.vercel.app/", org_slug="sahara", animal_id=ANIMAL,
                             custom_domain=domain, domain_verified=False)
        assert url == f"https://terra-mus.vercel.app/tag/sahara/{ANIMAL}"  # trailing slash tidied, no double slash
    # a verified flag with no domain must not produce "https:///tag/..."
    assert animal_tag_url(base_url="https://x.test", org_slug="s", animal_id=ANIMAL, custom_domain=None,
                          domain_verified=True) == f"https://x.test/tag/s/{ANIMAL}"


@pytest.mark.asyncio
async def test_qr_profile_carries_the_farms_identity_and_follows_the_store_switch(client, engine):
    _, org_slug, animal_id, listing_slug = await _setup_animal(client, "Tag Farm", "tagfarm@example.com")
    url = f"/api/v1/public/{org_slug}/animals/{animal_id}/qr-profile"

    body = (await client.get(url)).json()
    assert body["organization_name"] == "Tag Farm" and body["shop_enabled"] is True
    assert body["is_for_sale"] is True and body["listing_slug"] == listing_slug
    assert "acquisition_cost" not in body

    # switch the farm's public store off: the tag still resolves, but nothing is publicly for sale and the page won't link to the shop
    await _make_platform_admin(engine)
    headers = {"Authorization": f"Bearer {await _platform_login(client)}"}
    orgs = (await client.get("/api/v1/platform/organizations", headers=headers)).json()
    org_id = next(o["id"] for o in orgs if o["name"] == "Tag Farm")
    r = await client.patch(f"/api/v1/platform/organizations/{org_id}/public-store", json={"mode": "off"}, headers=headers)
    assert r.status_code == 200, r.text

    resp = await client.get(url)
    assert resp.status_code == 200
    body = resp.json()
    assert body["shop_enabled"] is False and body["is_for_sale"] is False and body["listing_slug"] is None
    assert body["organization_name"] == "Tag Farm" and body["animal_number"] == "QRPUB-COW"


# ----------------------------------------------------------------------- photo, weight, date of birth --
import io  # noqa: E402

from PIL import Image  # noqa: E402


def _photo() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (120, 80, 40)).save(buf, "PNG")
    return buf.getvalue()


async def _animal_with_details(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner", "email": email, "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    org_slug = (await client.get("/api/v1/auth/me", headers=headers)).json()["organization"]["slug"]
    farm = (await client.post("/api/v1/farms", json={"name": "Main Farm"}, headers=headers)).json()
    animal = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm["id"], "animal_number": "TAG-DET-1", "species": "cattle", "breed": "Boran", "sex": "male",
        "date_of_birth": "2023-03-12", "current_weight": "258",
        "acquisition_date": "2024-01-01", "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    assert animal.status_code == 201, animal.text
    animal_id = animal.json()["id"]
    up = await client.put(f"/api/v1/livestock/{animal_id}/photo", headers=headers, files={"file": ("a.png", _photo(), "image/png")})
    assert up.status_code == 200, up.text
    return headers, org_slug, animal_id


@pytest.mark.asyncio
async def test_tag_page_shows_photo_weight_and_birth_date_by_default(client):
    headers, org_slug, animal_id = await _animal_with_details(client, "Detail Farm", "detailfarm@example.com")
    body = (await client.get(f"/api/v1/public/{org_slug}/animals/{animal_id}/qr-profile")).json()
    assert body["date_of_birth"] == "2023-03-12"
    assert float(body["current_weight"]) == 258.0
    assert body["photo_url"].startswith(f"/api/v1/public/{org_slug}/animals/{animal_id}/photo?v=")
    assert "acquisition_cost" not in body

    photo = await client.get(body["photo_url"])
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(photo.content)).size == (60, 40)

    # another farm's address can never serve this animal's photo
    other = await _animal_with_details(client, "Other Detail Farm", "otherdetail@example.com")
    assert (await client.get(f"/api/v1/public/{other[1]}/animals/{animal_id}/photo")).status_code == 404


@pytest.mark.asyncio
async def test_farm_can_switch_each_tag_detail_off(client):
    headers, org_slug, animal_id = await _animal_with_details(client, "Private Farm", "privatefarm@example.com")
    url = f"/api/v1/public/{org_slug}/animals/{animal_id}/qr-profile"

    r = await client.put("/api/v1/cms/profile", headers=headers, json={"farm_name": "Private Farm", "tag_show_weight": False})
    assert r.status_code == 200, r.text
    assert r.json()["tag_show_weight"] is False and r.json()["tag_show_photo"] is True
    body = (await client.get(url)).json()
    assert body["current_weight"] is None and body["photo_url"] and body["date_of_birth"] == "2023-03-12"  # independent switches

    r = await client.put("/api/v1/cms/profile", headers=headers, json={"tag_show_photo": False, "tag_show_birth_date": False})
    assert r.status_code == 200, r.text
    body = (await client.get(url)).json()
    assert body["photo_url"] is None and body["date_of_birth"] is None and body["current_weight"] is None
    assert (await client.get(f"/api/v1/public/{org_slug}/animals/{animal_id}/photo")).status_code == 404  # photo not reachable by guessing

    # the basics always show
    assert body["animal_number"] == "TAG-DET-1" and body["species"] == "cattle"
    # a switch can't be set to null
    assert (await client.put("/api/v1/cms/profile", headers=headers, json={"tag_show_photo": None})).status_code == 422


@pytest.mark.asyncio
async def test_tag_photo_still_works_while_the_public_store_is_off(client, engine):
    headers, org_slug, animal_id = await _animal_with_details(client, "Store Off Farm", "storeoff@example.com")
    await _make_platform_admin(engine)
    admin = {"Authorization": f"Bearer {await _platform_login(client)}"}
    orgs = (await client.get("/api/v1/platform/organizations", headers=admin)).json()
    org_id = next(o["id"] for o in orgs if o["name"] == "Store Off Farm")
    await client.patch(f"/api/v1/platform/organizations/{org_id}/public-store", json={"mode": "off"}, headers=admin)

    assert (await client.get(f"/api/v1/public/{org_slug}/profile")).status_code == 403  # the shop is closed
    assert (await client.get(f"/api/v1/public/{org_slug}/animals/{animal_id}/photo")).status_code == 200  # the tag is not

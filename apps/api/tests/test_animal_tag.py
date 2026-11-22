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

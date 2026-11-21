"""Billing-package management and the public-store switch (package rule + per-tenant superadmin override).

Covered:
  * every existing tenant keeps a working public store by default
  * a superadmin can create / edit packages; the free package is protected; viewers can read but not write
  * turning the public store off on a package switches it off for tenants on that package
  * a per-tenant override ('on' / 'off') beats the package; 'package' hands the decision back
  * only the public storefront stops - the tenant's own authenticated system keeps working
  * the animal QR-tag page is not part of the store and keeps resolving
  * the change is written to the shared audit log
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.test_platform_admin import _make_platform_admin, _platform_login, _register_org

pytestmark = pytest.mark.asyncio


async def _setup(client, engine, name="Store Farm", email="store@example.com"):
    await _make_platform_admin(engine)
    tenant = await _register_org(client, name, email)
    token = await _platform_login(client)
    headers = {"Authorization": f"Bearer {token}"}
    orgs = await client.get("/api/v1/platform/organizations", headers=headers)
    org = next(o for o in orgs.json() if o["name"] == name)
    tenant_headers = {"Authorization": f"Bearer {tenant['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=tenant_headers)).json()
    return org["id"], me["organization"]["slug"], headers, tenant_headers


def _store_url(org_id):
    return f"/api/v1/platform/organizations/{org_id}/public-store"


async def _free_package(client, headers):
    packages = (await client.get("/api/v1/platform/billing/packages", headers=headers)).json()
    return next(p for p in packages if p["slug"] == "free")


async def test_default_every_package_includes_the_public_store(client, engine):
    org_id, slug, headers, _ = await _setup(client, engine)

    packages = (await client.get("/api/v1/platform/billing/packages", headers=headers)).json()
    assert {"free", "basic", "pro", "enterprise"} <= {p["slug"] for p in packages}
    assert all(p["public_store_included"] is True for p in packages)

    status = (await client.get(_store_url(org_id), headers=headers)).json()
    assert status["enabled"] is True and status["mode"] == "package"
    assert (await client.get(f"/api/v1/public/{slug}/profile")).status_code == 200


async def test_package_without_public_store_switches_it_off_for_its_tenants(client, engine):
    org_id, slug, headers, tenant_headers = await _setup(client, engine)
    free = await _free_package(client, headers)

    r = await client.patch(f"/api/v1/platform/billing/packages/{free['id']}", json={"public_store_included": False}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["public_store_included"] is False

    # a tenant that was never looked at by billing is on the free package, so it is affected too
    assert (await client.get(f"/api/v1/public/{slug}/profile")).status_code == 403
    assert (await client.get(f"/api/v1/public/{slug}/listings")).status_code == 403
    status = (await client.get(_store_url(org_id), headers=headers)).json()
    assert status["enabled"] is False and status["package_allows"] is False and status["mode"] == "package"

    # the tenant's own system is untouched
    assert (await client.get("/api/v1/auth/me", headers=tenant_headers)).status_code == 200
    assert (await client.get("/api/v1/cms/profile", headers=tenant_headers)).status_code == 200

    # moving the tenant to a package that includes the store turns it back on
    r = await client.patch(f"/api/v1/platform/organizations/{org_id}/subscription", json={"tier_slug": "basic"}, headers=headers)
    assert r.status_code == 200, r.text
    assert (await client.get(f"/api/v1/public/{slug}/profile")).status_code == 200


async def test_tenant_override_beats_the_package_and_can_be_handed_back(client, engine):
    org_id, slug, headers, _ = await _setup(client, engine)

    r = await client.patch(_store_url(org_id), json={"mode": "off", "reason": "unpaid"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "off" and r.json()["enabled"] is False
    assert (await client.get(f"/api/v1/public/{slug}/profile")).status_code == 403

    # package says no, override says yes -> on
    free = await _free_package(client, headers)
    await client.patch(f"/api/v1/platform/billing/packages/{free['id']}", json={"public_store_included": False}, headers=headers)
    r = await client.patch(_store_url(org_id), json={"mode": "on"}, headers=headers)
    assert r.json()["mode"] == "on" and r.json()["enabled"] is True
    assert (await client.get(f"/api/v1/public/{slug}/profile")).status_code == 200

    # back to following the package (which says no)
    r = await client.patch(_store_url(org_id), json={"mode": "package"}, headers=headers)
    assert r.json()["mode"] == "package" and r.json()["enabled"] is False
    assert (await client.get(f"/api/v1/public/{slug}/profile")).status_code == 403

    assert (await client.patch(_store_url(org_id), json={"mode": "sometimes"}, headers=headers)).status_code == 422
    assert (await client.patch(_store_url(uuid.uuid4()), json={"mode": "on"}, headers=headers)).status_code == 404


async def test_override_is_per_tenant(client, engine):
    org_a, slug_a, headers, _ = await _setup(client, engine, "Store A", "storea@example.com")
    await _register_org(client, "Store B", "storeb@example.com")
    orgs = (await client.get("/api/v1/platform/organizations", headers=headers)).json()
    slug_b = next(o["slug"] for o in orgs if o["name"] == "Store B")

    await client.patch(_store_url(org_a), json={"mode": "off"}, headers=headers)
    assert (await client.get(f"/api/v1/public/{slug_a}/profile")).status_code == 403
    assert (await client.get(f"/api/v1/public/{slug_b}/profile")).status_code == 200


async def test_qr_tag_page_is_not_part_of_the_store(client, engine):
    org_id, slug, headers, _ = await _setup(client, engine)
    await client.patch(_store_url(org_id), json={"mode": "off"}, headers=headers)
    r = await client.get(f"/api/v1/public/{slug}/animals/{uuid.uuid4()}/qr-profile")
    assert r.status_code != 403  # unknown animal -> 404, but never the store-unavailable 403


async def test_public_store_change_is_audited(client, engine):
    from app.modules.identity.models import AuditLog

    org_id, _, headers, _ = await _setup(client, engine)
    await client.patch(_store_url(org_id), json={"mode": "off", "reason": "plan lapsed"}, headers=headers)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.organization_id == uuid.UUID(org_id), AuditLog.action == "organization.public_store_change")
        )).scalars().all()
    assert len(rows) == 1  # self-audited, not logged a second time by the generic middleware
    assert rows[0].new_value["mode"] == "off" and rows[0].new_value["enabled"] is False


async def test_create_and_edit_packages(client, engine):
    _, _, headers, _ = await _setup(client, engine)

    r = await client.post("/api/v1/platform/billing/packages", headers=headers, json={
        "name": "Starter Plus", "slug": "Starter-Plus", "monthly_price_kes": 2500,
        "max_users": 8, "max_animals": 300, "max_crop_plantings": None, "public_store_included": False,
    })
    assert r.status_code == 201, r.text
    pkg = r.json()
    assert pkg["slug"] == "starter-plus" and pkg["max_crop_plantings"] is None
    assert pkg["public_store_included"] is False and pkg["organization_count"] == 0

    dup = await client.post("/api/v1/platform/billing/packages", headers=headers, json={
        "name": "Again", "slug": "starter-plus", "monthly_price_kes": 1,
    })
    assert dup.status_code == 409

    # omitted = unchanged; explicit null on a limit = unlimited
    r = await client.patch(f"/api/v1/platform/billing/packages/{pkg['id']}", headers=headers, json={"monthly_price_kes": 3000, "max_users": None})
    assert r.status_code == 200, r.text
    assert r.json()["monthly_price_kes"] == 3000 and r.json()["max_users"] is None and r.json()["max_animals"] == 300

    assert (await client.patch(f"/api/v1/platform/billing/packages/{pkg['id']}", headers=headers, json={"name": None})).status_code == 422
    assert (await client.patch(f"/api/v1/platform/billing/packages/{uuid.uuid4()}", headers=headers, json={"name": "x"})).status_code == 404

    # switched off = no longer offered to tenants, but still listed for the superadmin
    await client.patch(f"/api/v1/platform/billing/packages/{pkg['id']}", headers=headers, json={"is_active": False})
    offered = (await client.get("/api/v1/billing/tiers")).json()
    assert "starter-plus" not in {t["slug"] for t in offered}
    listed = (await client.get("/api/v1/platform/billing/packages", headers=headers)).json()
    assert "starter-plus" in {p["slug"] for p in listed}


async def test_free_package_is_protected(client, engine):
    _, _, headers, _ = await _setup(client, engine)
    free = await _free_package(client, headers)
    url = f"/api/v1/platform/billing/packages/{free['id']}"
    assert (await client.patch(url, json={"is_active": False}, headers=headers)).status_code == 409
    assert (await client.patch(url, json={"monthly_price_kes": 500}, headers=headers)).status_code == 422
    assert (await client.patch(url, json={"max_animals": 40}, headers=headers)).status_code == 200


async def test_viewer_can_read_but_not_write_packages_or_store(client, engine):
    org_id, _, headers, _ = await _setup(client, engine)
    await client.post("/api/v1/platform/admins", json={
        "email": "viewer@platform.example.com", "full_name": "Viewer", "password": "viewerpass123", "role": "viewer",
    }, headers=headers)
    login = await client.post("/api/v1/platform/auth/login", data={"username": "viewer@platform.example.com", "password": "viewerpass123"})
    viewer = {"Authorization": f"Bearer {login.json()['access_token']}"}
    free = await _free_package(client, headers)

    assert (await client.get("/api/v1/platform/billing/packages", headers=viewer)).status_code == 200
    assert (await client.get(_store_url(org_id), headers=viewer)).status_code == 200
    assert (await client.post("/api/v1/platform/billing/packages", headers=viewer, json={"name": "X", "slug": "xx", "monthly_price_kes": 1})).status_code == 403
    assert (await client.patch(f"/api/v1/platform/billing/packages/{free['id']}", headers=viewer, json={"max_users": 3})).status_code == 403
    assert (await client.patch(_store_url(org_id), json={"mode": "off"}, headers=viewer)).status_code == 403


async def test_tenant_token_cannot_reach_package_or_store_routes(client, engine):
    org_id, _, _, tenant_headers = await _setup(client, engine)
    assert (await client.get("/api/v1/platform/billing/packages", headers=tenant_headers)).status_code in (401, 403)
    assert (await client.patch(_store_url(org_id), json={"mode": "off"}, headers=tenant_headers)).status_code in (401, 403)


async def test_tenant_is_told_why_its_store_is_off(client, engine):
    org_id, slug, headers, tenant_headers = await _setup(client, engine)
    url = "/api/v1/billing/public-store"

    r = await client.get(url, headers=tenant_headers)
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True and r.json()["reason"] is None

    free = await _free_package(client, headers)
    await client.patch(f"/api/v1/platform/billing/packages/{free['id']}", json={"public_store_included": False}, headers=headers)
    r = await client.get(url, headers=tenant_headers)
    assert r.json()["enabled"] is False and r.json()["reason"] == "package"

    await client.patch(_store_url(org_id), json={"mode": "off"}, headers=headers)
    assert (await client.get(url, headers=tenant_headers)).json()["reason"] == "admin"

    await client.patch(_store_url(org_id), json={"mode": "on"}, headers=headers)
    r = await client.get(url, headers=tenant_headers)
    assert r.json()["enabled"] is True and r.json()["reason"] is None

    assert (await client.get(url)).status_code in (401, 403)  # needs a signed-in tenant user


async def test_store_status_endpoint_is_public_and_always_200(client, engine):
    org_id, slug, headers, _ = await _setup(client, engine)
    r = await client.get(f"/api/v1/public/{slug}/store-status")
    assert r.status_code == 200 and r.json() == {"enabled": True}

    await client.patch(_store_url(org_id), json={"mode": "off"}, headers=headers)
    r = await client.get(f"/api/v1/public/{slug}/store-status")
    assert r.status_code == 200 and r.json() == {"enabled": False}  # 200, not the 403 other public routes give

    assert (await client.get("/api/v1/public/no-such-farm/store-status")).status_code == 404

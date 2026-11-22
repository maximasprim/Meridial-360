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


# ------------------------------------------------------------------ app / sign-in branding --
import io  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

LOGO_BG = (30, 120, 60)


def _logo_png() -> bytes:
    """A wide logo: a white disc on a plain green background (so the icon's fill should come out green)."""
    img = Image.new("RGB", (400, 200), LOGO_BG)
    ImageDraw.Draw(img).ellipse([130, 30, 270, 170], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _branding_url(org_id):
    return f"/api/v1/platform/organizations/{org_id}/app-branding"


def _package_url(package_id):
    return f"/api/v1/platform/billing/packages/{package_id}"


async def _upload_logo(client, tenant_headers):
    up = await client.post("/api/v1/cms/images?kind=logo", headers=tenant_headers, files={"file": ("logo.png", _logo_png(), "image/png")})
    assert up.status_code == 201, up.text
    image_id = up.json()["id"]
    r = await client.put("/api/v1/cms/profile", headers=tenant_headers, json={
        "farm_name": "Branded Farm", "logo_url": f"http://localhost:8000/api/v1/media/site-images/{image_id}",
    })
    assert r.status_code == 200, r.text


async def test_branding_defaults_to_platform_and_reveals_nothing(client, engine):
    org_id, slug, headers, tenant_headers = await _setup(client, engine)
    await _upload_logo(client, tenant_headers)

    status = (await client.get(_branding_url(org_id), headers=headers)).json()
    for surface in ("staff", "shop"):
        assert status[surface] == {"mode": "package", "enabled": False, "package_allows": False}  # nothing included anywhere yet
    assert status["has_logo"] is True and status["has_icon"] is True

    public = (await client.get(f"/api/v1/public/{slug}/branding")).json()
    assert public["staff_branding"] is False and public["shop_branding"] is False
    assert public["farm_name"] is None and public["logo_url"] is None  # nothing exposed while on platform branding
    assert (await client.get(f"/api/v1/public/{slug}/app-icon/192.png")).status_code == 404
    assert (await client.get(f"/api/v1/public/{slug}/store-status")).json()["shop_branding"] is False
    assert (await client.get("/api/v1/public/no-such-farm/branding")).status_code == 404


async def test_packages_carry_the_two_branding_benefits(client, engine):
    org_id, slug, headers, tenant_headers = await _setup(client, engine)
    packages = (await client.get("/api/v1/platform/billing/packages", headers=headers)).json()
    assert all(p["staff_branding_included"] is False and p["shop_branding_included"] is False for p in packages)

    r = await client.post("/api/v1/platform/billing/packages", headers=headers, json={
        "name": "Brand Pro", "slug": "brand-pro", "monthly_price_kes": 5000,
        "staff_branding_included": True, "shop_branding_included": True,
    })
    assert r.status_code == 201, r.text
    assert r.json()["staff_branding_included"] is True and r.json()["shop_branding_included"] is True

    # the two benefits are independent and an explicit null is rejected like the other required flags
    pid = r.json()["id"]
    r = await client.patch(_package_url(pid), json={"staff_branding_included": False}, headers=headers)
    assert r.json()["staff_branding_included"] is False and r.json()["shop_branding_included"] is True
    assert (await client.patch(_package_url(pid), json={"shop_branding_included": None}, headers=headers)).status_code == 422

    # tenants see the benefits on the plans they can choose
    offered = {t["slug"]: t for t in (await client.get("/api/v1/billing/tiers")).json()}
    assert offered["brand-pro"]["shop_branding_included"] is True and offered["brand-pro"]["staff_branding_included"] is False
    assert offered["free"]["shop_branding_included"] is False


async def test_branding_follows_the_package_and_each_surface_is_independent(client, engine):
    org_id, slug, headers, tenant_headers = await _setup(client, engine)
    await _upload_logo(client, tenant_headers)
    free = await _free_package(client, headers)

    # tick only the shop benefit on the package the farm is on (free, since it was never changed)
    await client.patch(_package_url(free["id"]), json={"shop_branding_included": True}, headers=headers)
    status = (await client.get(_branding_url(org_id), headers=headers)).json()
    assert status["shop"] == {"mode": "package", "enabled": True, "package_allows": True}
    assert status["staff"] == {"mode": "package", "enabled": False, "package_allows": False}
    public = (await client.get(f"/api/v1/public/{slug}/branding")).json()
    assert public["shop_branding"] is True and public["staff_branding"] is False and public["farm_name"] == "Branded Farm"
    store = (await client.get(f"/api/v1/public/{slug}/store-status")).json()
    assert store["shop_branding"] is True and store["has_icon"] is True and store["icon_version"]

    # then the staff benefit too
    await client.patch(_package_url(free["id"]), json={"staff_branding_included": True}, headers=headers)
    assert (await client.get(f"/api/v1/public/{slug}/branding")).json()["staff_branding"] is True

    # moving the farm to a package without either benefit switches both off again
    r = await client.patch(f"/api/v1/platform/organizations/{org_id}/subscription", json={"tier_slug": "basic"}, headers=headers)
    assert r.status_code == 200, r.text
    public = (await client.get(f"/api/v1/public/{slug}/branding")).json()
    assert public["staff_branding"] is False and public["shop_branding"] is False and public["farm_name"] is None


async def test_farm_override_beats_the_package_and_can_be_handed_back(client, engine):
    org_id, slug, headers, tenant_headers = await _setup(client, engine)
    await _upload_logo(client, tenant_headers)
    free = await _free_package(client, headers)

    # package says no, override says yes -> on (only for the surface that was overridden)
    r = await client.patch(_branding_url(org_id), json={"staff": "on"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["staff"] == {"mode": "on", "enabled": True, "package_allows": False}
    assert r.json()["shop"]["mode"] == "package" and r.json()["shop"]["enabled"] is False
    public = (await client.get(f"/api/v1/public/{slug}/branding")).json()
    assert public["staff_branding"] is True and public["shop_branding"] is False

    # package says yes, override says no -> off
    await client.patch(_package_url(free["id"]), json={"shop_branding_included": True}, headers=headers)
    r = await client.patch(_branding_url(org_id), json={"shop": "off"}, headers=headers)
    assert r.json()["shop"] == {"mode": "off", "enabled": False, "package_allows": True}
    assert (await client.get(f"/api/v1/public/{slug}/store-status")).json()["shop_branding"] is False

    # hand both back to the package
    r = await client.patch(_branding_url(org_id), json={"staff": "package", "shop": "package"}, headers=headers)
    assert r.json()["staff"]["mode"] == "package" and r.json()["staff"]["enabled"] is False
    assert r.json()["shop"]["mode"] == "package" and r.json()["shop"]["enabled"] is True

    assert (await client.patch(_branding_url(org_id), json={"staff": True}, headers=headers)).status_code == 422  # modes, not booleans


async def test_app_icons_are_the_full_family_made_from_the_logo(client, engine):
    org_id, slug, headers, tenant_headers = await _setup(client, engine)
    await _upload_logo(client, tenant_headers)
    await client.patch(_branding_url(org_id), json={"staff": "on"}, headers=headers)

    expected = {
        "192.png": (192, "any"), "256.png": (256, "any"), "384.png": (384, "any"), "512.png": (512, "any"),
        "maskable-192.png": (192, "maskable"), "maskable-512.png": (512, "maskable"),
        "apple-180.png": (180, "apple"), "favicon-32.png": (32, "favicon"),
    }
    for name, (size, kind) in expected.items():
        r = await client.get(f"/api/v1/public/{slug}/app-icon/{name}")
        assert r.status_code == 200, (name, r.text)
        assert r.headers["content-type"] == "image/png"
        icon = Image.open(io.BytesIO(r.content))
        assert icon.size == (size, size), name
        rgba = icon.convert("RGBA")
        assert rgba.getpixel((size // 2, size // 2))[:3] == (255, 255, 255), name  # the logo's white disc sits in the middle
        if kind in ("any", "favicon"):
            assert rgba.getpixel((0, 0))[3] == 0, name  # rounded square: transparent corners, like the platform icon
        else:
            assert rgba.getpixel((0, 0)) == (*LOGO_BG, 255), name  # full-bleed square in the logo's own background colour
        if size >= 180:
            assert rgba.getpixel((size // 2, 4))[:3] == LOGO_BG, name  # the fill is the logo's edge colour, so no box shows

    for bad in ("64.png", "maskable-256.png", "apple-192.png", "192.jpg"):
        assert (await client.get(f"/api/v1/public/{slug}/app-icon/{bad}")).status_code == 422  # only the family above exists


async def test_branding_without_an_uploaded_logo_has_no_icon_and_falls_back(client, engine):
    org_id, slug, headers, _ = await _setup(client, engine)
    await client.patch(_branding_url(org_id), json={"staff": "on", "shop": "on"}, headers=headers)
    public = (await client.get(f"/api/v1/public/{slug}/branding")).json()
    assert public["staff_branding"] is True and public["farm_name"] and public["has_icon"] is False
    assert (await client.get(f"/api/v1/public/{slug}/app-icon/192.png")).status_code == 404  # web app uses the platform icon


async def test_branding_works_while_the_public_store_is_off(client, engine):
    org_id, slug, headers, _ = await _setup(client, engine)
    await client.patch(_branding_url(org_id), json={"staff": "on"}, headers=headers)
    await client.patch(_store_url(org_id), json={"mode": "off"}, headers=headers)
    assert (await client.get(f"/api/v1/public/{slug}/profile")).status_code == 403
    assert (await client.get(f"/api/v1/public/{slug}/branding")).status_code == 200  # the sign-in page still brands itself


async def test_app_branding_change_is_audited_and_permissioned(client, engine):
    from app.modules.identity.models import AuditLog

    org_id, _, headers, tenant_headers = await _setup(client, engine)
    await client.patch(_branding_url(org_id), json={"staff": "on"}, headers=headers)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.organization_id == uuid.UUID(org_id), AuditLog.action == "organization.app_branding_change")
        )).scalars().all()
    assert len(rows) == 1
    assert rows[0].previous_value == {"staff": "package", "shop": "package"}
    assert rows[0].new_value == {"staff": "on", "shop": "package"}

    assert (await client.get(_branding_url(org_id), headers=tenant_headers)).status_code in (401, 403)
    assert (await client.patch(_branding_url(org_id), json={"staff": "on"}, headers=tenant_headers)).status_code in (401, 403)
    assert (await client.patch(_branding_url(uuid.uuid4()), json={"staff": "on"}, headers=headers)).status_code == 404

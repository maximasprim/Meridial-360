"""Tenant branding for the installed apps and the sign-in page.

A superadmin decides, per tenant and separately for the STAFF app and the PUBLIC SHOP, whether the installed app
(name + home-screen icon) and, for staff, the sign-in page show the platform's identity or the farm's own name and
logo (tenant_catalog_settings.staff_branding_tenant / shop_branding_tenant, both False by default).

  * get_branding   - what the web app needs to brand itself. Reveals the farm's name/logo only when at least one of
                     the two switches is on, so a tenant left on platform branding exposes nothing new here.
  * get_app_icon_png - the farm's logo turned into the whole icon family an installed app needs (rounded-square icons at
                     192/256/384/512, full-bleed maskable icons, the iOS home-screen icon and a browser-tab favicon).
                     Only logos WE stored are used (never an arbitrary pasted URL, so the server never fetches a
                     address a tenant chose); otherwise the web app falls back to the platform icon.
"""
import asyncio
import io
import uuid
from typing import NamedTuple

import httpx
from fastapi import HTTPException, status
from PIL import Image, ImageDraw, ImageOps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import TenantCatalogSettings
from app.modules.cms.models import FarmProfile, SiteImage
from app.modules.cms.site_images import get_image_source, image_id_from_url
from app.modules.identity.models import Organization
from app.modules.public import schemas

# Every icon an installed app, a home screen or a browser tab asks for: name -> (pixels, kind).
#   any       rounded square with transparent corners (Chrome / Edge / Windows / desktop shortcuts), like the platform's own icon
#   maskable  full-bleed square; Android crops it to a circle / squircle, so the logo stays in the safe middle
#   apple     full-bleed opaque square for iOS "Add to Home Screen" (iOS rounds it itself and paints transparency black)
#   favicon   small rounded square for the browser tab, logo kept large so it stays readable
ICON_SPECS = {
    "192.png": (192, "any"),
    "256.png": (256, "any"),
    "384.png": (384, "any"),
    "512.png": (512, "any"),
    "maskable-192.png": (192, "maskable"),
    "maskable-512.png": (512, "maskable"),
    "apple-180.png": (180, "apple"),
    "favicon-32.png": (32, "favicon"),
}
_LOGO_SHARE = {"any": 0.68, "maskable": 0.56, "apple": 0.66, "favicon": 0.84}  # logo box as a share of the icon
_CORNER = {"any": 0.225, "favicon": 0.2}  # corner radius as a share of the icon; kinds not listed stay square
MAX_LOGO_BYTES = 5 * 1024 * 1024
_ICON_CACHE: dict[tuple[str, str], bytes] = {}
_ICON_CACHE_MAX = 128


class LogoInfo(NamedTuple):
    logo_url: str | None
    image_id: uuid.UUID | None  # set only when the logo is an uploaded image we hold (so an icon can be made from it)


async def get_flags(db: AsyncSession, org_id: uuid.UUID) -> tuple[bool, bool]:
    """(staff_branding_tenant, shop_branding_tenant); (False, False) when the tenant was never configured."""
    row = (await db.execute(
        select(TenantCatalogSettings.staff_branding_tenant, TenantCatalogSettings.shop_branding_tenant)
        .where(TenantCatalogSettings.organization_id == org_id)
    )).first()
    return (bool(row[0]), bool(row[1])) if row else (False, False)


async def farm_name_and_logo(db: AsyncSession, org: Organization) -> tuple[str, LogoInfo]:
    """Read-only (a public request must not create rows)."""
    profile = (await db.execute(select(FarmProfile).where(FarmProfile.organization_id == org.id))).scalar_one_or_none()
    name = (profile.farm_name if profile and profile.farm_name else None) or org.name
    logo_url = profile.logo_url if profile else None
    image_id = image_id_from_url(logo_url)
    if image_id is not None:
        owned = (await db.execute(
            select(SiteImage.id).where(SiteImage.id == image_id, SiteImage.organization_id == org.id)
        )).first()
        image_id = image_id if owned else None
    return name, LogoInfo(logo_url, image_id)


async def _org(db: AsyncSession, org_slug: str) -> Organization:
    org = (await db.execute(select(Organization).where(Organization.slug == org_slug))).scalar_one_or_none()
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Farm not found")
    return org


async def get_branding(db: AsyncSession, org_slug: str) -> schemas.BrandingOut:
    org = await _org(db, org_slug)
    staff, shop = await get_flags(db, org.id)
    if not (staff or shop):
        return schemas.BrandingOut(staff_branding=False, shop_branding=False)
    name, logo = await farm_name_and_logo(db, org)
    return schemas.BrandingOut(
        staff_branding=staff, shop_branding=shop, farm_name=name, logo_url=logo.logo_url,
        has_icon=logo.image_id is not None, icon_version=logo.image_id.hex[:8] if logo.image_id else None,
    )


async def _logo_bytes(db: AsyncSession, image_id: uuid.UUID) -> bytes | None:
    try:
        source = await get_image_source(db, image_id)
    except HTTPException:
        return None
    if source.data is not None:
        return source.data
    if source.redirect_url:  # stored in our own bucket: fetch it from the CDN address WE built from our settings
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(source.redirect_url)
            if resp.status_code == 200 and len(resp.content) <= MAX_LOGO_BYTES:
                return resp.content
        except httpx.HTTPError:
            return None
    return None


def _background_for(rgb: Image.Image) -> tuple[int, int, int]:
    """The icon's fill: the logo's own edge colour, so a logo that sits on a plain background (as uploaded logos usually
    do) blends into the icon instead of showing up as a box. A busy edge falls back to white."""
    small = rgb.copy()
    small.thumbnail((256, 256))
    w, h = small.size
    band = max(1, min(w, h) // 25)
    strips = (
        small.crop((0, 0, w, band)), small.crop((0, h - band, w, h)),
        small.crop((0, band, band, h - band)), small.crop((w - band, band, w, h - band)),
    )
    channels: list[list[int]] = [[], [], []]
    for strip in strips:
        for px in strip.getdata():
            for i in range(3):
                channels[i].append(px[i])
    median, spread = [], 0
    for values in channels:
        values.sort()
        n = len(values)
        median.append(values[n // 2])
        spread = max(spread, values[int(n * 0.9)] - values[int(n * 0.1)])
    return (255, 255, 255) if spread > 40 else (median[0], median[1], median[2])


def render_app_icon(logo: bytes, size: int, kind: str) -> bytes:
    """One icon of the family above, built from the farm's logo: the logo fitted inside the safe area (never cropped or
    stretched) on its own background colour, then shaped for `kind`."""
    with Image.open(io.BytesIO(logo)) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGBA")
    flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
    flat.alpha_composite(img)  # a logo with transparency is shown on white
    rgb = flat.convert("RGB")
    bg = _background_for(rgb)

    box = max(1, int(size * _LOGO_SHARE[kind]))
    fitted = ImageOps.contain(rgb, (box, box), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), bg)
    canvas.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))

    corner = _CORNER.get(kind)
    if corner is None:
        out = canvas  # full-bleed square: the platform (Android / iOS) applies its own mask
    else:
        radius = int(size * corner)
        if sum(bg) / 3 > 200:  # a light icon would vanish on a light desktop, so give it a hairline edge
            edge = tuple(int(c * 0.88) for c in bg)
            ImageDraw.Draw(canvas).rounded_rectangle(
                [0, 0, size - 1, size - 1], radius=radius, outline=edge, width=max(1, size // 128)
            )
        oversample = 4  # smooth corners: draw the mask large, then shrink it
        mask = Image.new("L", (size * oversample, size * oversample), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, size * oversample - 1, size * oversample - 1], radius=radius * oversample, fill=255
        )
        out = canvas.convert("RGBA")
        out.putalpha(mask.resize((size, size), Image.BOX))  # box average: exact 0 / 255 away from the curve, no ringing

    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


async def get_app_icon_png(db: AsyncSession, org_slug: str, icon_name: str) -> bytes:
    if icon_name not in ICON_SPECS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown icon")
    org = await _org(db, org_slug)
    staff, shop = await get_flags(db, org.id)
    if not (staff or shop):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No branded icon")
    _, logo = await farm_name_and_logo(db, org)
    if logo.image_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No branded icon")
    key = (logo.image_id.hex, icon_name)  # a new logo is a new image id, so a replaced logo never serves a stale icon
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    raw = await _logo_bytes(db, logo.image_id)
    if raw is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No branded icon")
    size, kind = ICON_SPECS[icon_name]
    try:
        png = await asyncio.to_thread(render_app_icon, raw, size, kind)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No branded icon")
    if len(_ICON_CACHE) >= _ICON_CACHE_MAX:
        _ICON_CACHE.pop(next(iter(_ICON_CACHE)))
    _ICON_CACHE[key] = png
    return png

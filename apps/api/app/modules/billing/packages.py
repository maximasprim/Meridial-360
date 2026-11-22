"""Superadmin management of billing packages (the rows of subscription_tiers): list, create, edit.

Additive: billing/service.py is untouched. Rules that keep existing behaviour safe:
  * a package's slug is its stable identifier and never changes after creation;
  * packages are never deleted - one is switched off (is_active=False) so it is no longer offered, while tenants
    already on it keep working;
  * the 'free' package is where every new tenant starts, so it can't be switched off and must stay at price 0.
Editing a price or a limit affects what is charged / allowed from then on; existing paid periods are not touched.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing import schemas
from app.modules.billing.models import Subscription, SubscriptionTier
from app.modules.billing.service import ensure_default_tiers


def _out(tier: SubscriptionTier, counts: dict[uuid.UUID, int]) -> schemas.PackageOut:
    return schemas.PackageOut(
        id=tier.id, name=tier.name, slug=tier.slug, monthly_price_kes=float(tier.monthly_price_kes),
        max_users=tier.max_users, max_animals=tier.max_animals, max_crop_plantings=tier.max_crop_plantings,
        is_active=tier.is_active, public_store_included=tier.public_store_included,
        staff_branding_included=tier.staff_branding_included, shop_branding_included=tier.shop_branding_included,
        organization_count=counts.get(tier.id, 0),
    )


async def _org_counts(db: AsyncSession) -> dict[uuid.UUID, int]:
    rows = (await db.execute(
        select(Subscription.tier_id, func.count(Subscription.id)).group_by(Subscription.tier_id)
    )).all()
    return {tier_id: count for tier_id, count in rows}


async def list_packages(db: AsyncSession) -> list[schemas.PackageOut]:
    await ensure_default_tiers(db)  # a fresh deployment still lists the four default packages
    await db.commit()
    tiers = (await db.execute(
        select(SubscriptionTier).order_by(SubscriptionTier.monthly_price_kes, SubscriptionTier.name)
    )).scalars().all()
    counts = await _org_counts(db)
    return [_out(t, counts) for t in tiers]


async def create_package(db: AsyncSession, req: schemas.PackageCreate) -> schemas.PackageOut:
    await ensure_default_tiers(db)
    slug = req.slug.strip().lower()
    if (await db.execute(select(SubscriptionTier.id).where(SubscriptionTier.slug == slug))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"A package with the identifier '{slug}' already exists")
    tier = SubscriptionTier(
        slug=slug, name=req.name.strip(), monthly_price_kes=round(req.monthly_price_kes, 2),
        max_users=req.max_users, max_animals=req.max_animals, max_crop_plantings=req.max_crop_plantings,
        is_active=req.is_active, public_store_included=req.public_store_included,
        staff_branding_included=req.staff_branding_included, shop_branding_included=req.shop_branding_included,
    )
    db.add(tier)
    await db.commit()
    await db.refresh(tier)
    return _out(tier, {})


async def update_package(db: AsyncSession, package_id: uuid.UUID, req: schemas.PackageUpdate) -> schemas.PackageOut:
    tier = (await db.execute(select(SubscriptionTier).where(SubscriptionTier.id == package_id))).scalar_one_or_none()
    if tier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    data = req.model_dump(exclude_unset=True)  # omitted = unchanged; an explicit null on a limit = unlimited
    if tier.slug == "free":
        if data.get("is_active") is False:
            raise HTTPException(status.HTTP_409_CONFLICT, "The Free package is where every new tenant starts and can't be switched off")
        if data.get("monthly_price_kes", 0) != 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The Free package must stay at price 0")
    if "name" in data:
        data["name"] = data["name"].strip()
    if "monthly_price_kes" in data:
        data["monthly_price_kes"] = round(data["monthly_price_kes"], 2)
    for field, value in data.items():
        setattr(tier, field, value)
    await db.commit()
    await db.refresh(tier)
    return _out(tier, await _org_counts(db))

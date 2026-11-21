"""Is a tenant's PUBLIC STORE switched on?

Two things decide it, in this order:
  1. a superadmin's per-tenant override (tenant_catalog_settings.public_store_enabled): True forces the store on,
     False forces it off;
  2. otherwise the tenant's billing package (subscription_tiers.public_store_included).

Everything defaults to "on" (the column default is TRUE and the override is NULL), so introducing this changes nothing
for any existing tenant until a superadmin edits a package or a tenant. Read-only on purpose: it is called on public
requests, so it never creates a subscription or settings row.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models import Subscription, SubscriptionTier
from app.modules.catalog.models import TenantCatalogSettings
from app.modules.identity.models import Organization

STORE_UNAVAILABLE_MESSAGE = "This store is currently unavailable."


async def public_store_state(db: AsyncSession, org_id: uuid.UUID) -> dict:
    row = (await db.execute(
        select(
            TenantCatalogSettings.public_store_enabled,
            SubscriptionTier.public_store_included,
            SubscriptionTier.slug,
            SubscriptionTier.name,
        )
        .select_from(Organization)
        .outerjoin(TenantCatalogSettings, TenantCatalogSettings.organization_id == Organization.id)
        .outerjoin(Subscription, Subscription.organization_id == Organization.id)
        .outerjoin(SubscriptionTier, SubscriptionTier.id == Subscription.tier_id)
        .where(Organization.id == org_id)
    )).first()

    override = row[0] if row else None
    package_allows, package_slug, package_name = (row[1], row[2], row[3]) if row else (None, None, None)

    if package_allows is None:
        # No subscription row yet: such a tenant is on the Free package the first time billing is looked at.
        free = (await db.execute(
            select(SubscriptionTier.public_store_included, SubscriptionTier.slug, SubscriptionTier.name)
            .where(SubscriptionTier.slug == "free")
        )).first()
        if free:
            package_allows, package_slug, package_name = free
        else:
            package_allows = True  # packages not seeded yet: nothing has been restricted

    mode = "package" if override is None else ("on" if override else "off")
    return {
        "mode": mode,
        "enabled": bool(package_allows) if override is None else bool(override),
        "package_allows": bool(package_allows),
        "package_slug": package_slug,
        "package_name": package_name,
    }


async def is_public_store_enabled(db: AsyncSession, org_id: uuid.UUID) -> bool:
    return (await public_store_state(db, org_id))["enabled"]

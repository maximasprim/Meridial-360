import uuid
from datetime import datetime
from typing import Literal

from app.core.emailnorm import NormalizedEmail
from pydantic import BaseModel, Field


# Platform admins can see and change every tenant, so their passwords get a
# stricter floor than tenant users' (8). The upper bound is bcrypt's 72-byte
# limit - anything longer is silently truncated by the hash, so reject it instead.
PLATFORM_PASSWORD_MIN = 12
PLATFORM_PASSWORD_MAX = 72


class PlatformAdminLoginRequest(BaseModel):
    email: NormalizedEmail
    password: str


class PlatformAdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PlatformAdminOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    role: str

    class Config:
        from_attributes = True


class OrganizationSummaryOut(BaseModel):
    """Cross-tenant admin view of an org - intentionally separate from
    identity.schemas' tenant-facing OrganizationOut, which a regular user
    sees for their own org only. This one adds fields (suspension status,
    user counts, subscription tier) that no tenant user should ever see
    about their own org via a self-service endpoint."""
    id: uuid.UUID
    name: str
    slug: str
    currency: str
    is_suspended: bool
    user_count: int
    subscription_tier: str | None
    subscription_status: str | None
    created_at: datetime
    # additive (plan management): the tier's stable slug and when the current period ends
    subscription_tier_slug: str | None = None
    subscription_period_end: datetime | None = None

    class Config:
        from_attributes = True


class OrganizationSubscriptionUpdate(BaseModel):
    """A superadmin setting a tenant's plan directly (no payment). `status` defaults to active and the period is
    extended 30 days when it has already ended, so the new plan takes effect immediately."""
    tier_slug: str
    status: str | None = Field(default=None, pattern="^(trialing|active|past_due|cancelled)$")
    current_period_end: datetime | None = None
    reason: str | None = Field(default=None, max_length=300)


class OrganizationStatusUpdate(BaseModel):
    is_suspended: bool
    reason: str | None = None


class PlatformAdminCreateRequest(BaseModel):
    email: NormalizedEmail
    full_name: str
    # no minimum on LOGIN (existing admins keep working); enforced when a password is SET
    password: str = Field(min_length=PLATFORM_PASSWORD_MIN, max_length=PLATFORM_PASSWORD_MAX)
    role: str = Field("superadmin", pattern="^(superadmin|viewer)$")


class PlatformAdminStatusUpdate(BaseModel):
    is_active: bool


class PlatformAdminRoleUpdate(BaseModel):
    role: str = Field(pattern="^(superadmin|viewer)$")


class PlatformAdminPasswordResetRequest(BaseModel):
    email: NormalizedEmail


class PlatformAdminPasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=PLATFORM_PASSWORD_MIN, max_length=PLATFORM_PASSWORD_MAX)


class PlatformDashboardStats(BaseModel):
    total_organizations: int
    active_organizations: int
    suspended_organizations: int
    total_users: int
    organizations_by_tier: dict[str, int]
    mrr_kes: float  # sum of active subscriptions' monthly_price_kes
    signups_last_30_days: int


class LifecycleCheckResult(BaseModel):
    marked_past_due: int
    marked_cancelled: int
    skipped: bool = False


class PublicStoreStatusOut(BaseModel):
    """Whether a tenant's public store works, and why. mode: 'package' (follows the billing package), 'on' or 'off'
    (a superadmin override). `enabled` is the effective result."""
    mode: Literal["package", "on", "off"]
    enabled: bool
    package_allows: bool
    package_slug: str | None = None
    package_name: str | None = None


class PublicStoreUpdate(BaseModel):
    mode: Literal["package", "on", "off"]
    reason: str | None = Field(default=None, max_length=300)


class AppBrandingOut(BaseModel):
    """Whether the staff app (installed app + sign-in page) and the public shop (installed app) present the farm's own
    name and logo (True) or the platform's (False). has_icon: an uploaded logo exists to build installed-app icons from."""
    staff_tenant_branding: bool
    shop_tenant_branding: bool
    farm_name: str | None = None
    has_logo: bool = False
    has_icon: bool = False


class AppBrandingUpdate(BaseModel):
    """Omitted = unchanged."""
    staff: bool | None = None
    shop: bool | None = None

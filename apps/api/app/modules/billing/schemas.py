import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class SubscriptionTierOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    monthly_price_kes: float
    max_users: int | None
    max_animals: int | None
    max_crop_plantings: int | None = None
    public_store_included: bool = True

    class Config:
        from_attributes = True


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    status: str
    current_period_start: datetime
    current_period_end: datetime | None
    cancel_at_period_end: bool
    tier: SubscriptionTierOut

    class Config:
        from_attributes = True


class SubscribeRequest(BaseModel):
    tier_slug: str
    phone_number: str = Field(..., description="M-Pesa phone number, e.g. 254712345678")


class SubscriptionPaymentOut(BaseModel):
    id: uuid.UUID
    status: str
    amount: float
    currency: str
    provider_reference: str
    initiated_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True


# ----------------------------------------------------- package management --
class PackageOut(BaseModel):
    """A billing package as a superadmin sees it (includes switched-off packages and how many tenants are on it)."""
    id: uuid.UUID
    name: str
    slug: str
    monthly_price_kes: float
    max_users: int | None
    max_animals: int | None
    max_crop_plantings: int | None
    is_active: bool
    public_store_included: bool
    organization_count: int


class PackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    slug: str = Field(min_length=2, max_length=64, pattern="^[a-zA-Z0-9][a-zA-Z0-9-]*$")
    monthly_price_kes: float = Field(ge=0, le=10_000_000)
    # None = unlimited
    max_users: int | None = Field(default=None, ge=1)
    max_animals: int | None = Field(default=None, ge=1)
    max_crop_plantings: int | None = Field(default=None, ge=1)
    is_active: bool = True
    public_store_included: bool = True


class PackageUpdate(BaseModel):
    """Omitted field = unchanged. For the three limits an explicit null means unlimited. The slug can't be changed."""
    name: str | None = Field(default=None, min_length=1, max_length=64)
    monthly_price_kes: float | None = Field(default=None, ge=0, le=10_000_000)
    max_users: int | None = Field(default=None, ge=1)
    max_animals: int | None = Field(default=None, ge=1)
    max_crop_plantings: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    public_store_included: bool | None = None

    @model_validator(mode="after")
    def _required_fields_cannot_be_null(self):
        for field in ("name", "monthly_price_kes", "is_active", "public_store_included"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

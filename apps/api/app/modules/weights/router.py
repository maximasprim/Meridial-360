import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.cycles.deps import CycleSel, cycle_filter
from app.modules.identity.deps import require_permission
from app.modules.identity.models import User
from app.modules.weights import service

router = APIRouter(prefix="/api/v1/weights", tags=["weights"])


class TargetIn(BaseModel):
    target_weight_kg: Decimal | None = Field(default=None, gt=0, le=2000)   # null clears it
    target_days: int | None = Field(default=None, gt=0, le=3650)            # only changed when sent; null clears it


class DefaultsIn(BaseModel):
    target_weight_kg: Decimal = Field(gt=0, le=2000)
    target_days: int | None = Field(default=None, gt=0, le=3650)    # null = no default schedule


@router.put("/defaults")
async def set_defaults(req: DefaultsIn, user: User = Depends(require_permission("weights.targets")),
                       db: AsyncSession = Depends(get_db)):
    """The farm-wide default target weight and days, used for feedlot animals with no target of their own or on their batch."""
    return await service.set_defaults(db, user.organization_id, float(req.target_weight_kg), req.target_days)


def _days(req: TargetIn) -> dict:
    """Only touch target_days when the caller sent it, so older callers that send just the weight are unaffected."""
    return {"days": req.target_days} if "target_days" in req.model_fields_set else {}


@router.get("/overview")
async def overview(batch_id: uuid.UUID | None = Query(None), user: User = Depends(require_permission("weights.view")),
                   db: AsyncSession = Depends(get_db), cycle: CycleSel | None = Depends(cycle_filter)):
    """Every animal still on the farm: latest weight, gain, target, readiness - plus a summary per batch."""
    return await service.overview(db, user.organization_id, batch_id, cycle)


@router.get("/daily")
async def daily(day: date | None = Query(None), user: User = Depends(require_permission("weights.view")),
                db: AsyncSession = Depends(get_db), cycle: CycleSel | None = Depends(cycle_filter)):
    """Weights recorded on one day (default: the latest weigh day), each compared with the animal's previous weighing."""
    return await service.daily(db, user.organization_id, day, cycle)


class AlertReviewIn(BaseModel):
    alert_date: date                                   # the "to" date of the alert being reviewed
    note: str | None = Field(default=None, max_length=500)


@router.get("/alerts")
async def alerts(user: User = Depends(require_permission("weights.view")), db: AsyncSession = Depends(get_db),
                 cycle: CycleSel | None = Depends(cycle_filter)):
    """Animals whose daily gain between the last two weighings is above +2 or below -2 kg/day and not yet reviewed."""
    from app.modules.weights import alerts as weight_alerts
    return await weight_alerts.list_open(db, user.organization_id, cycle)


@router.post("/alerts/{animal_id}/review")
async def review_alert(animal_id: uuid.UUID, req: AlertReviewIn, user: User = Depends(require_permission("weights.targets")),
                       db: AsyncSession = Depends(get_db)):
    """Mark an alert as followed up (it stays hidden for that reading; a newer weighing is judged afresh)."""
    from app.modules.weights import alerts as weight_alerts
    return await weight_alerts.review(db, user.organization_id, user.id, animal_id, req.alert_date, req.note)


@router.get("/animals/{animal_id}")
async def animal_detail(animal_id: uuid.UUID, user: User = Depends(require_permission("weights.view")),
                        db: AsyncSession = Depends(get_db)):
    """One animal's weight history, gain per interval, projection to its target and its batch average."""
    return await service.animal_detail(db, user.organization_id, animal_id)


@router.put("/batches/{batch_id}/target")
async def set_batch_target(batch_id: uuid.UUID, req: TargetIn, user: User = Depends(require_permission("weights.targets")),
                           db: AsyncSession = Depends(get_db)):
    return await service.set_batch_target(db, user.organization_id, batch_id,
                                          float(req.target_weight_kg) if req.target_weight_kg else None,
                                          **_days(req))


@router.put("/animals/{animal_id}/target")
async def set_animal_target(animal_id: uuid.UUID, req: TargetIn, user: User = Depends(require_permission("weights.targets")),
                            db: AsyncSession = Depends(get_db)):
    return await service.set_animal_target(db, user.organization_id, animal_id,
                                           float(req.target_weight_kg) if req.target_weight_kg else None,
                                           **_days(req))

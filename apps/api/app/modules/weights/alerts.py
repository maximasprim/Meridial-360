"""Daily-gain alerts: animals whose gain between their last two weighings is above +2 or below -2 kg/day.

Computed live from the weights (voided / corrected weights are already left out by the weights loader), so an alert
disappears by itself when the weight is corrected or a newer weighing is normal. A person can also mark it reviewed
(kept in weight_alert_reviews) so it stops showing while the reading stands.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cycles.deps import CycleSel
from app.modules.livestock.models import Animal, WeightAlertReview
from app.modules.weights import logic, service


async def list_open(db: AsyncSession, org_id: uuid.UUID, cycle: CycleSel | None = None) -> dict:
    rows = await service.assess_org(db, org_id, cycle=cycle)
    flagged = [r for r in rows if r.get("adg_alert")]
    if not flagged:
        return {"threshold": logic.ADG_ALERT, "count": 0, "alerts": []}
    ids = [uuid.UUID(r["id"]) for r in flagged]
    done = {(aid, d) for aid, d in (await db.execute(
        select(WeightAlertReview.animal_id, WeightAlertReview.alert_date).where(WeightAlertReview.animal_id.in_(ids)))).all()}
    alerts = []
    for r in flagged:
        a = r["adg_alert"]
        if (uuid.UUID(r["id"]), date.fromisoformat(a["to_date"])) in done:
            continue
        alerts.append({"animal_id": r["id"], "tag": r["tag"], "batch": r["batch"], **a})
    alerts.sort(key=lambda x: -abs(x["adg"]))
    return {"threshold": logic.ADG_ALERT, "count": len(alerts), "alerts": alerts}


async def review(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, animal_id: uuid.UUID, alert_date: date,
                 note: str | None) -> dict:
    animal = (await db.execute(select(Animal).where(Animal.id == animal_id, Animal.organization_id == org_id))).scalar_one_or_none()
    if animal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Animal not found")
    have = (await db.execute(select(WeightAlertReview.id).where(WeightAlertReview.animal_id == animal_id,
                                                                WeightAlertReview.alert_date == alert_date))).scalar_one_or_none()
    if have is None:
        db.add(WeightAlertReview(organization_id=org_id, animal_id=animal_id, alert_date=alert_date, note=(note or None),
                                 reviewed_by=user_id))
        await db.commit()
    return {"status": "reviewed", "animal_id": str(animal_id), "alert_date": alert_date.isoformat()}

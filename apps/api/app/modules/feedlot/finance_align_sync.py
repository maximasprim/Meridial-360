"""Brings the Finance ledger's livestock purchases in line with the worksheet's batches (database side).

Only ADDS ledger rows (reference_type 'worksheet_adjustment', category livestock_acquisition, tagged with the batch's
production cycle so cycle reports include them). Nothing is edited or deleted. Preview first (dry_run, the default).
Sales are not covered here: a sale's cash/credit posting follows the customer's account and needs its own step.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.feedlot import ledger_sync
from app.modules.feedlot.finance_align import plan_purchase_adjustments
from app.modules.feedlot.models import FeedlotAnimal, IntakeBatch
from app.modules.finance.models import FinanceTransaction
from app.modules.livestock.models import Animal

ADJUSTMENT_REF = "worksheet_adjustment"
MAX_ITEMS = 200


async def align_purchases(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, *, cycle_id: uuid.UUID | None = None,
                          dry_run: bool = True, dating: str = "original") -> dict:
    if dating not in ("original", "today"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "dating must be 'original' or 'today'")
    if not dry_run:
        await ledger_sync._lock_or_409(db, org_id)
    q = (select(FeedlotAnimal, Animal, IntakeBatch).join(Animal, Animal.id == FeedlotAnimal.animal_id)
         .join(IntakeBatch, IntakeBatch.id == FeedlotAnimal.intake_batch_id)
         .where(FeedlotAnimal.organization_id == org_id).order_by(Animal.animal_number))
    if cycle_id:
        q = q.where(IntakeBatch.production_cycle_id == cycle_id)
    rows = (await db.execute(q)).all()
    booked: dict[uuid.UUID, list[tuple[date, float]]] = defaultdict(list)
    ids = [a.id for _, a, _ in rows]
    if ids:
        tx = select(FinanceTransaction.reference_id, FinanceTransaction.transaction_date, FinanceTransaction.amount).where(
            FinanceTransaction.organization_id == org_id, FinanceTransaction.category == ledger_sync.ACQUISITION_CATEGORY,
            FinanceTransaction.transaction_type == "expense", FinanceTransaction.reference_id.in_(ids),
            FinanceTransaction.reference_type.in_((ledger_sync.ACQUISITION_REF, ADJUSTMENT_REF)))
        for rid, d, amt in (await db.execute(tx)).all():
            booked[rid].append((d, float(amt)))

    today = datetime.now().date()
    items, entries, not_booked = [], 0, 0
    net = 0.0
    months: dict[str, float] = defaultdict(float)
    for fa, animal, ib in rows:
        expected = float(ib.landed_cost_per_head)
        had = booked.get(animal.id, [])
        if not had:
            not_booked += 1
        plan = plan_purchase_adjustments(had, expected, fa.received_on, dating=dating, today=today)
        cost_differs = animal.acquisition_cost is None or abs(float(animal.acquisition_cost) - expected) > 0.004
        if not plan and not (cost_differs and expected > 0):
            continue
        if len(items) < MAX_ITEMS:
            items.append({"tag": animal.animal_number, "batch": ib.batch_number, "booked": round(sum(a for _, a in had), 2),
                          "expected": expected, "adjustments": [{"date": d.isoformat(), "amount": a} for d, a in plan]})
        for d, amt in plan:
            entries += 1; net += amt; months[d.strftime("%Y-%m")] += amt
            if not dry_run:
                db.add(FinanceTransaction(
                    organization_id=org_id, production_cycle_id=ib.production_cycle_id, transaction_type="expense",
                    category=ledger_sync.ACQUISITION_CATEGORY, amount=Decimal(str(amt)), transaction_date=d,
                    farm_id=animal.farm_id, activity="feedlot", reference_type=ADJUSTMENT_REF, reference_id=animal.id,
                    description=f"Worksheet correction: purchase of {animal.animal_number} (batch {ib.batch_number})", created_by=user_id))
        if not dry_run and cost_differs and expected > 0:
            animal.acquisition_cost = Decimal(str(expected))
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return {"dry_run": dry_run, "dating": dating, "animals_checked": len(rows), "animals_with_changes": len(items),
            "entries": entries, "net_amount": round(net, 2), "by_month": {k: round(v, 2) for k, v in sorted(months.items())},
            "purchases_not_booked_yet": not_booked, "items": items,
            "note": "Sales are not changed by this step. Purchases that were never booked are booked by the normal Finance sync."}

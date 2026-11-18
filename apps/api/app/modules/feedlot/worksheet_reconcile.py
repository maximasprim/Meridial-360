"""Database side of aligning imported weights with a worksheet (the rules are in worksheet_align).

Used by the importer (`import_worksheet`, reconcile mode) and by restore / unpost in worksheet_versions. It only ever
writes: new weight records, rows in weight_voids (and deletes of those rows), the matching timeline events, the
animal's current_weight and a feedlot link's entry weight. It never edits or deletes a weight record.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.feedlot.batch_scope import existing_by_number
from app.modules.feedlot.models import FeedlotAnimal, IntakeBatch
from app.modules.feedlot.worksheet_align import IMPORT_NOTE, StoredWeight, plan_weights, split_duplicate_days
from app.modules.livestock.models import Animal, AnimalEvent, WeightRecord, WeightVoid, live_weights

MAX_DETAILS = 200


def _utc(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _day(dt: datetime) -> date:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).date()


def _kg(x) -> str:
    return f"{float(x):g}"


async def align_animal_weights(db: AsyncSession, animal: Animal, desired: list[tuple[date, float]],
                               user_id: uuid.UUID | None, version_id: uuid.UUID | None, report: dict, *,
                               prune: bool = True, tag: str | None = None) -> bool:
    """Make the animal's imported weights match `desired` ([(date, kg)] from the worksheet). -> True if anything changed.
    Dates that the sheet lists twice are skipped and reported (ambiguous)."""
    clean, dups = split_duplicate_days(desired)
    rows = (await db.execute(
        select(WeightRecord, WeightVoid.id)
        .outerjoin(WeightVoid, WeightVoid.weight_record_id == WeightRecord.id)
        .where(WeightRecord.animal_id == animal.id)
        .order_by(WeightRecord.created_at, WeightRecord.recorded_at))).all()
    stored = [StoredWeight(id=str(w.id), day=_day(w.recorded_at), kg=float(w.weight_kg), imported=(w.notes == IMPORT_NOTE),
                           voided=vid is not None, order=i) for i, (w, vid) in enumerate(rows)]
    plan = plan_weights(stored, clean, prune=prune, protect=dups)
    label = tag or animal.animal_number
    if dups:
        report.setdefault("ambiguous_dates", []).append({"tag": label, "dates": sorted(d.isoformat() for d in dups)})
    for c in plan.conflicts:
        report.setdefault("weight_conflicts", []).append({"tag": label, **c})
    if not plan.changed:
        return False

    by_id = {str(w.id): w for w, _ in rows}
    now = datetime.now(timezone.utc)
    detail = {"tag": label, "void": [], "append": [], "restore": []}
    for wid, reason in plan.void:
        w = by_id[wid]
        db.add(WeightVoid(organization_id=animal.organization_id, weight_record_id=w.id, reason=reason,
                          version_id=version_id, voided_by=user_id))
        db.add(AnimalEvent(animal_id=animal.id, event_type="weight_voided", event_at=now, recorded_by=user_id,
                           data={"weight_kg": _kg(w.weight_kg), "recorded_on": _day(w.recorded_at).isoformat(),
                                 "reason": reason, "imported": True}))
        detail["void"].append({"date": _day(w.recorded_at).isoformat(), "kg": float(w.weight_kg)})
    if plan.unvoid:
        await db.execute(delete(WeightVoid).where(WeightVoid.weight_record_id.in_([uuid.UUID(i) for i in plan.unvoid])))
        for i in plan.unvoid:
            w = by_id[i]
            detail["restore"].append({"date": _day(w.recorded_at).isoformat(), "kg": float(w.weight_kg)})
    for d, kg in plan.append:
        db.add(WeightRecord(animal_id=animal.id, weight_kg=Decimal(str(kg)), recorded_at=_utc(d), recorded_by=user_id,
                            notes=IMPORT_NOTE))
        db.add(AnimalEvent(animal_id=animal.id, event_type="weighed", event_at=_utc(d), recorded_by=user_id,
                           data={"weight_kg": _kg(kg), "imported": True}))
        detail["append"].append({"date": d.isoformat(), "kg": float(kg)})

    report["created"]["weight_records"] += len(plan.append)
    report["updated"]["weights_voided"] += len(plan.void)
    report["updated"]["weights_restored"] += len(plan.unvoid)
    changes = report.setdefault("weight_changes", [])
    if len(changes) < MAX_DETAILS:
        changes.append(detail)

    await db.flush()
    latest = (await db.execute(
        select(WeightRecord.weight_kg).where(WeightRecord.animal_id == animal.id, live_weights())
        .order_by(WeightRecord.recorded_at.desc(), WeightRecord.created_at.desc()).limit(1))).scalar_one_or_none()
    if latest is not None and (animal.status == "active" or animal.current_weight is None):
        animal.current_weight = latest
    return True


def align_entry_weight(fa: FeedlotAnimal | None, entry: float | None, report: dict) -> bool:
    """Entry weight = the animal's first weight on the sheet. Corrected when the sheet changed it."""
    if fa is None or not entry:
        return False
    if fa.entry_weight_kg is not None and abs(float(fa.entry_weight_kg) - float(entry)) <= 0.004:
        return False
    fa.entry_weight_kg = Decimal(str(entry))
    report["updated"]["entry_weights"] += 1
    return True


async def realign_from_workbook(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID | None, pw, *,
                                cycle_id: uuid.UUID | None, version_id: uuid.UUID | None, report: dict,
                                empty: bool = False) -> None:
    """Align animals that ALREADY exist with `pw`; creates nothing else (no animals, batches, sales, finance).
    empty=True removes every imported weight instead (unpost). Animals whose batch in the system differs from the
    batch the sheet lists them under are left alone and reported."""
    batch_rows = list((await db.execute(select(IntakeBatch).where(IntakeBatch.organization_id == org_id)
                                        .order_by(IntakeBatch.created_at))).scalars())
    by_number = existing_by_number(batch_rows, cycle_id)
    scope = [b for b in batch_rows if cycle_id is None or b.production_cycle_id == cycle_id]
    members: dict[uuid.UUID, dict[str, tuple[Animal, FeedlotAnimal]]] = {b.id: {} for b in scope}
    if scope:
        q = (select(Animal, FeedlotAnimal).join(FeedlotAnimal, FeedlotAnimal.animal_id == Animal.id)
             .where(Animal.organization_id == org_id, FeedlotAnimal.intake_batch_id.in_(list(members))))
        for a, fa in (await db.execute(q)).all():
            members[fa.intake_batch_id][a.animal_number] = (a, fa)

    if empty:
        for b in scope:
            for tag, (a, fa) in sorted(members[b.id].items()):
                await align_animal_weights(db, a, [], user_id, version_id, report, prune=True, tag=tag)
        return

    missing: list[str] = []
    for num, sh in sorted(pw.intake.items()):
        b = by_number.get(num)
        if b is None:
            report["warnings"].append({"code": "batch_not_found", "where": sh.sheet,
                                       "message": f"{sh.sheet}: no batch {num} exists in this cycle, so nothing was aligned for it"})
            continue
        group = members.get(b.id, {})
        for r in sh.rows:
            hit = group.get(r["tag"])
            if hit is None:
                missing.append(r["tag"])
                continue
            a, fa = hit
            align_entry_weight(fa, r["entry_weight"], report)
            await align_animal_weights(db, a, r["weights"], user_id, version_id, report, prune=bool(r["weights"]), tag=r["tag"])
    if missing:
        report["warnings"].append({"code": "tags_not_in_system_batch", "where": "worksheet",
                                   "message": f"{len(missing)} tag(s) on the sheet are not in the matching batch in the system and were skipped: {missing[:12]}"})

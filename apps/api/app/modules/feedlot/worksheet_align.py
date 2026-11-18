"""Rules for aligning one animal's IMPORTED weights with what the worksheet now says.

Pure Python (no database, no framework) so the rules can be unit-tested on their own.

Why this exists: `weight_records` is append-only (a database trigger rejects UPDATE and DELETE), and the original
importer only ever added weights for dates it had not seen. When the farm corrected the worksheet afterwards, the old
value stayed and the correction was skipped. A correction therefore has two parts:

  * void   - the wrong imported record is set aside (a row in `weight_voids`; every reader skips voided records)
  * append - the right value is added as a new record

and a void can be undone (the row is deleted), which is how an older worksheet version is restored.

Rules, per weigh date:
  * the farm's own entries (anything not written by the importer) are never changed - a difference is reported;
  * a date the sheet no longer has: its live imported records are voided (only when `prune`);
  * a date the sheet has: exactly one live imported record with that value remains. A previously voided record with
    the same value is brought back instead of adding a duplicate.
  * a date that appears twice in the SAME sheet row (two header cells typed with the same date) is ambiguous: it is
    left exactly as it is and reported, never guessed (see `split_duplicate_days`).
Applying the plan and planning again gives an empty plan (idempotent).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

IMPORT_NOTE = "Imported from worksheet"
_TOL = 0.005


@dataclass(frozen=True)
class StoredWeight:
    id: str
    day: date
    kg: float
    imported: bool      # written by the worksheet importer (notes == IMPORT_NOTE)
    voided: bool
    order: int          # entry order, oldest = 0 (the weights report keeps the LAST one entered on a day)


@dataclass
class WeightPlan:
    append: list[tuple[date, float]] = field(default_factory=list)
    void: list[tuple[str, str]] = field(default_factory=list)       # (weight id, reason)
    unvoid: list[str] = field(default_factory=list)                 # weight ids brought back
    conflicts: list[dict] = field(default_factory=list)             # the farm's own entry differs from the sheet

    @property
    def changed(self) -> bool:
        return bool(self.append or self.void or self.unvoid)


def _same(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < _TOL


def split_duplicate_days(desired: list[tuple[date, float]]) -> tuple[list[tuple[date, float]], set[date]]:
    """-> (weights on dates that appear once, the set of dates that appear more than once). A sheet whose header has
    the same date in two columns cannot say which value belongs to the date, so those dates are not touched."""
    counts: dict[date, int] = defaultdict(int)
    for d, _ in desired:
        counts[d] += 1
    dups = {d for d, n in counts.items() if n > 1}
    return [(d, kg) for d, kg in desired if d not in dups], dups


def plan_weights(stored: list[StoredWeight], desired: list[tuple[date, float]], *, prune: bool = True,
                 protect: frozenset[date] | set[date] = frozenset()) -> WeightPlan:
    """stored: every weight record of the animal (voided ones included). desired: [(date, kg)] from the worksheet.
    protect: dates that must not be touched at all (ambiguous in the sheet)."""
    want: dict[date, float] = {}
    for d, kg in desired:
        want[d] = float(kg)
    by_day: dict[date, list[StoredWeight]] = defaultdict(list)
    for w in stored:
        by_day[w.day].append(w)
    plan = WeightPlan()
    days = (set(want) | (set(by_day) if prune else set())) - set(protect)
    for day in sorted(days):
        recs = sorted(by_day.get(day, []), key=lambda w: w.order)
        live = [w for w in recs if not w.voided]
        manual = [w for w in live if not w.imported]
        imported_live = [w for w in live if w.imported]
        target = want.get(day)
        if manual:
            if target is not None and not _same(manual[-1].kg, target):
                plan.conflicts.append({"date": day.isoformat(), "system_kg": manual[-1].kg, "sheet_kg": target})
            continue
        if target is None:
            for w in imported_live:
                plan.void.append((w.id, "no longer in the worksheet"))
            continue
        keep = next((w for w in reversed(imported_live) if _same(w.kg, target)), None)
        if keep is None:
            back = next((w for w in reversed(recs) if w.imported and w.voided and _same(w.kg, target)), None)
            if back is not None:
                plan.unvoid.append(back.id)
                keep = back
            else:
                plan.append.append((day, target))
        for w in imported_live:
            if keep is not None and w.id == keep.id:
                continue
            plan.void.append((w.id, "replaced by the worksheet value"))
    return plan

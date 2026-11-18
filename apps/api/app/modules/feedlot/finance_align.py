"""Pure rules for aligning the Finance ledger's purchase entries with the worksheet (no database, no framework).

The ledger is append-only, so a purchase that was booked at the wrong amount (or in the wrong month, because the animal
was in another batch) is corrected by ADDING entries that bring the books to the right figure. An entry can be negative.

  dating="original": each month ends up exactly right. The wrong amount is cancelled in the month it was booked and the
                     right amount is booked on the animal's delivery date.
  dating="today":    past months are left as reported; one entry dated today carries the whole difference.

Applying the plan and planning again gives an empty plan (idempotent).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

_TOL = 0.005


def plan_purchase_adjustments(booked: list[tuple[date, float]], expected: float, expected_on: date, *,
                              dating: str = "original", today: date | None = None) -> list[tuple[date, float]]:
    """booked: [(date, amount)] already in the ledger for this animal's purchase (earlier adjustments included).
    -> [(date, amount)] entries to add. Nothing is planned when nothing is booked yet (the normal Finance sync books
    a missing purchase) or when the expected cost is zero."""
    if not booked or expected <= 0:
        return []
    by_day: dict[date, float] = defaultdict(float)
    for d, a in booked:
        by_day[d] += float(a)
    if dating == "today":
        delta = round(expected - sum(by_day.values()), 2)
        return [(today or date.today(), delta)] if abs(delta) >= _TOL else []
    out: list[tuple[date, float]] = []
    for d in sorted(set(by_day) | {expected_on}):
        target = expected if d == expected_on else 0.0
        delta = round(target - by_day.get(d, 0.0), 2)
        if abs(delta) >= _TOL:
            out.append((d, delta))
    return out

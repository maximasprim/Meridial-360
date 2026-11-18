"""Aligning imported weights with a changed worksheet: the pure rules (no database)."""
import pathlib
from datetime import date

from app.modules.feedlot.worksheet_align import StoredWeight as S, plan_weights, split_duplicate_days
from app.modules.feedlot.worksheet_parse import parse_workbook

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sahara_oasis_second_cycle.xlsx"
D = date


def test_a_corrected_first_weight_is_voided_and_replaced_then_nothing_more_to_do():
    desired = [(D(2026, 10, 23), 228), (D(2026, 11, 2), 233)]
    p = plan_weights([S("a", D(2026, 10, 23), 179, True, False, 0)], desired)
    assert p.void == [("a", "replaced by the worksheet value")] and p.append == desired and not p.unvoid
    after = [S("a", D(2026, 10, 23), 179, True, True, 0), S("b", D(2026, 10, 23), 228, True, False, 1), S("c", D(2026, 11, 2), 233, True, False, 2)]
    assert not plan_weights(after, desired).changed                       # idempotent


def test_a_date_the_sheet_dropped_is_voided_and_a_voided_value_that_returns_is_brought_back():
    p = plan_weights([S("x", D(2026, 10, 27), 216, True, False, 0)], [(D(2026, 11, 3), 200)])
    assert [i for i, _ in p.void] == ["x"] and p.append == [(D(2026, 11, 3), 200.0)]
    back = plan_weights([S("x", D(2026, 10, 27), 216, True, True, 0)], [(D(2026, 10, 27), 216)])
    assert back.unvoid == ["x"] and not back.append and not back.void     # restore = bring the old record back


def test_the_farms_own_entries_are_never_changed_only_reported():
    p = plan_weights([S("m", D(2026, 11, 14), 250, False, False, 0)], [(D(2026, 11, 14), 242)])
    assert not p.changed and p.conflicts == [{"date": "2026-11-14", "system_kg": 250, "sheet_kg": 242.0}]
    assert not plan_weights([S("m", D(2026, 11, 20), 260, False, False, 0)], []).changed       # a manual date is not pruned


def test_a_date_listed_twice_on_the_sheet_is_left_alone():
    clean, dups = split_duplicate_days([(D(2026, 10, 26), 251), (D(2026, 10, 26), 261), (D(2026, 11, 14), 262)])
    assert clean == [(D(2026, 11, 14), 262)] and dups == {D(2026, 10, 26)}
    p = plan_weights([S("k", D(2026, 10, 26), 251, True, False, 0)], clean, protect=dups)
    assert not p.void and p.append == [(D(2026, 11, 14), 262.0)]         # the real 26 Oct reading is kept; only 14 Nov is added


def test_the_second_cycle_fixture_has_no_duplicate_weigh_dates():
    pw = parse_workbook(FIXTURE.read_bytes())
    for sh in pw.intake.values():
        for r in sh.rows:
            assert not split_duplicate_days(r["weights"])[1], (sh.sheet, r["tag"])


def test_finance_purchase_adjustments_correct_each_month_or_carry_the_difference_today():
    from app.modules.feedlot.finance_align import plan_purchase_adjustments as plan
    booked = [(D(2026, 10, 26), 61333.33)]                              # booked at the old batch's cost, old delivery date
    assert plan(booked, 48416.67, D(2026, 11, 2)) == [(D(2026, 10, 26), -61333.33), (D(2026, 11, 2), 48416.67)]
    assert plan(booked, 48416.67, D(2026, 11, 2), dating="today", today=D(2026, 11, 18)) == [(D(2026, 11, 18), -12916.66)]
    assert plan([(D(2026, 11, 2), 100.0)], 100.0, D(2026, 11, 2)) == []                       # already right
    assert plan([], 500.0, D(2026, 11, 2)) == []                                               # never booked: normal sync's job
    after = booked + [(D(2026, 10, 26), -61333.33), (D(2026, 11, 2), 48416.67)]
    assert plan(after, 48416.67, D(2026, 11, 2)) == []                                         # idempotent

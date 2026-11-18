"""Daily-gain alert: above +2 or below -2 kg/day between the last two weighings (pure rules, no database)."""
from datetime import date

from app.modules.weights import logic

D = date


def test_a_gain_or_loss_beyond_two_kg_a_day_raises_an_alert_with_the_two_weighings():
    up = logic.adg_alert([(D(2026, 10, 27), 210.0), (D(2026, 11, 14), 272.0)])           # +62 kg in 18 days = 3.44
    assert up["direction"] == "high" and up["adg"] == 3.44 and (up["from_kg"], up["to_kg"], up["days"]) == (210.0, 272.0, 18)
    down = logic.adg_alert([(D(2026, 10, 27), 216.0), (D(2026, 11, 3), 200.0)])          # -16 kg in 7 days = -2.29
    assert down["direction"] == "low" and down["adg"] == -2.29 and down["to_date"] == "2026-11-03"


def test_no_alert_at_or_inside_two_kg_a_day_or_with_fewer_than_two_weighings():
    assert logic.adg_alert([(D(2026, 11, 3), 279.0), (D(2026, 11, 14), 301.0)]) is None   # exactly 2.00
    assert logic.adg_alert([(D(2026, 10, 27), 216.0), (D(2026, 11, 14), 211.0)]) is None
    assert logic.adg_alert([(D(2026, 11, 14), 211.0)]) is None and logic.adg_alert([]) is None


def test_only_the_latest_interval_counts():
    pts = [(D(2026, 10, 1), 200.0), (D(2026, 10, 3), 260.0), (D(2026, 10, 13), 270.0)]    # an old jump, then a normal gain
    assert logic.adg_alert(pts) is None


def test_assess_carries_the_alert_and_a_flag_for_the_weights_page():
    pts = [(D(2026, 11, 3), 200.0), (D(2026, 11, 14), 240.0)]                             # +3.64 kg/day
    out = logic.assess(pts, 400.0, 200.0, D(2026, 11, 18))
    assert out["adg_alert"]["adg"] == 3.64 and "adg_alert" in out["flags"]
    ok = logic.assess([(D(2026, 11, 3), 200.0), (D(2026, 11, 14), 222.0)], 400.0, 200.0, D(2026, 11, 18))
    assert ok["adg_alert"] is None and "adg_alert" not in ok["flags"]

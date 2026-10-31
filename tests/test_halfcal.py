"""The honest tail of plan item 15: the split, the cross-fit and the cap. No data on disk needed."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

from landers import halfcal as hc


def test_checkerboard_is_fixed_on_the_ground():
    assert hc.colour([0, 0, 3999, 4000], [0, 4000, 0, 4000], 0.25).tolist() == [0, 1, 0, 0]
    assert hc.colour([0, 0, 1999, 2000], [0, 2000, 0, 2000], 0.5).tolist() == [0, 1, 0, 0]
    assert hc.colour([0, 2000], [0, 0], 0.25, shift_m=500.0).tolist() == [0, 1]


def test_colour_areas_sum_to_the_valid_area():
    valid = np.ones((1000, 500), bool)
    valid[:10] = False
    a0, a1 = hc.colour_areas(valid, 16, 0.25)
    assert a0 + a1 == pytest.approx(float(valid.sum()) * (16 * 0.25) ** 2 / 1e6)
    assert a0 > 0 and a1 > 0


def test_inside_the_curve_the_score_is_the_measured_rate():
    raw = np.arange(1.0, 101.0)
    cal = hc.fit_population(np.array(["bright"] * 100), raw, 10.0)
    got = hc.capped_scores(cal, np.array(["bright"]), np.array([100.0]), np.array([0.0]))[0]
    assert got == pytest.approx(math.log10(10.0) + hc.TIE_BREAK * 100.0)
    got = hc.capped_scores(cal, np.array(["bright"]), np.array([1.0]), np.array([0.0]))[0]
    assert got == pytest.approx(-math.log10(100 / 10.0) + hc.TIE_BREAK * 1.0)


def test_nothing_is_extrapolated_above_the_curve():
    cal = hc.fit_population(np.array(["bright"] * 3), np.array([1.0, 2.0, 3.0]), 8.0)
    cap = hc.cap_of(8.0)
    s = hc.capped_scores(cal, np.array(["bright", "bright"]), np.array([3.5, 1000.0]), np.array([1.0, 1.0]))
    assert s[0] == s[1], "how far above the top claims nothing: the table's order alone separates them"
    assert cap <= s[0] < cap + hc.ORDER_SPAN


def test_the_table_orders_within_the_cap_across_branches():
    cal = hc.fit_population(np.array(["bright"]), np.array([1.0]), 8.0)
    s = hc.capped_scores(cal, np.array(["bright", "sheet"]), np.array([2.0, 99.0]), np.array([3.0, 2.0]))
    assert s[0] > s[1]
    assert hc.cap_of(8.0) <= s[1] < hc.cap_of(8.0) + hc.ORDER_SPAN


def test_a_branch_empty_on_the_fitted_colour_gets_the_cap_not_a_table_score():
    cal = hc.fit_population(np.array(["bright"]), np.array([1.0]), 8.0)
    s = hc.capped_scores(cal, np.array(["dark"]), np.array([5.0]), np.array([-2.0]))[0]
    assert hc.cap_of(8.0) <= s < hc.cap_of(8.0) + hc.ORDER_SPAN


def test_cap_stands_above_every_measured_score_for_ordinary_raw_scores():
    raw = np.arange(1.0, 51.0)
    cal = hc.fit_population(np.array(["bright"] * 50), raw, 8.0)
    top_inside = hc.capped_scores(cal, np.array(["bright"]), np.array([50.0]), np.array([0.0]))[0]
    above = hc.capped_scores(cal, np.array(["bright"]), np.array([51.0]), np.array([-100.0]))[0]
    assert above > top_inside


def test_a_candidate_does_not_lower_its_own_rarity():
    branches = np.array(["bright"] * 6)
    raw = np.array([1.0, 2.0, 3.0, 1.5, 2.5, 500.0])
    colours = np.array([0, 0, 0, 1, 1, 1])
    cals = hc.cross_fit(branches, raw, colours, (4.0, 4.0))
    assert max(cals[0].branches["bright"].scores) == 3.0
    s = hc.score_by_other(cals, branches, raw, np.zeros(6), colours)
    assert s[5] >= hc.cap_of(4.0), "fitted on the other colour, the strong candidate sits above the curve"
    assert s[2] < s[5]


def test_cross_fit_refuses_a_colour_without_area():
    with pytest.raises(ValueError):
        hc.cross_fit(np.array(["bright"]), np.array([1.0]), np.array([0]), (4.0, 0.0))


def test_realised_rates_leave_out_levels_at_the_cap():
    r = hc.realised_rates(np.array([0.5, 1.5, 2.5]), np.array(["a", "a", "b"]), 2.0, (0.0, 1.0, 2.0), cap=2.0)
    assert sorted(r) == [0.0, 1.0]
    assert r[0.0]["all"] == 1.5
    assert r[1.0]["branches"] == {"a": 0.5, "b": 0.5}


def test_the_runner_refuses_a_strip_of_a_blind_site(monkeypatch, tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import halfcal as script
    import rerank as rr

    sites, _, _ = rr.controls()
    blind = next(sid for s in sites["sites"] if s["group"] != "tuning" for sid in s["strips"])
    monkeypatch.setattr(script, "POP", tmp_path)
    monkeypatch.setattr(script, "LISTS", ())
    monkeypatch.setattr(script, "target_strips", lambda: [blind])
    with pytest.raises(ValueError):
        script.population(None)


def test_better_rank_keeps_each_lists_first_candidates():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import halfcal as script

    first = np.array([3.0, 2.0, 1.0, 0.0])
    second = np.array([0.0, 1.0, 2.0, 3.0])
    order = np.argsort(-script.fused(first, second)).tolist()
    assert set(order[:2]) == {0, 3}, "each list's best candidate comes first"


def test_exchangeable_ground_gives_the_nominal_rate_on_the_other_half():
    """The check the item asks for, on a fake strip with one distribution all over: the realised rate follows the
    nominal one, and an extrapolating tail is not needed to reach it."""
    rng = np.random.default_rng(0)
    n = 20000
    raw = rng.exponential(1.0, n)
    colours = rng.integers(0, 2, n)
    branches = np.array(["bright"] * n)
    areas = (100.0, 100.0)
    cals = hc.cross_fit(branches, raw, colours, areas)
    s = hc.score_by_other(cals, branches, raw, np.zeros(n), colours)
    for lv in (0.0, 0.5, 1.0):
        rate = float((s >= lv).sum()) / 200.0
        assert rate == pytest.approx(10.0**-lv, rel=0.25)

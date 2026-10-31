"""The honest tail of plan item 15: the split, the cross-fit and the cap. No data on disk needed."""

import copy
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

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


def fake_list(n=400):
    """A strip's list with ties in the score, in file order that is not score order."""
    rng = np.random.default_rng(1)
    raw = rng.exponential(1.0, n)
    rows = rng.integers(0, 40000, n).astype(float)
    cols = rng.integers(0, 40000, n).astype(float)
    branches = rng.choice(["bright", "sheet", "shadow"], n)
    cands = [
        {
            "row": float(r),
            "col": float(c),
            "score": round(float(x), 1),
            "branch": str(b),
            "grade": "needs second look",
            "extra": {"raw_score": float(x)},
        }
        for r, c, x, b in zip(rows, cols, raw, branches, strict=True)
    ]
    colours = hc.colour(rows, cols, 0.25)
    rate, below = hc.rates_by_other(hc.cross_fit(branches, raw, colours, (20.0, 25.0)), branches, raw, colours)
    return cands, raw, branches, colours, rate, below


def test_the_rate_is_the_score_without_its_tie_break_and_the_cap_says_below_only():
    _, raw, branches, colours, rate, below = fake_list()
    cals = hc.cross_fit(branches, raw, colours, (20.0, 25.0))
    s = hc.score_by_other(cals, branches, raw, np.zeros(len(raw)), colours)
    inside = np.isfinite(rate)
    assert inside.any() and (~inside).any()
    assert s[inside] == pytest.approx(-np.log10(rate[inside]) + hc.TIE_BREAK * raw[inside])
    assert (s[~inside] >= [hc.cap_of(25.0 if k == 0 else 20.0) for k in colours[~inside]]).all()
    assert np.isnan(below[inside]).all()
    assert below[~inside].tolist() == [1.0 / (25.0 if k == 0 else 20.0) for k in colours[~inside]]


def test_a_branch_with_no_curve_on_the_other_colour_says_below_not_a_rate():
    cals = hc.cross_fit(np.array(["bright"]), np.array([1.0]), np.array([0]), (4.0, 5.0))
    rate, below = hc.rates_by_other(cals, np.array(["sheet"]), np.array([9.0]), np.array([1]))
    assert np.isnan(rate[0]) and below[0] == 1.0 / 4.0


def test_the_order_and_every_other_field_are_identical_with_and_without_the_column():
    from landers.models.run import top_candidates
    from landers.score import _sorted_candidates as score_ranked
    from landers.search.export import rank_top
    from landers.search.persistence import survivors

    cands, _, _, _, rate, below = fake_list()
    before = copy.deepcopy(cands)
    after = hc.with_rate_column(cands, rate, below)
    assert cands == before, "the input is not touched"
    assert hc.only_the_column_differs(before, after)
    assert [c["row"] for c in after] == [c["row"] for c in before]

    def strip(rows):
        return [{k: v for k, v in c.items() if k not in (hc.RATE_FIELD, hc.BELOW_FIELD)} for c in rows]

    entry = {"valid_area_km2": 45.0}
    assert strip(top_candidates(after, 400)) == top_candidates(before, 400)
    assert strip(score_ranked({"candidates": after})) == score_ranked({"candidates": before})
    assert strip(survivors({**entry, "candidates": after}, 8.0)) == survivors({**entry, "candidates": before}, 8.0)
    assert rank_top(after, 400) == rank_top(before, 400), "the export keeps its own fields"


def test_any_other_change_to_a_row_is_caught():
    cands, _, _, _, rate, below = fake_list(20)
    after = hc.with_rate_column(cands, rate, below)
    after[3]["score"] += 1.0
    assert not hc.only_the_column_differs(cands, after)
    after = hc.with_rate_column(cands, rate, below)
    after[0], after[1] = after[1], after[0]
    assert not hc.only_the_column_differs(cands, after)


def test_the_column_is_written_as_a_number_or_null_and_as_valid_json():
    cands, _, _, _, rate, below = fake_list(200)
    rows = hc.with_rate_column(cands, rate, below)
    assert json.loads(json.dumps(rows, allow_nan=False)) == rows
    assert all((c[hc.RATE_FIELD] is None) != (c[hc.BELOW_FIELD] is None) for c in rows)


def test_a_review_prompt_does_not_carry_the_rate():
    from landers.models.spark import EXTRA_WHITELIST

    assert hc.RATE_FIELD not in EXTRA_WHITELIST and hc.BELOW_FIELD not in EXTRA_WHITELIST


def test_the_join_refuses_a_candidate_outside_the_population_and_two_raws_at_one_place():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import halfcal as script

    s = SimpleNamespace(
        sid="x",
        row=np.array([1.0, 2.0]),
        col=np.array([3.0, 4.0]),
        branch=np.array(["bright", "sheet"]),
        raw=np.array([5.0, 6.0]),
    )
    assert script.raws_of(s, [{"row": 2.0, "col": 4.0, "branch": "sheet"}]).tolist() == [6.0]
    with pytest.raises(KeyError):
        script.raws_of(s, [{"row": 2.0, "col": 4.0, "branch": "bright"}])
    s.row, s.col = np.array([1.0, 1.0]), np.array([3.0, 3.0])
    s.branch = np.array(["bright", "bright"])
    with pytest.raises(ValueError):
        script.raws_of(s, [])


def test_the_column_refuses_a_list_holding_a_blind_strip(monkeypatch, tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import halfcal as script
    import rerank as rr

    sites, _, _ = rr.controls()
    blind = next(sid for s in sites["sites"] if s["group"] != "tuning" for sid in s["strips"])
    p = tmp_path / "list.json"
    p.write_text(json.dumps({"strips": {blind: {"candidates": []}}}))
    (tmp_path / "results.json").write_text(json.dumps({"top20_makeup": {}}))
    monkeypatch.setattr(script, "OUT", tmp_path)
    with pytest.raises(ValueError):
        script.rate_column(SimpleNamespace(lists=[str(p)]))


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

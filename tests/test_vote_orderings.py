"""The orderings of docs/proposals/vote-order-v1.md, on made-up votes."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def vo():
    sys.path.insert(0, str(ROOT / "experiments"))
    spec = importlib.util.spec_from_file_location("vote_orderings", ROOT / "experiments" / "vote_orderings.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rec(*votes):
    return {"votes": [{"verdict": v, "confidence": c} for v, c in votes]}


def test_a_moves_first_vote_hardware_ahead_and_keeps_order(vo):
    recs = {1: rec(("natural", 0.9)), 2: rec(("hardware", 0.1)), 4: rec(("hardware", 0.9)), 5: rec(("unsure", 0.5))}
    assert vo.order_a(list(range(6)), recs) == [2, 4, 0, 1, 3, 5]


def test_a_uses_the_first_vote_only_and_ignores_off_schema(vo):
    later = rec(("natural", 0.8), ("hardware", 0.9), ("hardware", 0.9))
    off = {"votes": [{"verdict": "hardware", "confidence": 0.9, "off_schema": True}]}
    assert vo.order_a([0, 1, 2], {1: later, 2: off}) == [0, 1, 2]


def test_a_does_nothing_below_the_voted_depth(vo):
    depths = list(range(vo.TOP + 2))
    assert vo.order_a(depths, {vo.TOP + 1: rec(("hardware", 0.9))}) == depths


def test_signed_is_the_mean_over_votes(vo):
    assert vo.signed(rec(("hardware", 0.6))) == pytest.approx(0.6)
    assert vo.signed(rec(("natural", 0.9), ("natural", 0.6), ("unsure", 0.9))) == pytest.approx(-0.5)
    assert vo.signed({"votes": [{"verdict": "hardware", "confidence": 0.9, "off_schema": True}]}) == 0.0


def test_b_scales_depth_by_the_vote(vo):
    # depth 3 (counted from 1: 4) with hardware at full confidence has key 1, and ties go to the better depth; natural at full
    # confidence at the top has key 4
    assert vo.order_b(list(range(6)), {3: rec(("hardware", 1.0)), 0: rec(("natural", 1.0))}) == [3, 1, 2, 0, 4, 5]


def test_b_with_no_votes_is_the_combined_order(vo):
    assert vo.order_b(list(range(5)), {}) == list(range(5))


def test_relist_scores_sort_back_to_the_order(vo):
    rows = [{"name": i, "score": 0.0} for i in range(4)]
    order = [2, 0, 3, 1]
    out = vo.relist(rows, order)
    assert [r["name"] for r in sorted(out, key=lambda r: -r["score"])] == order

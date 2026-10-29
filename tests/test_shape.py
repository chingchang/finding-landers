import json

import numpy as np

from landers import shape
from landers.detect import Candidate
from landers.score import _auc, feature_separation


def test_disc_is_circular_and_filled():
    lab = np.zeros((40, 40), int)
    yy, xx = np.mgrid[:40, :40]
    lab[(yy - 20) ** 2 + (xx - 20) ** 2 <= 8**2] = 1
    z = lab.astype(float) * 5.0
    g = shape.gradient_magnitude(z)
    sl = (slice(12, 29), slice(12, 29))
    f = shape.component_features(lab, 1, z, g, sl)
    assert f["circularity"] > 0.6 and f["fill"] > 0.6 and f["elongation"] < 0.1 and f["edge_sharpness"] > 0


def test_bar_is_elongated():
    lab = np.zeros((40, 40), int)
    lab[18:22, 5:35] = 1
    z = lab.astype(float) * 5.0
    f = shape.component_features(lab, 1, z, shape.gradient_magnitude(z), (slice(18, 22), slice(5, 35)))
    assert f["elongation"] > 0.5 and f["fill"] == 1.0


def test_tile_ranks_and_auc():
    assert shape.tile_ranks([3.0, 9.0, 5.0]) == [2, 0, 1]
    assert _auc([5, 6], [1, 2]) == 1.0 and _auc([1, 2], [5, 6]) == 0.0 and _auc([3], [3]) == 0.5


def test_feature_separation_groups_by_kind_and_branch():
    truths = [{"tile": "t", "row": 10, "col": 10, "kind": "blob_shadow", "size_m": 2}]
    dets = [
        {"tile": "t", "row": 11, "col": 10, "score": 1, "branch": "bright", "features": {"circularity": 0.9}},
        {"tile": "t", "row": 500, "col": 500, "score": 1, "branch": "bright", "features": {"circularity": 0.3}},
        {"tile": "t", "row": 600, "col": 600, "score": 1, "branch": "bright", "features": {"circularity": 0.4}},
    ]
    r = feature_separation(dets, truths, 5.0)
    assert r["rows"][0]["kind"] == "blob_shadow" and r["rows"][0]["auc"]["circularity"] == 1.0


# ---------------------------------------------------------------- shadow-side features


def _object_with_dark(dark_side: int, run: int = 8, size: int = 101):
    """A bright 3 px-radius object at the centre of a flat z map, with a dark run of ``run`` px starting
    2 px past its edge, on the +col side (dark_side=+1) or the -col side (-1)."""
    z = np.zeros((size, size), float)
    yy, xx = np.mgrid[:size, :size]
    c = size // 2
    z[(yy - c) ** 2 + (xx - c) ** 2 <= 9] = 8.0
    start = c + dark_side * 5
    cols = range(start, start + dark_side * run, dark_side)
    for k in cols:
        z[c - 3 : c + 4, k] = -4.0
    return z


def test_band_profile_reads_along_the_ray():
    z = np.zeros((50, 50))
    z[25, 30:35] = -3.0
    prof = shape.band_profile(z, 25, 25, 0.0, 1.0, 0, 1, 12)  # along +col, 1 px wide, distances 1..12
    assert prof[4] == -3.0 and prof[0] == 0.0 and len(prof) == 12
    off = shape.band_profile(z, 25, 25, 0.0, 1.0, 0, 20, 40)  # runs off the array: NaN past the edge
    assert np.isnan(off[-1])


def test_two_sided_is_positive_for_shadow_on_anti_sun_side():
    # sun towards -col: shadows fall towards +col, so (drow, dcol) = (0, +1)
    z = _object_with_dark(+1)
    f = shape.shadow_features(z, 50, 50, 3.0, 0.0, 1.0, reach_px=14, scale_m=0.25, incidence_deg=50.0)
    assert f["anti_sun_min_z"] == -4.0 and f["sun_min_z"] == 0.0 and f["two_sided"] == 4.0
    assert f["shadow_run_px"] == 8
    assert abs(f["shadow_height_m"] - 8 * 0.25 / np.tan(np.radians(50.0))) < 0.02
    # the same dark on the sun side: a two-sided test must reject it
    g = shape.shadow_features(_object_with_dark(-1), 50, 50, 3.0, 0.0, 1.0, 14, 0.25, 50.0)
    assert g["two_sided"] == -4.0 and g["shadow_run_px"] == 0 and g["shadow_height_m"] == 0.0


def test_isolation_and_saturated_count():
    pts = [(0.0, 0.0), (0.0, 10.0), (500.0, 500.0)]
    assert shape.isolation(pts) == [10.0, 10.0, shape.ISOLATION_CAP_PX]
    assert shape.isolation([(1.0, 1.0)]) == [shape.ISOLATION_CAP_PX]
    lab = np.zeros((6, 6), int)
    lab[1:4, 1:4] = 1
    sat = np.zeros((6, 6), bool)
    sat[2, 2] = sat[2, 3] = sat[5, 5] = True
    assert shape.saturated_count(sat, lab, 1, (slice(1, 4), slice(1, 4))) == 2


# ---------------------------------------------------------------- rules


def _rules(tmp_path):
    d = {
        "version": "shape_test",
        "basis": "test",
        "rules": [
            {
                "name": "shadow",
                "branches": ["bright", "shadow"],
                "conditions": [
                    {"feature": "two_sided", "op": ">=", "threshold": 2.0},
                    {"feature": "shadow_height_m", "op": "in", "threshold": [0.5, 3.0]},
                ],
                "false_alarm_pass_fraction": 0.01,
                "gain": 2.0,
            },
            {
                "name": "isolated",
                "branches": ["bright"],
                "conditions": [{"feature": "isolation_px", "op": ">=", "threshold": 100}],
                "gain": 0.5,
            },
        ],
    }
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(d))
    return shape.ShapeRules.load(p)


def test_rules_add_gain_only_when_passed(tmp_path):
    rules = _rules(tmp_path)
    look = "needs second look"
    passes = Candidate(1, 1, 0.0, "bright", look, 9, {"two_sided": 3.0, "shadow_height_m": 1.2, "isolation_px": 200})
    fails = Candidate(2, 2, 0.0, "bright", look, 9, {"two_sided": -1.0, "shadow_height_m": 0.0, "isolation_px": 20})
    tall = Candidate(5, 5, 0.0, "bright", look, 9, {"two_sided": 5.0, "shadow_height_m": 6.0, "isolation_px": 20})
    other = Candidate(3, 3, 0.0, "dark", look, 9, {"two_sided": 9.0, "shadow_height_m": 1.0})
    missing = Candidate(4, 4, 0.0, "bright", look, 9, {"two_sided": 9.0})  # no height: the rule cannot be judged
    out = shape.apply_rules([passes, fails, tall, other, missing], rules)
    assert out[0].score == 2.5 and out[0].extra["shape_pass"] == ["shadow", "isolated"]
    assert out[1].score == 0.0 and "shape_pass" not in out[1].extra
    assert out[2].score == 0.0  # a 6 m shadow is not a lander's; both conditions must hold
    assert out[3].score == 0.0 and out[4].score == 0.0
    # the same adjustment on a candidates-file dict, as scripts/rescore.py applies it
    d = {
        "row": 1,
        "col": 1,
        "score": -0.5,
        "branch": "shadow",
        "extra": {"two_sided": 2.0, "shadow_height_m": 0.5, "isolation_px": 300},
    }
    r = shape.apply_rules_json(d, rules)
    assert r["score"] == 1.5 and r["extra"]["shape_pass"] == ["shadow"]  # isolation rule is bright-only
    assert d["score"] == -0.5  # input untouched

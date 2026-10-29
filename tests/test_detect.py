import dataclasses

import numpy as np
import pytest

from landers import config, detect, geo
from landers.label import StripLabel
from landers.strip import Strip, Window
from tests.conftest import needs_data, site_strips


def fake_label(**over) -> StripLabel:
    base = dict(
        observation_id="X",
        rationale="",
        lines=4000,
        samples=4000,
        scale_m=0.25,
        projection="EQUIRECTANGULAR",
        center_lat=0.0,
        center_lon=180.0,
        line_offset=0.0,
        sample_offset=0.0,
        map_resolution=237102.0,
        radius_m=3396190.0,
        min_lat=0,
        max_lat=0,
        west_lon=0,
        east_lon=0,
        incidence_deg=50.0,
        sub_solar_azimuth_deg=170.0,
        north_azimuth_deg=270.0,
        solar_longitude_deg=0.0,
        start_time="",
    )
    base.update(over)
    return StripLabel(**base)


def synthetic_tile(seed=0, size=512, bright_at=(200, 300), dark_scar_at=(400, 120)):
    rng = np.random.default_rng(seed)
    img = 500 + 20 * rng.standard_normal((size, size)).astype(np.float32)
    lbl = fake_label()
    drow, dcol = geo.shadow_direction(lbl)
    shadow = geo.shadow_length_px(lbl, 1.5)
    r, c = bright_at
    yy, xx = np.mgrid[:size, :size]
    img[(yy - r) ** 2 + (xx - c) ** 2 <= 3**2] += 250  # a 1.5 m bright object
    sr, sc = r + drow * (shadow / 2 + 3), c + dcol * (shadow / 2 + 3)
    for t in np.linspace(0, 1, 40):  # its shadow, a dark streak along the shadow direction
        pr, pc = r + drow * (3 + t * shadow), c + dcol * (3 + t * shadow)
        img[int(round(pr)) - 1 : int(round(pr)) + 2, int(round(pc)) - 1 : int(round(pc)) + 2] -= 150
    r2, c2 = dark_scar_at
    img[(yy - r2) ** 2 + (xx - c2) ** 2 <= 12**2] -= 120  # a 6 m dark scar
    data = np.clip(img, 1, 1021).astype(np.uint16)
    valid = np.ones_like(data, dtype=bool)
    valid[:, :40] = False  # a no-data margin like the slanted footprint edge
    data[:, :40] = 0
    return Window(1000, 2000, data, valid), lbl, (sr, sc)


def test_branches_find_planted_objects():
    win, lbl, _ = synthetic_tile()
    cands = detect.detect_tile(win, lbl, detect.DetectorConfig())
    by_branch = {}
    for c in cands:
        by_branch.setdefault(c.branch, []).append(c)
    shadow = [c for c in by_branch.get("shadow", []) if abs(c.row - 1200) < 3 and abs(c.col - 2300) < 3]
    assert shadow, [(c.branch, c.row, c.col) for c in cands]
    assert 0 < shadow[0].extra["shadow_len_px"] <= shadow[0].extra["shadow_len_max_px"] + 6
    dark = [c for c in by_branch.get("dark", []) if abs(c.row - 1400) < 3 and abs(c.col - 2120) < 3]
    assert dark
    assert all(c.col >= 2000 + 40 for c in cands)  # nothing on the no-data margin
    assert all(c.grade == "needs second look" for c in cands)


def test_shadow_side_features_on_planted_object():
    win, lbl, _ = synthetic_tile()
    cands = detect.detect_tile(win, lbl, detect.DetectorConfig())
    (c,) = [c for c in cands if c.branch in ("bright", "shadow") and abs(c.row - 1200) < 3 and abs(c.col - 2300) < 3]
    e = c.extra
    assert e["two_sided"] > 1.0 and e["anti_sun_min_z"] < -2.0 and e["sun_min_z"] > -2.0
    assert 0.5 < e["shadow_height_m"] < 3.0 and e["shadow_run_px"] > 0
    assert e["isolation_px"] > 50 and e["saturated_px"] == 0
    assert all("isolation_px" in k.extra and "two_sided" in k.extra for k in cands if k.branch == "dark_compact")


def test_saturated_object_is_data_not_a_hole():
    """v0.1 masked saturated pixels as no-data and lost saturated hardware; v0.2 keeps them."""
    rng = np.random.default_rng(3)
    size = 512
    img = 500 + 20 * rng.standard_normal((size, size)).astype(np.float32)
    data = np.clip(img, 1, 1021).astype(np.uint16)
    yy, xx = np.mgrid[:size, :size]
    data[(yy - 250) ** 2 + (xx - 250) ** 2 <= 3**2] = 1023  # a 1.5 m saturated object
    win = Window(0, 0, data, np.ones_like(data, dtype=bool) & (data < 1022))
    lbl = fake_label()
    found = [
        c
        for c in detect.detect_tile(win, lbl, detect.DetectorConfig())
        if abs(c.row - 250) < 3 and abs(c.col - 250) < 3
    ]
    assert found and found[0].branch in ("bright", "shadow") and found[0].extra["saturated_px"] >= 20
    legacy = detect.detect_tile(win, lbl, detect.DetectorConfig(saturated_is_data=False))
    assert not [c for c in legacy if c.branch in ("bright", "shadow") and abs(c.row - 250) < 3 and abs(c.col - 250) < 3]


def test_finish_tile_rules_match_rescore(tmp_path):
    import json

    from landers.shape import ShapeRules, apply_rules_json

    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "version": "shape_t",
                "rules": [
                    {
                        "name": "shadow",
                        "branches": ["bright", "shadow"],
                        "conditions": [{"feature": "two_sided", "op": ">=", "threshold": 1.0}],
                        "gain": 1.5,
                    }
                ],
            }
        )
    )
    win, lbl, _ = synthetic_tile()
    cfg = detect.DetectorConfig(shape_rules=str(rules_path))
    raw = detect.detect_tile(win, lbl, cfg)
    ruled = detect.finish_tile(raw, cfg, None, detect.load_shape_rules(cfg))
    again = [apply_rules_json(c.to_json(), ShapeRules.load(rules_path)) for c in raw]
    assert [round(c.score, 3) for c in ruled] == [round(float(c["score"]), 3) for c in again]
    assert any(c.extra.get("shape_pass") for c in ruled)


def test_no_shadow_branch_when_sun_is_high():
    win, lbl, _ = synthetic_tile()
    lbl = dataclasses.replace(lbl, incidence_deg=31.0)
    cands = detect.detect_tile(win, lbl, detect.DetectorConfig())
    assert not [c for c in cands if c.branch == "shadow"]
    assert [c for c in cands if c.branch == "bright" and abs(c.row - 1200) < 3]


def test_dedupe_keeps_best():
    a = detect.Candidate(10, 10, 5.0, "bright", "needs second look", 9)
    b = detect.Candidate(12, 11, 7.0, "shadow", "needs second look", 9)
    c = detect.Candidate(100, 100, 1.0, "dark", "needs second look", 200)
    kept = detect.dedupe([a, b, c])
    assert [k.branch for k in kept] == ["shadow", "dark"]


@needs_data
def test_label_shadow_direction_agrees_with_real_ground():
    """On the Viking 1 strip, bright rocks must have dark patches on the label's shadow side far more
    often than on the opposite side. Pins the PDS azimuth convention used in geo.shadow_direction."""
    ids = site_strips("viking1")
    if not ids or config.find_strip(ids[0]) is None:
        pytest.skip("Viking 1 strip not on disk")
    strip = Strip.open(ids[0])
    r, c = strip.shape[0] // 2, strip.shape[1] // 2
    win = strip.read(r - 1024, r + 1024, c - 1024, c + 1024)
    along, against = detect.shadow_direction_evidence(win, strip.label, detect.DetectorConfig())
    assert along > 20, (along, against)
    assert along > 2 * against, (along, against)


def test_sheet_and_dark_compact_branches():
    rng = np.random.default_rng(1)
    size = 1024
    img = 500 + 20 * rng.standard_normal((size, size)).astype(np.float32)
    lbl = fake_label()
    yy, xx = np.mgrid[:size, :size]
    # a flat bright ellipse 16 m x 8 m (64 x 32 px): a parachute
    img[((yy - 300) / 32.0) ** 2 + ((xx - 400) / 16.0) ** 2 <= 1.0] *= 1.35
    # a dark disc 2.5 m (10 px) across: a heat shield
    img[(yy - 700) ** 2 + (xx - 650) ** 2 <= 5**2] *= 0.6
    data = np.clip(img, 1, 1021).astype(np.uint16)
    win = Window(0, 0, data, np.ones_like(data, dtype=bool))
    cands = detect.detect_tile(win, lbl, detect.DetectorConfig())
    sheets = [c for c in cands if c.branch == "sheet" and abs(c.row - 300) < 8 and abs(c.col - 400) < 8]
    assert sheets, [(c.branch, round(c.row), round(c.col)) for c in cands]
    assert 10 < sheets[0].extra["extent_m"] < 25
    darks = [c for c in cands if c.branch == "dark_compact" and abs(c.row - 700) < 4 and abs(c.col - 650) < 4]
    assert darks, [(c.branch, round(c.row), round(c.col)) for c in cands]
    assert darks[0].extra["fill"] >= 0.45


def test_injected_objects_are_recovered_on_synthetic_ground():
    from landers import inject as inj
    from landers.score import recall_at_false_alarm_rate

    rng = np.random.default_rng(2)
    size = 2048
    data = np.clip(500 + 20 * rng.standard_normal((size, size)), 1, 1021).astype(np.uint16)
    win = Window(0, 0, data, np.ones_like(data, dtype=bool))
    lbl = fake_label()
    injected, objs = inj.inject(win, lbl, inj.InjectConfig(), rng, per_kind=4)
    assert len(objs) == 12 and {o.kind for o in objs} == set(inj.KINDS)
    assert injected.data.shape == win.shape and (injected.data != win.data).any()
    cands = detect.detect_tile(injected, lbl, detect.DetectorConfig())
    dets = [{"tile": "t", "row": c.row, "col": c.col, "score": c.score, "branch": c.branch} for c in cands]
    truths = [dict(o.to_json(), tile="t") for o in objs]
    area = size * size * lbl.scale_m**2 / 1e6
    r = recall_at_false_alarm_rate(dets, truths, area, radius_px=20.0, fa_per_km2=2.0)
    assert r["recall_overall"] >= 0.75, r
    kinds_found = {row["kind"] for row in r["rows"] if row["found"]}
    assert kinds_found == set(inj.KINDS), r["rows"]

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from landers import config, detect, geo, sheets
from landers.strip import Strip, Window
from tests.conftest import needs_data, site_strips

ROOT = Path(__file__).resolve().parent.parent


def test_select_radius_and_order():
    entry = {
        "candidates": [
            {"row": 100, "col": 100, "score": 1.0, "branch": "bright"},
            {"row": 110, "col": 100, "score": 5.0, "branch": "sheet"},
            {"row": 9000, "col": 100, "score": 9.0, "branch": "shadow"},  # outside 1 km at 25 cm/px
        ]
    }
    picks = sheets.select(entry, 0.25, 100, 100, radius_m=1000, top_n=10)
    assert [p.branch for p in picks] == ["sheet", "bright"]
    assert picks[0].rank == 1 and abs(picks[0].distance_m - 2.5) < 1e-9
    assert picks[0].shadow is None and picks[0].shadow_rank is None
    assert sheets.count_within(entry, 0.25, 100, 100, 1000) == 2
    s = sheets.summarise(sheets.select(entry, 0.25, 100, 100, radius_m=1000, top_n=1), None)
    assert s == {
        "n": 1,
        "branches": {"sheet": 1},
        "score_top": 5.0,
        "score_last": 5.0,
        "in_grid": 0,
        "nearest_m": 2,  # 2.5 m rounds to even
        "nearest_rank": 1,
    }
    assert sheets.summarise([], None) == {"n": 0}


def test_rank_picks_carries_both_rankings():
    entry = {
        "candidates": [
            {"row": 100, "col": 100, "score": 1.0, "branch": "bright"},  # 0: lowest score, best shadow
            {"row": 110, "col": 100, "score": 5.0, "branch": "sheet"},  # 1: top score, no shadow test (edge)
            {"row": 120, "col": 100, "score": 3.0, "branch": "dark"},  # 2
        ]
    }
    shadows = {0: sheets.ShadowTest(4.0, -3.0, 0.0), 1: None, 2: sheets.ShadowTest(-4.0, -2.0, -1.0)}
    inside = sheets.within(entry, 0.25, 100, 100, 1000)
    picks, shadow_picks = sheets.rank_picks(entry, inside, 2, shadows)
    assert [(p.rank, p.shadow_rank) for p in picks] == [(1, None), (2, 2)]
    assert [(p.rank, p.shadow_rank) for p in shadow_picks] == [(3, 1), (2, 2)]
    assert shadow_picks[0].shadow.score == 3.0 and shadow_picks[1].shadow.score == -5.0
    assert shadow_picks[0].shadow.to_json() == {"z_centre": 4.0, "z_anti": -3.0, "z_sun": 0.0, "score": 3.0}


def test_anchor_falls_back_to_site_position():
    site = {
        "lat": 1.0,
        "lon_e": 2.0,
        "pieces_refined": [
            {"piece": "lander", "lat": 1.5, "lon_e": 2.5, "precision_m": 60},
            {"piece": "backshell", "lat": None, "lon_e": None},
        ],
    }
    assert sheets.anchor_for(site, "lander")[:3] == (1.5, 2.5, 60.0)
    lat, lon, prec, how = sheets.anchor_for(site, "backshell")
    assert (lat, lon, prec) == (1.0, 2.0, 1000.0) and "published" in how


def test_stretch_handles_empty():
    a = np.zeros((8, 8), np.uint16)
    assert sheets._stretch(a, np.zeros((8, 8), bool)).max() == 0
    assert sheets.stretch_limits([(a, np.zeros((8, 8), bool))]) is None
    assert sheets.apply_stretch(a, np.ones((8, 8), bool), None).max() == 0


def test_one_stretch_for_the_whole_sheet():
    """Stretched on their own, a dim crop and a bright crop both reach white; under the sheet's one
    stretch the dim crop stays dim, so brightness can be compared across thumbnails."""
    rng = np.random.default_rng(0)
    v = np.ones((64, 64), bool)
    dim = (300 + 10 * rng.standard_normal((64, 64))).astype(np.uint16)
    bright = (300 + 10 * rng.standard_normal((64, 64))).astype(np.uint16)
    bright[28:36, 28:36] = 900  # a 2 m object far above the ground
    assert sheets._stretch(dim, v).max() == 255 and sheets._stretch(bright, v).max() == 255
    limits = sheets.stretch_limits([(dim, v), (bright, v)])
    assert 260 < limits[0] < 300 and limits[1] > 500
    assert sheets.apply_stretch(dim, v, limits).max() < 80
    assert sheets.apply_stretch(bright, v, limits).max() == 255


def _crop_with(sun_az_deg: float, streak_side: str | None, size: int = 128, r_obj: float = 3.0):
    """A bright 1.5 m disc on flat noisy ground with a dark streak on the anti-sun side, the sun side,
    both, or neither; returns the arguments of ``shadow_test``."""
    from tests.test_detect import fake_label

    lbl = fake_label(sub_solar_azimuth_deg=sun_az_deg, incidence_deg=50.0)
    drow, dcol = geo.shadow_direction(lbl)
    lmax = sheets.shadow_probe_px(lbl)
    rng = np.random.default_rng(1)
    img = 500 + 15 * rng.standard_normal((size, size)).astype(np.float32)
    c = size // 2
    yy, xx = np.mgrid[:size, :size]
    img[(yy - c) ** 2 + (xx - c) ** 2 <= r_obj**2] += 300
    sides = {"anti": [+1], "sun": [-1], "both": [+1, -1], None: []}[streak_side]
    for sign in sides:
        for t in np.linspace(r_obj + 1, r_obj + 7, 30):  # a 1.5 m object's shadow at 50 deg: 7 px
            pr, pc = c + sign * drow * t, c + sign * dcol * t
            img[int(round(pr)) - 1 : int(round(pr)) + 2, int(round(pc)) - 1 : int(round(pc)) + 2] = 350
    return np.clip(img, 1, 1021).astype(np.uint16), np.ones((size, size), bool), r_obj, drow, dcol, lmax


@pytest.mark.parametrize("sun_az", [170.0, 268.0, 45.0])
def test_shadow_test_is_two_sided(sun_az):
    cases = {side: sheets.shadow_test(*_crop_with(sun_az, side)) for side in ("anti", "sun", "both", None)}
    for side, t in cases.items():
        assert t is not None and t.z_centre > 5, (side, t)
    anti, sun, both, none = (cases[k] for k in ("anti", "sun", "both", None))
    # a raised object: shadow on the anti-sun side only, and nothing dark on the sun side
    assert anti.z_anti < -3 and anti.z_sun > -1.5 and anti.score > 3, anti
    # a trough or crater wall: bright with its dark side toward the sun
    assert sun.z_sun < -3 and sun.z_anti > -1.5 and sun.score < 0, sun
    # dark on both sides earns nothing over dark on neither
    assert both.score < anti.score - 2 and abs(both.score - none.score) < 1.5, (both, none)
    assert none.score < 1.5, none


def test_shadow_test_needs_ground_and_sun():
    data, v, r_obj, drow, dcol, lmax = _crop_with(170.0, "anti")
    assert sheets.shadow_test(data, np.zeros_like(v), r_obj, drow, dcol, lmax) is None
    from tests.test_detect import fake_label

    assert sheets.shadow_probe_px(fake_label(incidence_deg=30.0)) is None
    assert 10 < sheets.shadow_probe_px(fake_label(incidence_deg=50.0)) < 16  # 3 m at 50 deg, 25 cm/px
    assert sheets.object_radius_px(0) == 2.0 and sheets.object_radius_px(10**6) == 16.0


@needs_data
def test_shadow_test_sign_agrees_with_real_ground():
    """Bright rocks on the Viking 1 strip must be darker on the label's anti-sun side than on the sun
    side far more often than not. Pins the sign of the test to the convention the detector checks."""
    ids = site_strips("viking1")
    if not ids or config.find_strip(ids[0]) is None:
        pytest.skip("Viking 1 strip not on disk")
    strip = Strip.open(ids[0])
    r, c = strip.shape[0] // 2, strip.shape[1] // 2
    win = strip.read(r - 1024, r + 1024, c - 1024, c + 1024)
    cands = [x.to_json() for x in detect.detect_tile(win, strip.label, detect.DetectorConfig())]
    idx = [i for i, x in enumerate(cands) if x["branch"] in ("bright", "shadow")]
    tests = sheets.shadow_tests(strip, cands, idx, 128)
    vals = [t for t in tests.values() if t is not None]
    assert len(vals) >= 10
    darker_on_shadow_side = sum(1 for t in vals if t.z_anti < t.z_sun)
    assert darker_on_shadow_side > 0.6 * len(vals), (darker_on_shadow_side, len(vals))


def test_grid_layout_numbers_tiles_like_the_grid_renderer():
    # 1500 m at 0.25 m/px is 6000 px: 12 x 12 tiles of 512 (6144 px), centre at pixel 3072 of the window
    lay = sheets.grid_layout(10000, 20000, 0.25, 1500, 512)
    assert (lay.n, lay.size, lay.row0, lay.col0) == (12, 6144, 10000 - 3072, 20000 - 3072)
    assert lay.tile_of(10000, 20000) == 6 * 12 + 6 + 1  # the centre pixel starts tile row 6, column 6
    assert lay.tile_of(10000 - 1, 20000 - 1) == 5 * 12 + 5 + 1
    assert lay.tile_of(lay.row0, lay.col0) == 1
    assert lay.tile_of(lay.row0 + lay.size - 1, lay.col0 + lay.size - 1) == 144
    assert lay.tile_of(lay.row0 - 1, 20000) is None and lay.tile_of(10000, lay.col0 + lay.size) is None
    # near the image origin the window is clipped at 0, as Strip.read clips it, and tile 1 starts there
    near = sheets.grid_layout(100, 100, 0.25, 1500, 512)
    assert (near.row0, near.col0) == (0, 0) and near.tile_of(0, 0) == 1


def test_draw_map_marks_every_pick_and_the_grid():
    rng = np.random.default_rng(0)
    data = rng.integers(200, 400, (300, 300)).astype(np.uint16)
    w = Window(1000, 2000, data, np.ones(data.shape, bool), step=8)  # 2400 image px, 300 map px
    grid = sheets.grid_layout(2200, 3200, 0.25, 600, 800)  # 3 x 3 tiles of 800 image px: the whole map
    assert (grid.row0, grid.col0, grid.n) == (1000, 2000, 3)
    picks = [
        sheets.Pick(1, 2200, 3200, 5.0, "bright", 0.0, 9, {}),
        sheets.Pick(2, 1000 + 8 * 20, 2000 + 8 * 250, 4.0, "dark", 500.0, 9, {}),
    ]
    shadow_picks = [sheets.Pick(7, 1000 + 8 * 250, 2000 + 8 * 40, 1.0, "bright", 900.0, 9, {}, None, 1)]
    im = sheets.draw_map(w, 0.25, 2200, 3200, 300, 60, picks, grid, "test", shadow_picks)
    assert im.size == (300, 300 + 56)
    px = np.asarray(im)
    # a yellow mark near each pick, in map pixels: pick 1 at ((3200-2000)/8, (2200-1000)/8) = (150, 150)
    for x, y in ((150, 150), (250, 20)):
        patch = px[max(y - 8, 0) : y + 8, max(x - 8, 0) : x + 16]
        yellow = (patch[..., 0] > 200) & (patch[..., 1] > 200) & (patch[..., 2] < 60)
        assert yellow.any()
    # a magenta mark at the shadow pick, map (40, 250)
    patch = px[240:262, 30:52]
    assert ((patch[..., 0] == 255) & (patch[..., 1] == 120) & (patch[..., 2] == 255)).any()
    # grid tile outlines are brown: nine 100 px squares on the map
    assert grid.tile_of(2200, 3200) == 1 * 3 + 1 + 1 == 5
    brown = (px[..., 0] == 90) & (px[..., 1] == 70) & (px[..., 2] == 0)
    assert brown.sum() > 1500


def _run_script(tmp_path, run: dict, *extra: str) -> dict:
    (tmp_path / "candidates_t.json").write_text(json.dumps(run))
    out = tmp_path / "sheets"
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "contact_sheets.py"),
            str(tmp_path / "candidates_t.json"),
            "--site",
            "viking1",
            "--thumb-px",
            "64",
            "--out",
            str(out),
            *extra,
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads((out / "suggestions.json").read_text())


@pytest.mark.skipif(not (ROOT / "controls" / "sites.json").exists(), reason="no sites file")
def test_contact_sheets_script_end_to_end(tmp_path):
    ids = site_strips("viking1")
    if not ids or config.find_strip(ids[0]) is None:
        pytest.skip("Viking 1 strip not on disk")
    sid = ids[0]
    strip = Strip.open(sid)
    sites = json.loads((ROOT / "controls" / "sites.json").read_text())["sites"]
    site = next(s for s in sites if s["name"] == "viking1")
    lat, lon, _, _ = sheets.anchor_for(site, "lander")
    row0, col0 = (float(x) for x in geo.latlon_to_rowcol(strip.label, lat, lon))
    px_m = 1 / strip.label.scale_m
    cands = [
        {"row": row0 + 40, "col": col0 - 20, "score": 2.0, "branch": "bright", "area_px": 12, "extra": {}},
        # 800 m: inside the 1500 m radius, outside the 1500 m grid square (768 m half-span at 25 cm/px)
        {
            "row": row0 + 800 * px_m,
            "col": col0,
            "score": 3.0,
            "branch": "dark",
            "area_px": 30,
            "extra": {"also": ["x"]},
        },
        {"row": row0 + 2250 * px_m, "col": col0, "score": 9.0, "branch": "shadow", "area_px": 5, "extra": {}},
    ]
    run = {"run": "t", "git_commit": "abc", "strips": {sid: {"scale_m": strip.label.scale_m, "candidates": cands}}}
    key_before = (ROOT / "controls" / "tuning.json").read_bytes()
    sug = _run_script(tmp_path, run)
    assert (ROOT / "controls" / "tuning.json").read_bytes() == key_before  # never writes the key
    piece = next(p for p in sug["sites"][0]["pieces"] if p["piece"] == "lander")
    entry = piece["strips"][0]
    out = tmp_path / "sheets"
    for f in (entry["sheet"], entry["shadow_sheet"], entry["map"]):
        assert (out / f).exists(), f
    assert entry["anchor_how"] == "refined" and entry["within_radius"] == 2 and entry["shadow_tested"] == 2
    assert len(entry["stretch_dn"]) == 2 and entry["stretch_dn"][0] < entry["stretch_dn"][1]
    picks = entry["picks"]
    assert [p["rank"] for p in picks] == [1, 2] and [p["branch"] for p in picks] == ["dark", "bright"]
    assert picks[1]["line"] == round(row0 + 41, 1) and picks[1]["sample"] == round(col0 - 19, 1)
    assert picks[1]["grid_tile"] is not None and picks[0]["grid_tile"] is None
    assert picks[0]["also"] == ["x"]
    assert {p["shadow_rank"] for p in picks} == {1, 2}
    assert all(set(p["shadow"]) == {"z_centre", "z_anti", "z_sun", "score"} for p in picks)
    by_shadow = entry["shadow_picks"]
    assert [p["shadow_rank"] for p in by_shadow] == [1, 2]
    assert by_shadow[0]["shadow"]["score"] >= by_shadow[1]["shadow"]["score"]
    md = (out / "suggestions.md").read_text()
    assert "| 2 |" in md and entry["map"] in md and "By shadow test" in md


@pytest.mark.skipif(not (ROOT / "controls" / "sites.json").exists(), reason="no sites file")
def test_contact_sheets_strip_centre_anchor(tmp_path):
    ids = site_strips("viking1")
    if not ids or config.find_strip(ids[0]) is None:
        pytest.skip("Viking 1 strip not on disk")
    sid = ids[0]
    strip = Strip.open(sid)
    cr, cc = sheets.strip_centre(strip)
    assert 0 < cr < strip.shape[0] and 0 < cc < strip.shape[1]
    cands = [{"row": cr + 100, "col": cc + 100, "score": 1.0, "branch": "bright", "area_px": 12, "extra": {}}]
    run = {"run": "t", "git_commit": "abc", "strips": {sid: {"scale_m": strip.label.scale_m, "candidates": cands}}}
    sug = _run_script(
        tmp_path, run, "--strip-centre", "viking1", "--radius-for", "viking1=200", "--no-map", "--no-shadow"
    )
    assert sug["strip_centre_sites"] == ["viking1"] and sug["radius_for"] == {"viking1": 200.0}
    entry = next(p for p in sug["sites"][0]["pieces"] if p["piece"] == "lander")["strips"][0]
    assert entry["anchor_how"] == "strip centre" and entry["radius_m"] == 200.0
    assert abs(entry["anchor_line"] - (cr + 1)) < 1 and abs(entry["anchor_sample"] - (cc + 1)) < 1
    assert entry["grid_centre_line"] != entry["anchor_line"]  # the grid stays on the refined position
    assert entry["within_radius"] == 1 and entry["shadow_tested"] == 0 and entry["shadow_sheet"] is None
    assert entry["picks"][0]["shadow"] is None and entry["picks"][0]["shadow_rank"] is None

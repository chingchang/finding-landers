import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from landers import config, geo, sheets
from landers.strip import Strip, Window
from tests.conftest import site_strips

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
    im = sheets.draw_map(w, 0.25, 2200, 3200, 300, 60, picks, grid, "test")
    assert im.size == (300, 300 + 36)
    px = np.asarray(im)
    # a yellow mark near each pick, in map pixels: pick 1 at ((3200-2000)/8, (2200-1000)/8) = (150, 150)
    for x, y in ((150, 150), (250, 20)):
        patch = px[max(y - 8, 0) : y + 8, max(x - 8, 0) : x + 16]
        yellow = (patch[..., 0] > 200) & (patch[..., 1] > 200) & (patch[..., 2] < 60)
        assert yellow.any()
    # grid tile outlines are brown: nine 100 px squares on the map
    assert grid.tile_of(2200, 3200) == 1 * 3 + 1 + 1 == 5
    brown = (px[..., 0] == 90) & (px[..., 1] == 70) & (px[..., 2] == 0)
    assert brown.sum() > 1500


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
    (tmp_path / "candidates_t.json").write_text(json.dumps(run))
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
            str(tmp_path / "sheets"),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    sug = json.loads((tmp_path / "sheets" / "suggestions.json").read_text())
    piece = next(p for p in sug["sites"][0]["pieces"] if p["piece"] == "lander")
    entry = piece["strips"][0]
    assert (tmp_path / "sheets" / entry["sheet"]).exists() and (tmp_path / "sheets" / entry["map"]).exists()
    picks = entry["picks"]
    assert [p["rank"] for p in picks] == [1, 2] and [p["branch"] for p in picks] == ["dark", "bright"]
    assert picks[1]["line"] == round(row0 + 41, 1) and picks[1]["sample"] == round(col0 - 19, 1)
    assert picks[1]["grid_tile"] is not None and picks[0]["grid_tile"] is None
    assert picks[0]["also"] == ["x"]
    md = (tmp_path / "sheets" / "suggestions.md").read_text()
    assert "| 2 |" in md and entry["map"] in md
    assert not (ROOT / "controls" / "tuning.json").read_text().count('"line": 4')  # never writes the key

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from landers import config
from landers.label import StripLabel
from landers.search import coverage as cov
from landers.search import plan, run
from landers.search.grid import PolarGrid, cells_of_mask, pack, unpack
from landers.search.inventory import StripRecord
from landers.strip import Strip
from tests.conftest import manifest_ids, needs_data

ROOT = Path(__file__).resolve().parent.parent
STEP = 16  # overview step
SCALE = 0.25  # m/px, so one overview pixel is 4 m


def fake_label(sid: str, line_offset: float = 0.0, sample_offset: float = 0.0, scale: float = SCALE) -> StripLabel:
    return StripLabel(
        observation_id=sid,
        rationale="Search for Mars Polar Lander",
        lines=4000,
        samples=4000,
        scale_m=scale,
        projection="POLAR STEREOGRAPHIC",
        center_lat=-90.0,
        center_lon=0.0,
        line_offset=line_offset,
        sample_offset=sample_offset,
        map_resolution=235703.22482333 * (SCALE / scale),
        radius_m=3396190.0,
        min_lat=-77.0,
        max_lat=-76.0,
        west_lon=160.0,
        east_lon=170.0,
        incidence_deg=60.0,
        sub_solar_azimuth_deg=20.0,
        north_azimuth_deg=90.0,
        solar_longitude_deg=300.0,
        start_time="2007-09-01T00:00:00",
    )


def test_pack_unpack_roundtrip():
    ix = np.array([-5, 0, 7, 123456])
    iy = np.array([3, -9, 0, -123456])
    a, b = unpack(pack(ix, iy))
    assert (a == ix).all() and (b == iy).all()


def test_full_mask_covers_its_own_area():
    lbl = fake_label("A")
    grid = PolarGrid.from_label(lbl, cell_m=100.0)
    valid = np.ones((250, 250), dtype=bool)  # 250 * 16 * 0.25 m = 1 km on each side
    keys = cells_of_mask(lbl, valid, STEP, grid)
    assert keys.size == 100 and abs(keys.size * grid.cell_km2 - 1.0) < 1e-9
    # the same mask in blocks of 7 rows gives the same cells
    assert (cells_of_mask(lbl, valid, STEP, grid, block_rows=7) == keys).all()


def test_half_covered_cells_follow_min_fraction():
    lbl = fake_label("A")
    valid = np.ones((250, 250), dtype=bool)
    valid[:, 240:] = False  # last 40 m of each 100 m column of cells is missing: 60 percent covered
    assert cells_of_mask(lbl, valid, STEP, PolarGrid.from_label(lbl, 100.0, min_fraction=0.5)).size == 100
    assert cells_of_mask(lbl, valid, STEP, PolarGrid.from_label(lbl, 100.0, min_fraction=0.7)).size == 90


def test_grid_rejects_another_projection():
    lbl = fake_label("A")
    grid = PolarGrid.from_label(lbl)
    other = StripLabel(**{**lbl.__dict__, "projection": "EQUIRECTANGULAR", "center_lat": 0.0})
    with pytest.raises(ValueError):
        cells_of_mask(other, np.ones((4, 4), dtype=bool), STEP, grid)


def _two_strips():
    """A (1 km square) and B (the same square shifted 500 m along x): half of each is shared."""
    la = fake_label("A")
    lb = fake_label("B", sample_offset=-2000.0)  # x = (col + 2000) * 0.25: shifted by 500 m
    grid = PolarGrid.from_label(la, 100.0)
    valid = np.ones((250, 250), dtype=bool)
    return grid, {"A": cells_of_mask(la, valid, STEP, grid), "B": cells_of_mask(lb, valid, STEP, grid)}


def test_overlaps_and_coverage_on_two_shifted_squares():
    grid, cells = _two_strips()
    pairs = cov.overlaps(cells, grid)
    assert pairs == [{"a": "A", "b": "B", "km2": 0.5, "fraction_of_a": 0.5, "fraction_of_b": 0.5}]
    c = cov.coverage(cells, grid)
    assert c["union_km2"] == 1.5 and c["km2_by_dates"] == {1: 1.0, 2: 0.5} and c["max_dates"] == 2
    assert c["km2_with_at_least_n_dates"] == {1: 1.5, 2: 0.5}
    assert c["per_strip"]["A"] == {"km2": 1.0, "km2_on_two_or_more_dates": 0.5, "fraction_on_two_or_more_dates": 0.5}
    assert c["cells"].shape == (150, 3) and (c["cells"][:, 2] >= 1).all()
    # json form is plain lists
    j = cov.coverage_json(c)
    json.dumps(j)
    assert len(j["cells"]) == 150


def test_render_writes_a_png(tmp_path):
    grid, cells = _two_strips()
    c = cov.coverage(cells, grid)
    p = cov.render(c, tmp_path / "coverage.png")
    from PIL import Image

    im = Image.open(p)
    assert im.size[0] > 100 and im.size[1] > 100
    # the darker (two dates) colour appears, and so does the one-date colour
    px = np.asarray(im.convert("RGB")).reshape(-1, 3)
    assert (px == cov.RAMP[0]).all(axis=1).any() and (px == cov.RAMP[1]).all(axis=1).any()


RUN_LOG = (
    "\rX tiles=1 cands=4\rX tiles=2 cands=9\n"
    "X: 300 candidates from 20 tiles in 50s\n"
    "Y: 10 candidates from 30 tiles in 50s\n"
    "written: out/candidates.json\n"
)


def test_baseline_rate_from_log(tmp_path):
    p = tmp_path / "run.log"
    p.write_text(RUN_LOG)
    r = plan.baseline_rate(p)
    assert r["tiles"] == 50 and r["seconds"] == 100 and r["tiles_per_second"] == 0.5
    assert [s["observation_id"] for s in r["strips"]] == ["X", "Y"]
    (tmp_path / "empty.log").write_text("nothing here\n")
    with pytest.raises(ValueError):
        plan.baseline_rate(tmp_path / "empty.log")


def rec(sid, phase, date, tiles, search_title=True) -> StripRecord:
    return StripRecord(
        observation_id=sid,
        case="mpl_summer",
        phase=phase,
        date=date,
        start_time=date + "T00:00:00",
        solar_longitude_deg=300.0,
        incidence_deg=60.0,
        tan_incidence=1.732,
        sub_solar_azimuth_deg=20.0,
        scale_m=0.25,
        lines=1,
        samples=1,
        valid_area_km2=float(tiles),
        footprint={},
        title="Search for Mars Polar Lander" if search_title else "dune database entry",
        search_title=search_title,
        tiles=tiles,
        tile_px=2048,
        overlap_px=128,
        grid_cells=0,
        grid_km2=0.0,
    )


def test_plan_orders_psp_first_and_packs_sessions():
    rate = {"tiles_per_second": 0.5, "tiles": 50, "seconds": 100, "source": "x", "strips": []}
    records = [
        rec("E2", "ESP", "2009-06-01", 1000),
        rec("E1", "ESP", "2009-05-01", 2000),
        rec("P2", "PSP", "2007-10-01", 500),
        rec("P1", "PSP", "2007-07-01", 1500),
        rec("D", "ESP", "2008-01-01", 100, search_title=False),
    ]
    p = plan.tiling_plan(records, rate, session_seconds=7200)
    ids = [s["observation_id"] for s in p["strips"]]
    assert ids == ["P1", "P2", "E1", "E2", "D"]
    # 1500 + 500 tiles = 4000 s fits one session; E1 (4000 s) opens the second; E2 (2000 s) joins it; D (200 s) too
    assert p["sessions"] == [["P1", "P2"], ["E1", "E2", "D"]]
    assert p["strips"][0]["estimated_seconds"] == 3000 and p["strips"][-1]["note"]
    assert p["totals"]["tiles"] == 5100 and p["totals"]["psp_tiles"] == 2000 and p["totals"]["sessions"] == 2
    assert p["totals"]["estimated_hours"] == round(5100 / 0.5 / 3600, 2)


def test_pending_skips_written_strips(tmp_path):
    (tmp_path / "candidates_B.json").write_text("{}")
    assert run.pending(["A", "B", "C"], tmp_path) == ["A", "C"]


def test_run_refuses_without_frozen(tmp_path):
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "search.py"), "run", "--out", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 3 and "frozen" in r.stderr


# --- on real strips ---------------------------------------------------------------------------------------

MPL = manifest_ids("mpl_summer")


@needs_data
@pytest.mark.skipif(not MPL, reason="no search strips in the manifest")
def test_cells_match_valid_area_on_a_search_strip():
    sid = next((s for s in MPL if config.find_strip(s)), None)
    if sid is None:
        pytest.skip("no search strip on disk")
    strip = Strip.open(sid)
    grid = PolarGrid.from_label(strip.label, 100.0)
    keys = cells_of_mask(strip.label, strip.overview.valid, strip.overview_step, grid)
    km2 = keys.size * grid.cell_km2
    assert abs(km2 - strip.valid_area_km2()) / strip.valid_area_km2() < 0.03, (km2, strip.valid_area_km2())


@needs_data
@pytest.mark.skipif(not MPL, reason="no search strips in the manifest")
def test_run_writes_one_file_per_strip_with_a_stub_detector(tmp_path):
    sid = next((s for s in MPL if config.find_strip(s)), None)
    if sid is None:
        pytest.skip("no search strip on disk")
    from landers.detect import DetectorConfig

    def stub(strip, cfg):
        return {"valid_area_km2": 1.0, "scale_m": strip.label.scale_m, "tiles": 0, "candidates": []}

    path, entry = run.run_strip(sid, DetectorConfig(frozen=True), tmp_path, detector=stub)
    d = json.loads(path.read_text())
    assert path.name == f"candidates_{sid}.json" and d["detector"]["frozen"] is True
    assert list(d["strips"]) == [sid] and "commit" in d["git"]
    assert run.pending([sid], tmp_path) == []

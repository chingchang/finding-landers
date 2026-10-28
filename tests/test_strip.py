import numpy as np
import pytest

from landers import config
from landers.strip import Strip
from tests.conftest import manifest_ids, needs_data

# One of each: equirectangular (Curiosity), north polar (Phoenix), south polar (an MPL strip).
SAMPLE_IDS = (
    manifest_ids("control_curiosity")[:1] + manifest_ids("control_phoenix")[:1] + manifest_ids("mpl_summer")[:1]
)


@pytest.fixture(scope="module", params=SAMPLE_IDS or ["none"])
def strip(request):
    if request.param == "none":
        pytest.skip("no manifest on disk")
    if config.find_strip(request.param) is None:
        pytest.skip(f"{request.param} not on disk")
    return Strip.open(request.param)


@needs_data
def test_window_shape_and_mask(strip):
    r, c = strip.shape[0] // 2, strip.shape[1] // 2
    w = strip.read_centered(r, c, 512)
    assert w.shape == (512, 512) and w.data.dtype == np.uint16
    assert w.valid.dtype == bool and w.valid.shape == w.shape
    assert w.data.max() < 1024


@needs_data
def test_overview_footprint_matches_label(strip):
    lbl = strip.label
    mn, mx, w, e = strip.footprint_bounds()
    # One overview pixel is 16 image px = 4 m, about 7e-5 deg of latitude; allow a few.
    tol_lat = 5e-4
    tol_lon = 5e-4 / abs(np.cos(np.radians(lbl.center_lat if lbl.projection == "EQUIRECTANGULAR" else lbl.min_lat)))
    assert abs(mn - lbl.min_lat) < tol_lat and abs(mx - lbl.max_lat) < tol_lat, (
        lbl.observation_id,
        mn,
        mx,
        lbl.min_lat,
        lbl.max_lat,
    )
    assert abs(w - lbl.west_lon) < tol_lon and abs(e - lbl.east_lon) < tol_lon, (
        lbl.observation_id,
        w,
        e,
        lbl.west_lon,
        lbl.east_lon,
    )


@needs_data
def test_tiles_cover_valid_area_only(strip):
    tiles = list(strip.tiles(size=4096, overlap=256))
    assert tiles
    n_total = -(-strip.shape[0] // 3840) * -(-strip.shape[1] // 3840)
    assert len(tiles) < n_total  # the empty corners beside the slanted footprint are skipped
    assert strip.valid_area_km2() > 1

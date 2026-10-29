"""One pass over the search strips: the label facts, the valid area, the tile count and the grid cells each
strip covers. Opening a strip costs one overview decode (seconds); nothing is read at full resolution."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from landers import config
from landers.search.grid import PolarGrid, cells_of_mask
from landers.strip import Strip

SEARCH_CASE = "mpl_summer"
SEARCH_TITLE_WORDS = ("polar lander", "mpl")  # a strip whose title lacks these was not taken for the search


@dataclass
class StripRecord:
    observation_id: str
    case: str
    phase: str  # PSP or ESP, from the id
    date: str  # YYYY-MM-DD from START_TIME
    start_time: str
    solar_longitude_deg: float
    incidence_deg: float
    tan_incidence: float
    sub_solar_azimuth_deg: float
    scale_m: float
    lines: int
    samples: int
    valid_area_km2: float
    footprint: dict  # min_lat, max_lat, west_lon, east_lon from the overview's valid pixels
    title: str  # RATIONALE_DESC
    search_title: bool  # the title says this strip was taken to look for the lander
    tiles: int  # detector tiles over the valid footprint at the given tile size and overlap
    tile_px: int
    overlap_px: int
    grid_cells: int
    grid_km2: float

    def to_json(self) -> dict:
        return asdict(self)


def manifest_ids(case: str = SEARCH_CASE) -> list[str]:
    """Observation ids of one case in the manifest, in manifest order."""
    out = []
    for line in config.manifest_path().read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == case:
            out.append(parts[1])
    return out


def survey_strip(strip: Strip, grid: PolarGrid, tile: int, overlap: int, case: str = SEARCH_CASE):
    """A ``StripRecord`` and the strip's covered cell keys."""
    lbl = strip.label
    ov = strip.overview
    keys = cells_of_mask(lbl, ov.valid, strip.overview_step, grid)
    mn, mx, w, e = strip.footprint_bounds()
    n_tiles = sum(1 for _ in strip.tiles(tile, overlap))
    title = lbl.rationale
    rec = StripRecord(
        observation_id=lbl.observation_id,
        case=case,
        phase=lbl.observation_id.split("_")[0],
        date=lbl.start_time[:10],
        start_time=lbl.start_time,
        solar_longitude_deg=round(lbl.solar_longitude_deg, 2),
        incidence_deg=round(lbl.incidence_deg, 2),
        tan_incidence=round(math.tan(math.radians(lbl.incidence_deg)), 3),
        sub_solar_azimuth_deg=round(lbl.sub_solar_azimuth_deg, 2),
        scale_m=lbl.scale_m,
        lines=lbl.lines,
        samples=lbl.samples,
        valid_area_km2=round(strip.valid_area_km2(), 3),
        footprint={"min_lat": round(mn, 5), "max_lat": round(mx, 5), "west_lon": round(w, 5), "east_lon": round(e, 5)},
        title=title,
        search_title=any(w_ in title.lower() for w_ in SEARCH_TITLE_WORDS),
        tiles=n_tiles,
        tile_px=tile,
        overlap_px=overlap,
        grid_cells=int(keys.size),
        grid_km2=round(float(keys.size) * grid.cell_km2, 3),
    )
    return rec, keys


def survey(ids: list[str], cell_m: float, tile: int, overlap: int, progress=None):
    """Records and cell keys for every id that is on disk; ids not on disk are listed separately.
    The grid is defined by the first strip's label and every other strip must share its frame."""
    records: list[StripRecord] = []
    cells: dict[str, np.ndarray] = {}
    missing: list[str] = []
    grid: PolarGrid | None = None
    for sid in ids:
        if config.find_strip(sid) is None:
            missing.append(sid)
            continue
        strip = Strip.open(sid)
        if grid is None:
            grid = PolarGrid.from_label(strip.label, cell_m)
        rec, keys = survey_strip(strip, grid, tile, overlap)
        records.append(rec)
        cells[sid] = keys
        if progress:
            progress(rec)
        del strip  # drop the cached overview before the next one
    if grid is None:
        raise FileNotFoundError("none of the strips is on disk")
    return grid, records, cells, missing

"""A square grid in the strips' own map projection, and which of its cells a strip covers.

All the search strips share one polar stereographic projection (same pole, same centre longitude, same
sphere), so a strip pixel maps to projection metres through its label's offsets and scale alone, and two
strips' footprints can be compared cell by cell without going through latitude and longitude. The grid
refuses a label from a different projection rather than silently mixing frames.

A cell is an integer pair (ix, iy) = floor(x / cell_m), floor(y / cell_m); it is packed into one int64 key
so sets of cells can be unioned and intersected with numpy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from landers import geo
from landers.label import StripLabel

_OFF = 1 << 30  # cells live in [-2**30, 2**30); each index takes 31 bits of the int64 key
_SHIFT = 31


@dataclass(frozen=True)
class PolarGrid:
    cell_m: float
    projection: str
    center_lat: float
    center_lon: float
    radius_m: float  # sphere radius implied by MAP_RESOLUTION and MAP_SCALE
    min_fraction: float = 0.5  # a cell counts as covered when this fraction of it holds valid pixels

    @classmethod
    def from_label(cls, lbl: StripLabel, cell_m: float = 100.0, min_fraction: float = 0.5) -> PolarGrid:
        return cls(
            float(cell_m),
            lbl.projection,
            lbl.center_lat,
            lbl.center_lon,
            geo.sphere_radius_m(lbl),
            min_fraction,
        )

    def check(self, lbl: StripLabel) -> None:
        """Raise unless ``lbl`` is in this grid's projection frame."""
        same = (
            lbl.projection == self.projection
            and abs(lbl.center_lat - self.center_lat) < 1e-6
            and abs(lbl.center_lon - self.center_lon) < 1e-6
            and abs(geo.sphere_radius_m(lbl) - self.radius_m) < 1.0
        )
        if not same:
            raise ValueError(
                f"{lbl.observation_id}: projection {lbl.projection} centred {lbl.center_lat}, {lbl.center_lon} "
                f"is not the grid's {self.projection} centred {self.center_lat}, {self.center_lon}"
            )

    @property
    def cell_km2(self) -> float:
        return self.cell_m * self.cell_m / 1e6

    def to_json(self) -> dict:
        return {
            "cell_m": self.cell_m,
            "projection": self.projection,
            "center_lat": self.center_lat,
            "center_lon": self.center_lon,
            "sphere_radius_m": round(self.radius_m, 1),
            "min_fraction": self.min_fraction,
            "cell": "ix = floor(x / cell_m), iy = floor(y / cell_m); x, y are projection metres: "
            "x = (sample - SAMPLE_PROJECTION_OFFSET) * MAP_SCALE, y = (LINE_PROJECTION_OFFSET - line) * MAP_SCALE "
            "with 0-based line and sample",
        }


def pack(ix: np.ndarray, iy: np.ndarray) -> np.ndarray:
    return (ix.astype(np.int64) + _OFF) * (1 << _SHIFT) + (iy.astype(np.int64) + _OFF)


def unpack(keys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    keys = np.asarray(keys, dtype=np.int64)
    ix = (keys >> _SHIFT) - _OFF
    iy = (keys & ((1 << _SHIFT) - 1)) - _OFF
    return ix, iy


def xy_of_rowcol(lbl: StripLabel, row, col):
    """Projection metres of 0-based pixel centres (the same convention as ``landers.geo``)."""
    row = np.asarray(row, dtype=np.float64)
    col = np.asarray(col, dtype=np.float64)
    return (col - lbl.sample_offset) * lbl.scale_m, (lbl.line_offset - row) * lbl.scale_m


def cells_of_mask(lbl: StripLabel, valid: np.ndarray, step: int, grid: PolarGrid, block_rows: int = 256):
    """Sorted unique keys of the grid cells covered by a reduced-resolution valid mask (``step`` image pixels
    per mask pixel). A cell is covered when at least ``grid.min_fraction`` of its area holds valid pixels.

    Works in blocks of mask rows so a whole strip's overview never becomes several arrays of its own size.
    """
    grid.check(lbl)
    px_m = lbl.scale_m * step
    need = grid.min_fraction * grid.cell_m * grid.cell_m / (px_m * px_m)
    parts: list[np.ndarray] = []
    counts: list[np.ndarray] = []
    for r0 in range(0, valid.shape[0], block_rows):
        rows, cols = np.nonzero(valid[r0 : r0 + block_rows])
        if rows.size == 0:
            continue
        x, y = xy_of_rowcol(lbl, (rows + r0) * step + step / 2 - 0.5, cols * step + step / 2 - 0.5)
        keys = pack(np.floor(x / grid.cell_m), np.floor(y / grid.cell_m))
        u, c = np.unique(keys, return_counts=True)
        parts.append(u)
        counts.append(c)
    if not parts:
        return np.zeros(0, dtype=np.int64)
    allk = np.concatenate(parts)
    allc = np.concatenate(counts)
    u, inv = np.unique(allk, return_inverse=True)
    total = np.zeros(u.size, dtype=np.int64)
    np.add.at(total, inv, allc)
    return u[total >= need]

"""Windowed access to one HiRISE strip. Never loads a whole strip at full resolution.

Pixels are uint16 holding 10-bit values: 0 is no data (outside the slanted footprint or a gap), 1022 and
1023 are saturated. ``Window.valid`` masks both out; callers mask, they never fill.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import glymur
import numpy as np

from landers import config, geo
from landers.label import StripLabel

NO_DATA = 0
SATURATED = 1022
OVERVIEW_LEVEL = 4  # 2**4 = 16 image px per overview px; about 2 s and 20 MB for the largest strip


@dataclass(frozen=True)
class Window:
    row0: int
    col0: int
    data: np.ndarray  # uint16 (rows, cols)
    valid: np.ndarray  # bool, same shape
    step: int = 1  # image pixels per data pixel (1 at full resolution)

    @property
    def shape(self):
        return self.data.shape


def valid_mask(data: np.ndarray) -> np.ndarray:
    return (data != NO_DATA) & (data < SATURATED)


class Strip:
    def __init__(self, jp2_path: str | Path, lbl_path: str | Path | None = None):
        self.jp2_path = Path(jp2_path)
        self.lbl_path = Path(lbl_path) if lbl_path else self.jp2_path.with_suffix(".LBL")
        self.label = StripLabel.read(self.lbl_path)
        self._jp2 = glymur.Jp2k(str(self.jp2_path))
        if self._jp2.shape[:2] != (self.label.lines, self.label.samples):
            raise ValueError(
                f"{self.jp2_path.name}: JP2 {self._jp2.shape[:2]} vs label {(self.label.lines, self.label.samples)}"
            )

    @classmethod
    def open(cls, observation_id: str) -> Strip:
        p = config.find_strip(observation_id)
        if p is None:
            raise FileNotFoundError(f"{observation_id} not under {config.strips_dir()}")
        return cls(p)

    @property
    def shape(self) -> tuple[int, int]:
        return self.label.lines, self.label.samples

    def read(self, row0: int, row1: int, col0: int, col1: int) -> Window:
        """Pixels of [row0:row1, col0:col1], clipped to the image. Rows and cols are 0-based."""
        row0, col0 = max(row0, 0), max(col0, 0)
        row1, col1 = min(row1, self.label.lines), min(col1, self.label.samples)
        if row1 <= row0 or col1 <= col0:
            raise ValueError("empty window")
        data = np.asarray(self._jp2[row0:row1, col0:col1])
        if data.ndim == 3:
            data = data[..., 0]
        return Window(row0, col0, data, valid_mask(data))

    def read_centered(self, row: float, col: float, size: int) -> Window:
        r0, c0 = int(round(row)) - size // 2, int(round(col)) - size // 2
        return self.read(r0, r0 + size, c0, c0 + size)

    def read_reduced(self, row0: int, row1: int, col0: int, col1: int, step: int) -> Window:
        """[row0:row1, col0:col1] at one pixel per ``step`` image pixels (a power of two), decoded from the
        JPEG 2000 resolution levels, so a 3 km square at 2 m/px costs seconds, not a 300 MB read.

        ``Window.row0``/``col0`` are full-resolution coordinates; data pixel (i, j) sits at image pixel
        (row0 + i * step, col0 + j * step)."""
        if step < 1 or step & (step - 1):
            raise ValueError(f"step must be a power of two, not {step}")
        row0, col0 = max(row0, 0), max(col0, 0)
        row1, col1 = min(row1, self.label.lines), min(col1, self.label.samples)
        if row1 <= row0 or col1 <= col0:
            raise ValueError("empty window")
        data = np.asarray(self._jp2[row0:row1:step, col0:col1:step])
        if data.ndim == 3:
            data = data[..., 0]
        return Window(row0, col0, data, valid_mask(data), step)

    @cached_property
    def overview(self) -> Window:
        """Whole strip at 1/2**OVERVIEW_LEVEL resolution; used for the footprint and tile planning."""
        step = 2**OVERVIEW_LEVEL
        data = np.asarray(self._jp2[::step, ::step])
        if data.ndim == 3:
            data = data[..., 0]
        return Window(0, 0, data, valid_mask(data))

    @property
    def overview_step(self) -> int:
        return 2**OVERVIEW_LEVEL

    def valid_area_km2(self) -> float:
        px_m = self.label.scale_m * self.overview_step
        return float(self.overview.valid.sum()) * px_m * px_m / 1e6

    def footprint_bounds(self):
        return geo.mask_bounds(self.label, self.overview.valid, self.overview_step)

    def tiles(self, size: int = 2048, overlap: int = 128, min_valid_fraction: float = 0.02):
        """Yield (row0, row1, col0, col1) windows covering the valid footprint, with overlap.

        Tiles whose overview shows almost no valid pixels are skipped, so the empty triangles beside
        the slanted footprint cost nothing.
        """
        ov = self.overview.valid
        step = self.overview_step
        stride = size - overlap
        for r0 in range(0, self.label.lines, stride):
            r1 = min(r0 + size, self.label.lines)
            for c0 in range(0, self.label.samples, stride):
                c1 = min(c0 + size, self.label.samples)
                sub = ov[r0 // step : -(-r1 // step), c0 // step : -(-c1 // step)]
                if sub.size and sub.mean() >= min_valid_fraction:
                    yield r0, r1, c0, c1

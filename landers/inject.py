"""Synthetic objects of known size placed into real tiles, so recall can be measured by size and branch
without an answer key. The ground is real; only the object is drawn. Contrast is a fraction of the local
background mean, and every injected object records its kind, size, contrast and position.

Kinds:
- ``sheet``: a bright flat ellipse (aspect ``sheet_aspect``), 8 to 25 m; a parachute on the ground.
- ``dark_compact``: a dark disc 1 to 4 m; optionally with a shadow of a ``height_m`` tall object.
- ``blob_shadow``: a bright disc 1 to 5 m with the shadow of an object ``height_m`` tall.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
from scipy import ndimage

from landers import geo
from landers.label import StripLabel
from landers.strip import Window

KINDS = ("sheet", "dark_compact", "blob_shadow")


@dataclass
class InjectConfig:
    sheet_size_m: tuple[float, float] = (8.0, 25.0)
    sheet_aspect: float = 0.5
    sheet_contrast: float = 0.35
    dark_compact_size_m: tuple[float, float] = (1.0, 4.0)
    dark_compact_contrast: float = -0.35
    dark_compact_shadow_fraction: float = 0.5  # fraction of dark compacts that also get a shadow
    blob_size_m: tuple[float, float] = (1.0, 5.0)
    blob_contrast: float = 0.5
    shadow_contrast: float = -0.5
    height_m: tuple[float, float] = (0.5, 2.5)
    edge_px: float = 1.0  # softness of every edge, in px
    background_px: int = 65

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class Injected:
    kind: str
    row: float  # tile-local, 0-based
    col: float
    size_m: float
    contrast: float
    height_m: float | None
    shadow: bool

    def to_json(self) -> dict:
        return asdict(self)


def _local_mean(data: np.ndarray, valid: np.ndarray, r: int, c: int, size: int) -> float:
    h = size // 2
    sub = data[max(r - h, 0) : r + h + 1, max(c - h, 0) : c + h + 1]
    v = valid[max(r - h, 0) : r + h + 1, max(c - h, 0) : c + h + 1]
    return float(sub[v].mean()) if v.any() else float(data[valid].mean())


def _ellipse(shape, r, c, a_px, b_px, angle, edge):
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    dy, dx = yy - r, xx - c
    u = dy * math.cos(angle) + dx * math.sin(angle)
    v = -dy * math.sin(angle) + dx * math.cos(angle)
    m = ((u / a_px) ** 2 + (v / b_px) ** 2 <= 1.0).astype(np.float64)
    return ndimage.gaussian_filter(m, edge) if edge > 0 else m


def _streak(shape, r, c, drow, dcol, start_px, length_px, width_px, edge):
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    dy, dx = yy - r, xx - c
    along = dy * drow + dx * dcol
    across = np.abs(dy * dcol - dx * drow)
    m = ((along >= start_px) & (along <= start_px + length_px) & (across <= width_px / 2)).astype(np.float64)
    return ndimage.gaussian_filter(m, edge) if edge > 0 else m


def _place(rng, valid: np.ndarray, margin: int, taken: list[tuple[float, float, float]], tries: int = 200):
    h, w = valid.shape
    for _ in range(tries):
        r = int(rng.integers(margin, h - margin))
        c = int(rng.integers(margin, w - margin))
        if not valid[r - margin : r + margin + 1, c - margin : c + margin + 1].all():
            continue
        if any(math.hypot(r - tr, c - tc) < (margin + tm) for tr, tc, tm in taken):
            continue
        return r, c
    return None


def inject(
    win: Window, lbl: StripLabel, cfg: InjectConfig, rng: np.random.Generator, per_kind: int
) -> tuple[Window, list[Injected]]:
    """Return a copy of the tile with ``per_kind`` objects of each kind drawn in, and their records."""
    scale = lbl.scale_m
    data = win.data.astype(np.float64)
    valid = win.valid
    drow, dcol = geo.shadow_direction(lbl)
    objs: list[Injected] = []
    taken: list[tuple[float, float, float]] = []
    gain = np.ones_like(data)

    for kind in KINDS:
        for _ in range(per_kind):
            if kind == "sheet":
                size = float(rng.uniform(*cfg.sheet_size_m))
                margin = int(size / scale) + 16
            elif kind == "dark_compact":
                size = float(rng.uniform(*cfg.dark_compact_size_m))
                margin = int(geo.shadow_length_px(lbl, cfg.height_m[1]) + size / scale) + 16
            else:
                size = float(rng.uniform(*cfg.blob_size_m))
                margin = int(geo.shadow_length_px(lbl, cfg.height_m[1]) + size / scale) + 16
            pos = _place(rng, valid, margin, taken)
            if pos is None:
                continue
            r, c = pos
            taken.append((r, c, margin))
            radius_px = size / scale / 2
            if kind == "sheet":
                angle = float(rng.uniform(0, math.pi))
                m = _ellipse(data.shape, r, c, radius_px, radius_px * cfg.sheet_aspect, angle, cfg.edge_px)
                gain += cfg.sheet_contrast * m
                objs.append(Injected(kind, r, c, size, cfg.sheet_contrast, None, False))
            else:
                contrast = cfg.dark_compact_contrast if kind == "dark_compact" else cfg.blob_contrast
                m = _ellipse(data.shape, r, c, radius_px, radius_px, 0.0, cfg.edge_px)
                gain += contrast * m
                shadow = kind == "blob_shadow" or rng.uniform() < cfg.dark_compact_shadow_fraction
                height = None
                if shadow:
                    height = float(rng.uniform(*cfg.height_m))
                    length = geo.shadow_length_px(lbl, height)
                    s = _streak(
                        data.shape, r, c, drow, dcol, radius_px * 0.8, length, max(2.0, radius_px * 1.6), cfg.edge_px
                    )
                    gain += cfg.shadow_contrast * np.clip(s - m, 0, 1)
                objs.append(Injected(kind, r, c, size, contrast, height, shadow))
    out = np.clip(data * gain, 1, 1021)
    out[~valid] = 0
    return Window(win.row0, win.col0, out.astype(np.uint16), valid.copy()), objs

"""Physical tests, version 0. No model is involved anywhere in this module.

Three branches run per tile and every candidate carries the branch that made it:

- ``bright``: a compact patch brighter than its surroundings (local z-score over a ring background),
  1 to 10 m across. Landers, backshells and parachutes are bright; so are many rocks.
- ``dark``: a compact patch darker than its surroundings, 2.5 to 50 m across (crash scars, blast zones,
  the dark side of a disturbed area).
- ``shadow``: a ``bright`` candidate with a dark patch adjacent to it in the direction shadows fall, at a
  distance consistent with an object 0.5 to 3 m tall under this strip's sun. The label gives the sun
  azimuth and incidence; nothing else about the image is used.

Grades here can only be "needs second look" (passes a physical test on one date) or "likely natural";
"candidate" needs a second date, which is the persistence step and not part of this module.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy import ndimage

from landers import geo
from landers.label import StripLabel
from landers.strip import Strip, Window


@dataclass
class DetectorConfig:
    version: str = "v0"
    frozen: bool = False
    tile: int = 2048
    overlap: int = 128
    background_px: int = 65  # window for the local mean and std
    smooth_sigma: float = 0.7
    z_bright: float = 4.0
    z_dark: float = -3.5
    bright_area_px: tuple[int, int] = (6, 1600)  # 1 m .. 10 m across at 25 cm/px
    dark_area_px: tuple[int, int] = (100, 40000)  # 2.5 m .. 50 m across
    shadow_heights_m: tuple[float, float] = (0.5, 3.0)
    shadow_min_incidence_deg: float = 35.0  # below this shadows are too short to test (Opportunity strip)
    edge_margin_px: int = 8

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class Candidate:
    row: float
    col: float
    score: float
    branch: str
    grade: str
    area_px: int
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        d = asdict(self)
        d["row"] = round(d["row"], 1)
        d["col"] = round(d["col"], 1)
        d["score"] = round(d["score"], 3)
        return d


def local_z(
    data: np.ndarray, valid: np.ndarray, size: int, sigma: float, inner: int = 15, margin: int = 4
) -> np.ndarray:
    """Z-score of each pixel against the mean and std of an annulus (``size`` window minus an ``inner``
    window) of valid pixels around it. Invalid pixels, and a ``margin`` around them, get z = 0.

    Smoothing is a normalised convolution so no-data zeros never bleed into valid ground, and the sums
    are float64 so the variance does not cancel away at 10-bit signal levels.
    """
    w = valid.astype(np.float64)
    x = data.astype(np.float64) * w
    if sigma > 0:
        num = ndimage.gaussian_filter(x, sigma)
        den = ndimage.gaussian_filter(w, sigma)
        with np.errstate(divide="ignore", invalid="ignore"):
            x = np.where(den > 1e-3, num / den, 0.0)
        x *= w

    def sums(k: int):
        n = ndimage.uniform_filter(w, k, mode="constant") * (k * k)
        s1 = ndimage.uniform_filter(x, k, mode="constant") * (k * k)
        s2 = ndimage.uniform_filter(x * x, k, mode="constant") * (k * k)
        return n, s1, s2

    n_o, s1_o, s2_o = sums(size)
    n_i, s1_i, s2_i = sums(inner)
    n, s1, s2 = n_o - n_i, s1_o - s1_i, s2_o - s2_i
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = s1 / n
        var = s2 / n - mean * mean
    std = np.sqrt(np.maximum(var, 1e-6))
    z = (x - mean) / std
    enough = n >= 0.5 * (size * size - inner * inner)
    bad = ~valid
    if bad.any() and margin > 0:
        bad = ndimage.binary_dilation(bad, iterations=margin)
    z[~enough | bad] = 0.0
    return z.astype(np.float32)


def _components(mask: np.ndarray, zmap: np.ndarray, area: tuple[int, int], valid: np.ndarray, margin: int):
    lab, n = ndimage.label(mask)
    if n == 0:
        return []
    idx = np.arange(1, n + 1)
    areas = ndimage.sum(np.ones_like(lab, dtype=np.int32), lab, idx)
    keep = (areas >= area[0]) & (areas <= area[1])
    out = []
    if not keep.any():
        return out
    peaks = ndimage.maximum(np.abs(zmap), lab, idx)
    centroids = ndimage.center_of_mass(np.abs(zmap), lab, idx)
    h, w = mask.shape
    bad_edge = ndimage.binary_dilation(~valid, iterations=margin) if (~valid).any() else None
    for i in np.nonzero(keep)[0]:
        r, c = centroids[i]
        if r < margin or c < margin or r > h - margin or c > w - margin:
            continue
        if bad_edge is not None and bad_edge[int(r), int(c)]:
            continue
        out.append((float(r), float(c), float(peaks[i]), int(areas[i]), int(i + 1)))
    return out


def detect_tile(win: Window, lbl: StripLabel, cfg: DetectorConfig) -> list[Candidate]:
    z = local_z(win.data, win.valid, cfg.background_px, cfg.smooth_sigma)
    bright = _components(z > cfg.z_bright, z, cfg.bright_area_px, win.valid, cfg.edge_margin_px)
    dark = _components(z < cfg.z_dark, z, cfg.dark_area_px, win.valid, cfg.edge_margin_px)
    # small dark patches too (shadows are a few px): separate pass with the bright size range
    small_dark = _components(z < cfg.z_dark, z, cfg.bright_area_px, win.valid, cfg.edge_margin_px)

    out: list[Candidate] = []
    can_shadow = lbl.incidence_deg >= cfg.shadow_min_incidence_deg
    drow, dcol = geo.shadow_direction(lbl)
    lmin = geo.shadow_length_px(lbl, cfg.shadow_heights_m[0])
    lmax = geo.shadow_length_px(lbl, cfg.shadow_heights_m[1])
    dark_pts = np.array([(r, c) for r, c, *_ in small_dark]) if small_dark else np.zeros((0, 2))

    for r, c, peak, area, _ in bright:
        cand = Candidate(win.row0 + r, win.col0 + c, peak, "bright", "needs second look", area)
        if can_shadow and len(dark_pts):
            v = dark_pts - np.array([r, c])
            along = v[:, 0] * drow + v[:, 1] * dcol
            across = np.abs(v[:, 0] * dcol - v[:, 1] * drow)
            radius = math.sqrt(area / math.pi)
            ok = (along > radius * 0.5) & (along <= lmax + radius + 2) & (across <= max(3.0, radius + 2))
            if ok.any():
                j = int(np.argmax(np.where(ok, -across, -np.inf)))
                cand = Candidate(
                    cand.row,
                    cand.col,
                    peak * 1.5,
                    "shadow",
                    "needs second look",
                    area,
                    {
                        "shadow_len_px": round(float(along[j]), 1),
                        "shadow_len_min_px": round(lmin, 1),
                        "shadow_len_max_px": round(lmax, 1),
                    },
                )
        out.append(cand)
    for r, c, peak, area, _ in dark:
        out.append(Candidate(win.row0 + r, win.col0 + c, peak * 0.5, "dark", "needs second look", area))
    return out


def dedupe(cands: list[Candidate], radius: float = 6.0) -> list[Candidate]:
    """Overlapping tiles see the same object twice; keep the higher-scoring copy."""
    cands = sorted(cands, key=lambda c: -c.score)
    kept: list[Candidate] = []
    pts: list[tuple[float, float]] = []
    for c in cands:
        if any(math.hypot(c.row - r, c.col - k) <= radius for r, k in pts):
            continue
        kept.append(c)
        pts.append((c.row, c.col))
    return kept


def detect_strip(strip: Strip, cfg: DetectorConfig, max_tiles: int | None = None, progress=None) -> dict:
    """Run every branch over the strip's valid footprint. Returns the per-strip entry of a candidates file."""
    cands: list[Candidate] = []
    n = 0
    for r0, r1, c0, c1 in strip.tiles(cfg.tile, cfg.overlap):
        if max_tiles is not None and n >= max_tiles:
            break
        win = strip.read(r0, r1, c0, c1)
        cands.extend(detect_tile(win, strip.label, cfg))
        n += 1
        if progress:
            progress(n, len(cands))
    cands = dedupe(cands)
    return {
        "valid_area_km2": round(strip.valid_area_km2(), 3),
        "tiles": n,
        "candidates": [c.to_json() for c in cands],
    }


def shadow_direction_evidence(win: Window, lbl: StripLabel, cfg: DetectorConfig) -> tuple[int, int]:
    """Diagnostic: how many bright patches have a dark patch just *along* vs just *against* the label's
    shadow direction. Rocks cast shadows, so the along count should win clearly on any real ground.
    Uses looser thresholds than the detector because it wants statistics over many ordinary rocks."""
    z = local_z(win.data, win.valid, cfg.background_px, cfg.smooth_sigma)
    area = (4, cfg.bright_area_px[1])
    bright = _components(z > 3.0, z, area, win.valid, cfg.edge_margin_px)
    dark = _components(z < -2.5, z, area, win.valid, cfg.edge_margin_px)
    if not bright or not dark:
        return 0, 0
    drow, dcol = geo.shadow_direction(lbl)
    lmax = geo.shadow_length_px(lbl, cfg.shadow_heights_m[1])
    dp = np.array([(r, c) for r, c, *_ in dark])
    along_n = against_n = 0
    for r, c, _, a, _ in bright:
        v = dp - np.array([r, c])
        along = v[:, 0] * drow + v[:, 1] * dcol
        across = np.abs(v[:, 0] * dcol - v[:, 1] * drow)
        radius = math.sqrt(a / math.pi)
        near = across <= max(3.0, radius + 2)
        along_n += int(((along > radius * 0.5) & (along <= lmax + radius + 2) & near).any())
        against_n += int(((along < -radius * 0.5) & (along >= -(lmax + radius + 2)) & near).any())
    return along_n, against_n

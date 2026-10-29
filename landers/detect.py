"""Physical tests, version 0. No model is involved anywhere in this module.

Branches run per tile; every candidate carries the branch that made it:

- ``bright``: a compact patch brighter than its surroundings (local z-score over an annulus),
  1 to 10 m across. Landers, backshells and parachutes are bright; so are many rocks.
- ``shadow``: a ``bright`` candidate with a dark patch adjacent to it in the direction shadows fall, at a
  distance consistent with an object 0.5 to 3 m tall under this strip's sun. The label gives the sun
  azimuth and incidence; nothing else about the image is used.
- ``sheet``: a bright, flat patch 8 to 25 m across, found at 1 m/px, no shadow required. Parachutes.
- ``dark_compact``: a compact dark patch 1 to 4 m across. Backshells and heat shields, which are dark
  on the ground; a shadow is optional and, when the patch is stretched along the shadow direction,
  raises the score.
- ``dark``: a dark patch 2.5 to 50 m across (crash scars, blast zones).

Grades here can only be "needs second look" (passes a physical test on one date) or "likely natural";
"candidate" needs a second date, which is the persistence step and not part of this module.

v0.2 (plan item 6): saturated pixels are data at the top of the range rather than no-data (v0.1 lost
saturated hardware to the no-data margin); every bright, shadow and dark_compact candidate carries the
shadow-side, isolation and saturation features of ``landers.shape``; and a versioned rules file may add to
the calibrated score of candidates that pass a feature test (``finish_tile``).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy import ndimage

from landers import geo, shape
from landers.label import StripLabel
from landers.strip import SATURATED, Strip, Window

GRADE_LOOK = "needs second look"


@dataclass
class DetectorConfig:
    version: str = "v0.2"
    frozen: bool = False
    calibration: str | None = None  # path of a landers.calibrate JSON; scores are then on the common scale
    min_calibrated_score: float = -3.0  # with a calibration, drop candidates rarer than 1000 false alarms/km2
    shape_rules: str | None = None  # path of a landers.shape rules JSON; passed rules add to the calibrated score
    # v0.2: saturated pixels (1022, 1023) are data at the top of the range, not holes. v0.1 masked them with
    # the no-data margin, which hid saturated hardware (bright metal, canopies) from every branch.
    saturated_is_data: bool = True
    band_dark_z: float = -2.0  # a band mean below this counts as shadow in shape.shadow_features
    tile: int = 2048
    overlap: int = 128
    background_px: int = 65  # annulus outer size for the local mean and std
    inner_px: int = 15
    smooth_sigma: float = 0.7
    edge_margin_px: int = 8
    # bright / shadow
    z_bright: float = 4.0
    bright_size_m: tuple[float, float] = (1.0, 10.0)
    shadow_heights_m: tuple[float, float] = (0.5, 3.0)
    shadow_min_incidence_deg: float = 35.0  # below this shadows are too short to test
    z_shadow_dark: float = -3.5
    # sheet (parachute): detected at full-res pixels * sheet_reduce
    sheet_reduce: int = 4
    sheet_background_px: int = 65
    sheet_inner_px: int = 31
    sheet_sigma: float = 1.0
    z_sheet: float = 3.0
    sheet_size_m: tuple[float, float] = (8.0, 25.0)
    sheet_flatness: float = 0.45  # mean z / peak z inside the patch; a point-like peak is not a sheet
    # dark compact (backshell, heat shield)
    z_dark_compact: float = -4.0
    dark_compact_size_m: tuple[float, float] = (1.0, 4.0)
    compact_fill: float = 0.45  # area / bounding box area
    # dark disturbance (scar)
    z_dark: float = -3.5
    dark_size_m: tuple[float, float] = (2.5, 50.0)

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


@dataclass
class Component:
    row: float
    col: float
    peak: float
    mean: float
    area: int
    bbox_h: int
    bbox_w: int
    label: int

    @property
    def radius(self) -> float:
        return math.sqrt(self.area / math.pi)


def area_range_px(size_m: tuple[float, float], scale_m: float, lo_frac: float = 0.4, hi_frac: float = 1.3):
    """Pixel-area bounds for objects ``size_m`` across; ``lo_frac`` admits elongated shapes."""
    amin = lo_frac * math.pi * (size_m[0] / scale_m / 2) ** 2
    amax = hi_frac * math.pi * (size_m[1] / scale_m / 2) ** 2
    return max(4, int(round(amin))), int(round(amax))


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


def components(mask: np.ndarray, zmap: np.ndarray, area: tuple[int, int], valid: np.ndarray, margin: int):
    """Connected components of ``mask`` with area in range, away from the tile edge and from no-data."""
    lab, n = ndimage.label(mask)
    if n == 0:
        return [], lab
    idx = np.arange(1, n + 1)
    areas = ndimage.sum(np.ones_like(lab, dtype=np.int32), lab, idx)
    keep = (areas >= area[0]) & (areas <= area[1])
    out: list[Component] = []
    if not keep.any():
        return out, lab
    absz = np.abs(zmap)
    peaks = ndimage.maximum(absz, lab, idx)
    means = ndimage.mean(absz, lab, idx)
    centroids = ndimage.center_of_mass(absz, lab, idx)
    slices = ndimage.find_objects(lab)
    h, w = mask.shape
    bad_edge = ndimage.binary_dilation(~valid, iterations=margin) if (~valid).any() else None
    for i in np.nonzero(keep)[0]:
        r, c = centroids[i]
        if r < margin or c < margin or r > h - margin or c > w - margin:
            continue
        if bad_edge is not None and bad_edge[int(r), int(c)]:
            continue
        sl = slices[i]
        out.append(
            Component(
                float(r),
                float(c),
                float(peaks[i]),
                float(means[i]),
                int(areas[i]),
                sl[0].stop - sl[0].start,
                sl[1].stop - sl[1].start,
                int(i + 1),
            )
        )
    return out, lab


def _along_across(points: np.ndarray, r: float, c: float, drow: float, dcol: float):
    v = points - np.array([r, c])
    return v[:, 0] * drow + v[:, 1] * dcol, np.abs(v[:, 0] * dcol - v[:, 1] * drow)


def _principal_axis_alignment(lab: np.ndarray, comp: Component, drow: float, dcol: float, sl=None) -> float:
    """|cos| between the component's long axis and the shadow direction, times its elongation (0 if round)."""
    sub = lab[sl] if sl is not None else lab
    rr, cc = np.nonzero(sub == comp.label)
    if len(rr) < 6:
        return 0.0
    cov = np.cov(np.vstack([rr, cc]).astype(float))
    evals, evecs = np.linalg.eigh(cov)
    if evals[1] <= 0:
        return 0.0
    elong = 1.0 - math.sqrt(max(evals[0], 0.0) / evals[1])
    axis = evecs[:, 1]
    return float(abs(axis[0] * drow + axis[1] * dcol) * elong)


def block_mean(data: np.ndarray, valid: np.ndarray, n: int):
    """Mean over valid pixels in n x n blocks; a block is valid when more than half its pixels are."""
    h, w = (data.shape[0] // n) * n, (data.shape[1] // n) * n
    v = valid[:h, :w].reshape(h // n, n, w // n, n).astype(np.float64)
    x = data[:h, :w].reshape(h // n, n, w // n, n).astype(np.float64) * v
    cnt = v.sum(axis=(1, 3))
    with np.errstate(divide="ignore", invalid="ignore"):
        m = np.where(cnt > 0, x.sum(axis=(1, 3)) / np.maximum(cnt, 1), 0.0)
    return m, cnt > (n * n) / 2


def detect_tile(win: Window, lbl: StripLabel, cfg: DetectorConfig) -> list[Candidate]:
    scale = lbl.scale_m
    sat = win.data >= SATURATED
    usable = (win.valid | sat) if cfg.saturated_is_data else win.valid
    z = local_z(win.data, usable, cfg.background_px, cfg.smooth_sigma, cfg.inner_px)
    grad = shape.gradient_magnitude(z)
    bright, b_lab = components(z > cfg.z_bright, z, area_range_px(cfg.bright_size_m, scale), usable, cfg.edge_margin_px)
    b_slices = ndimage.find_objects(b_lab) if bright else []
    small_dark, _ = components(
        z < cfg.z_shadow_dark, z, area_range_px(cfg.bright_size_m, scale), usable, cfg.edge_margin_px
    )
    dark_compact, dc_lab = components(
        z < cfg.z_dark_compact, z, area_range_px(cfg.dark_compact_size_m, scale), usable, cfg.edge_margin_px
    )
    dark, _ = components(z < cfg.z_dark, z, area_range_px(cfg.dark_size_m, scale), usable, cfg.edge_margin_px)
    dc_slices = ndimage.find_objects(dc_lab) if dark_compact else []
    b_rank = shape.tile_ranks([k.peak for k in bright])
    dc_rank = shape.tile_ranks([k.peak for k in dark_compact])
    b_iso = shape.isolation([(k.row, k.col) for k in bright])
    dc_iso = shape.isolation([(k.row, k.col) for k in dark_compact])

    out: list[Candidate] = []
    can_shadow = lbl.incidence_deg >= cfg.shadow_min_incidence_deg
    drow, dcol = geo.shadow_direction(lbl)
    lmin = geo.shadow_length_px(lbl, cfg.shadow_heights_m[0])
    lmax = geo.shadow_length_px(lbl, cfg.shadow_heights_m[1])
    dark_pts = np.array([(k.row, k.col) for k in small_dark]) if small_dark else np.zeros((0, 2))

    def side_feats(k: Component) -> dict:
        return shape.shadow_features(
            z, k.row, k.col, k.radius, drow, dcol, lmax, scale, lbl.incidence_deg, cfg.band_dark_z
        )

    for i, k in enumerate(bright):
        feats = shape.component_features(b_lab, k.label, z, grad, b_slices[k.label - 1])
        feats["tile_rank"] = b_rank[i]
        feats["isolation_px"] = b_iso[i]
        feats["saturated_px"] = shape.saturated_count(sat, b_lab, k.label, b_slices[k.label - 1])
        feats.update(side_feats(k))
        cand = Candidate(win.row0 + k.row, win.col0 + k.col, k.peak, "bright", GRADE_LOOK, k.area, dict(feats))
        if can_shadow and len(dark_pts):
            along, across = _along_across(dark_pts, k.row, k.col, drow, dcol)
            ok = (along > k.radius * 0.5) & (along <= lmax + k.radius + 2) & (across <= max(3.0, k.radius + 2))
            if ok.any():
                j = int(np.argmax(np.where(ok, -across, -np.inf)))
                shadow_peak = small_dark[j].peak
                cand = Candidate(
                    cand.row,
                    cand.col,
                    k.peak * 1.5,
                    "shadow",
                    GRADE_LOOK,
                    k.area,
                    {
                        **feats,
                        "shadow_len_px": round(float(along[j]), 1),
                        "shadow_len_min_px": round(lmin, 1),
                        "shadow_len_max_px": round(lmax, 1),
                        "shadow_ratio": round(shadow_peak / k.peak, 3) if k.peak > 0 else 0.0,
                    },
                )
        out.append(cand)

    for i, k in enumerate(dark_compact):
        fill = k.area / float(k.bbox_h * k.bbox_w)
        if fill < cfg.compact_fill:
            continue
        extra = shape.component_features(dc_lab, k.label, z, grad, dc_slices[k.label - 1])
        extra["tile_rank"] = dc_rank[i]
        extra["isolation_px"] = dc_iso[i]
        extra.update(side_feats(k))
        score = k.peak
        if can_shadow:
            align = _principal_axis_alignment(dc_lab, k, drow, dcol, dc_slices[k.label - 1])
            extra["shadow_alignment"] = round(align, 2)
            if align > 0.3:
                score *= 1.3
        out.append(Candidate(win.row0 + k.row, win.col0 + k.col, score, "dark_compact", GRADE_LOOK, k.area, extra))

    for k in dark:
        out.append(Candidate(win.row0 + k.row, win.col0 + k.col, k.peak * 0.5, "dark", GRADE_LOOK, k.area))

    # sheets at reduced resolution
    n = cfg.sheet_reduce
    if min(win.shape) >= n * cfg.sheet_background_px:
        d_r, v_r = block_mean(win.data, usable, n)
        z_r = local_z(d_r, v_r, cfg.sheet_background_px, cfg.sheet_sigma, cfg.sheet_inner_px, margin=2)
        sheets, _ = components(
            z_r > cfg.z_sheet, z_r, area_range_px(cfg.sheet_size_m, scale * n), v_r, max(2, cfg.edge_margin_px // n)
        )
        max_extent = cfg.sheet_size_m[1] * 1.4 / (scale * n)
        for k in sheets:
            flat = k.mean / k.peak if k.peak > 0 else 0.0
            if flat < cfg.sheet_flatness or max(k.bbox_h, k.bbox_w) > max_extent:
                continue
            out.append(
                Candidate(
                    win.row0 + k.row * n + n / 2 - 0.5,
                    win.col0 + k.col * n + n / 2 - 0.5,
                    k.mean,
                    "sheet",
                    GRADE_LOOK,
                    k.area * n * n,
                    {"flatness": round(flat, 2), "extent_m": round(max(k.bbox_h, k.bbox_w) * scale * n, 1)},
                )
            )
    return out


def dedupe(cands: list[Candidate], radius: float = 6.0) -> list[Candidate]:
    """Overlapping tiles see the same object twice; keep the higher-scoring copy and note the other branches.
    A grid hash keeps this linear in the number of candidates."""
    cands = sorted(cands, key=lambda c: -c.score)
    kept: list[Candidate] = []
    cells: dict[tuple[int, int], list[int]] = {}
    cell = max(radius, 1.0)
    for c in cands:
        gr, gc = int(c.row // cell), int(c.col // cell)
        hit = None
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                for i in cells.get((gr + dr, gc + dc), ()):
                    k = kept[i]
                    if math.hypot(c.row - k.row, c.col - k.col) <= radius:
                        hit = i
                        break
                if hit is not None:
                    break
            if hit is not None:
                break
        if hit is not None:
            also = kept[hit].extra.setdefault("also", [])
            if c.branch != kept[hit].branch and c.branch not in also:
                also.append(c.branch)
            continue
        cells.setdefault((gr, gc), []).append(len(kept))
        kept.append(c)
    return kept


def load_calibration(cfg: DetectorConfig):
    if not cfg.calibration:
        return None
    from landers.calibrate import Calibration

    return Calibration.load(cfg.calibration)


def load_shape_rules(cfg: DetectorConfig):
    return shape.ShapeRules.load(cfg.shape_rules) if cfg.shape_rules else None


def finish_tile(cands: list[Candidate], cfg: DetectorConfig, cal, rules) -> list[Candidate]:
    """Calibrate, drop what is below the floor, then add the shape-rule gains (in that order, so the
    floor is a property of the branch score alone and ``scripts/rescore.py`` can reproduce the rules)."""
    if cal is not None:
        from landers.calibrate import apply

        cands = [c for c in apply(cands, cal) if c.score >= cfg.min_calibrated_score]
    if rules is not None:
        cands = shape.apply_rules(cands, rules)
    return cands


def detect_strip(strip: Strip, cfg: DetectorConfig, max_tiles: int | None = None, progress=None) -> dict:
    """Run every branch over the strip's valid footprint. Returns the per-strip entry of a candidates file."""
    cal = load_calibration(cfg)
    rules = load_shape_rules(cfg)
    cands: list[Candidate] = []
    n = 0
    for r0, r1, c0, c1 in strip.tiles(cfg.tile, cfg.overlap):
        if max_tiles is not None and n >= max_tiles:
            break
        win = strip.read(r0, r1, c0, c1)
        tile_cands = finish_tile(detect_tile(win, strip.label, cfg), cfg, cal, rules)
        cands.extend(tile_cands)
        n += 1
        if progress:
            progress(n, len(cands))
    cands = dedupe(cands)
    return {
        "valid_area_km2": round(strip.valid_area_km2(), 3),
        "scale_m": strip.label.scale_m,
        "tiles": n,
        "candidates": [c.to_json() for c in cands],
    }


_WORKER: dict = {}


def _worker_init(observation_id: str, cfg_json: dict):
    from landers.strip import Strip as _Strip

    _WORKER["strip"] = _Strip.open(observation_id)
    _WORKER["cfg"] = DetectorConfig(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in cfg_json.items()})
    _WORKER["cal"] = load_calibration(_WORKER["cfg"])
    _WORKER["rules"] = load_shape_rules(_WORKER["cfg"])


def _worker_tile(bounds):
    r0, r1, c0, c1 = bounds
    strip, cfg = _WORKER["strip"], _WORKER["cfg"]
    win = strip.read(r0, r1, c0, c1)
    return finish_tile(detect_tile(win, strip.label, cfg), cfg, _WORKER["cal"], _WORKER["rules"])


def detect_strip_parallel(
    strip: Strip, cfg: DetectorConfig, jobs: int, max_tiles: int | None = None, progress=None
) -> dict:
    """Same result as ``detect_strip`` with ``jobs`` worker processes, each holding its own open strip.
    About 1.5 GB per worker at peak, so three is the most this 8 GB machine should run."""
    import multiprocessing as mp

    tiles = list(strip.tiles(cfg.tile, cfg.overlap))
    if max_tiles is not None:
        tiles = tiles[:max_tiles]
    cands: list[Candidate] = []
    ctx = mp.get_context("spawn")
    with ctx.Pool(jobs, initializer=_worker_init, initargs=(strip.label.observation_id, cfg.to_json())) as pool:
        for n, part in enumerate(pool.imap(_worker_tile, tiles, chunksize=1), start=1):
            cands.extend(part)
            if progress:
                progress(n, len(cands))
    cands = dedupe(cands)
    return {
        "valid_area_km2": round(strip.valid_area_km2(), 3),
        "scale_m": strip.label.scale_m,
        "tiles": len(tiles),
        "candidates": [c.to_json() for c in cands],
    }


def shadow_direction_evidence(win: Window, lbl: StripLabel, cfg: DetectorConfig) -> tuple[int, int]:
    """Diagnostic: how many bright patches have a dark patch just *along* vs just *against* the label's
    shadow direction. Rocks cast shadows, so the along count should win clearly on any real ground.
    Uses looser thresholds than the detector because it wants statistics over many ordinary rocks."""
    z = local_z(win.data, win.valid, cfg.background_px, cfg.smooth_sigma, cfg.inner_px)
    area = (4, area_range_px(cfg.bright_size_m, lbl.scale_m)[1])
    bright, _ = components(z > 3.0, z, area, win.valid, cfg.edge_margin_px)
    dark, _ = components(z < -2.5, z, area, win.valid, cfg.edge_margin_px)
    if not bright or not dark:
        return 0, 0
    drow, dcol = geo.shadow_direction(lbl)
    lmax = geo.shadow_length_px(lbl, cfg.shadow_heights_m[1])
    dp = np.array([(k.row, k.col) for k in dark])
    along_n = against_n = 0
    for k in bright:
        along, across = _along_across(dp, k.row, k.col, drow, dcol)
        near = across <= max(3.0, k.radius + 2)
        along_n += int(((along > k.radius * 0.5) & (along <= lmax + k.radius + 2) & near).any())
        against_n += int(((along < -k.radius * 0.5) & (along >= -(lmax + k.radius + 2)) & near).any())
    return along_n, against_n

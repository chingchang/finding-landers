"""Registration for the pairs item 11 could not register, and the cache of every pair's registration nodes.

``landers.persist`` matches windows pixel for pixel and takes its coarse offset from the 1/16 overviews along
one column. That fails on a pair of different map scales, whatever the ground. This module does the same job
across scales and is not part of the frozen detector, so ``landers/persist.py`` stays byte for byte the tag's:

- the coarse offset is measured at reduced resolution, each strip read at the JPEG 2000 level that gives both
  the same metres per pixel, high-pass filtered, at spots spread over the ground the two strips share;
- at a fine node the coarser strip's window is resampled to the finer strip's scale, then matched with
  ``landers.persist.register_arrays`` and accepted by the same rule as ``register_at``.

A node's offsets stay in pixels of the second strip, as in ``landers.persist``, so ``map_to_b`` and
``annotate`` take these nodes unchanged. The cache needs no JP2 to be read back, so persistence can still run
after the strips are deleted.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy import ndimage

from landers import persist as lp

COARSE_M_PER_PX = (2.0, 4.0)  # tried in this order until enough spots agree
COARSE_SIZE = 256  # template, reduced pixels
COARSE_SEARCH = 64  # either way, reduced pixels
COARSE_HIGHPASS_PX = 32.0  # Gaussian sigma, reduced pixels; removes the albedo and haze gradient
COARSE_MIN_AGREE = 3  # spots that must agree before an offset is believed
COARSE_AGREE_M = 32.0  # within this of the spots' median
# the node acceptance rule of landers.persist.register_at, repeated because that one is inline
MIN_CORR = 0.25
MIN_RATIO = 1.15
SEARCH_MARGIN = 4


def grid_zooms(strip_a, strip_b) -> tuple[int, int]:
    """Whole factors that bring each strip to the finer of the two scales: (1, 2) for 0.25 m with 0.5 m."""
    fine = min(strip_a.label.scale_m, strip_b.label.scale_m)
    za, zb = strip_a.label.scale_m / fine, strip_b.label.scale_m / fine
    if abs(za - round(za)) > 1e-6 or abs(zb - round(zb)) > 1e-6:
        raise ValueError(f"scales {strip_a.label.scale_m} and {strip_b.label.scale_m} are not whole multiples")
    return int(round(za)), int(round(zb))


def upsample(x: np.ndarray, zoom: int) -> np.ndarray:
    """Linear resampling by a whole factor. The output covers exactly the input's extent, so the two windows'
    centres stay the same point on the ground."""
    if zoom == 1:
        return x
    return ndimage.zoom(x.astype(np.float32), zoom, order=1, mode="nearest", grid_mode=True)


def _shared_spots(strip_a, strip_b, n_spots: int, margin_m: float) -> list[tuple[float, float, float, float]]:
    """Up to ``n_spots`` positions, spread along the first strip, valid on both and clear of the second's edge."""
    ova, ovb = strip_a.overview.valid, strip_b.overview.valid
    stepa, stepb = strip_a.overview_step, strip_b.overview_step
    mb = margin_m / strip_b.label.scale_m
    rows, cols = np.nonzero(ova)
    if not len(rows):
        return []
    stride = max(len(rows) // 4000, 1)
    spots = []
    for r16, c16 in zip(rows[::stride], cols[::stride]):
        ra, ca = float(r16) * stepa, float(c16) * stepa
        rb, cb = lp.predict_in_b(strip_a, strip_b, ra, ca)
        if not (mb <= rb < strip_b.shape[0] - mb and mb <= cb < strip_b.shape[1] - mb):
            continue
        if ovb[int(rb // stepb), int(cb // stepb)]:
            spots.append((ra, ca, rb, cb))
    if not spots:
        return []
    return [spots[i] for i in np.unique(np.linspace(0, len(spots) - 1, n_spots).astype(int))]


def _level(m_per_px: float, scale_m: float) -> int:
    step = m_per_px / scale_m
    k = int(round(math.log2(step)))
    if abs(2**k - step) > 1e-6:
        raise ValueError(f"{m_per_px} m per px is not a JPEG 2000 level of a {scale_m} m strip")
    return 2**k


def _centred_reduced(strip, row: float, col: float, n: int, step: int):
    half = n * step // 2
    r, c = int(round(row)), int(round(col))
    return strip.read_reduced(r - half, r + half, c - half, c + half, step)


def coarse_offset(strip_a, strip_b, n_spots: int = 25) -> tuple[float, float, dict]:
    """Offset of B from the label prediction in B pixels, with the record of how it was reached. The offset is
    (0, 0) and ``found`` False when too few spots agree at any resolution: then the pair is not registered."""
    tried = []
    for m in COARSE_M_PER_PX:
        stepa, stepb = _level(m, strip_a.label.scale_m), _level(m, strip_b.label.scale_m)
        margin = (COARSE_SIZE + 2 * COARSE_SEARCH) * m / 2
        found, corrs = [], []
        for ra, ca, rb, cb in _shared_spots(strip_a, strip_b, n_spots, margin):
            wa = _centred_reduced(strip_a, ra, ca, COARSE_SIZE, stepa)
            wb = _centred_reduced(strip_b, rb, cb, COARSE_SIZE + 2 * COARSE_SEARCH, stepb)
            if wa.valid.mean() < 0.9 or wb.valid.mean() < 0.9:
                continue
            hp = [x.astype(np.float32) - ndimage.gaussian_filter(x.astype(np.float32), COARSE_HIGHPASS_PX)
                  for x in (wa.data, wb.data)]
            dr, dc, corr, ratio = lp.register_arrays(hp[0], wa.valid, hp[1], wb.valid)
            corrs.append(round(corr, 3))
            if corr >= MIN_CORR and ratio >= MIN_RATIO:
                found.append((dr * stepb, dc * stepb))
        rec = {"m_per_px": m, "spots_read": len(corrs), "spots_good": len(found),
               "median_corr": round(float(np.median(corrs)), 3) if corrs else None,
               "max_corr": max(corrs) if corrs else None}
        tried.append(rec)
        if len(found) >= COARSE_MIN_AGREE:
            med_r = float(np.median([f[0] for f in found]))
            med_c = float(np.median([f[1] for f in found]))
            limit = COARSE_AGREE_M / strip_b.label.scale_m
            agree = sum(math.hypot(f[0] - med_r, f[1] - med_c) <= limit for f in found)
            rec["spots_agree"] = agree
            if agree >= COARSE_MIN_AGREE:
                return med_r, med_c, {"found": True, "tried": tried}
    return 0.0, 0.0, {"found": False, "tried": tried}


def register_node(strip_a, strip_b, row_a: float, col_a: float, size: int, search: int, prior: tuple[float, float],
                  zooms: tuple[int, int]) -> lp.Node:
    """Fine registration at one node. ``size`` and ``search`` are in pixels of the finer scale, ``prior`` and
    the node's offsets in pixels of B. Equal scales give what ``landers.persist.register_at`` gives."""
    za, zb = zooms
    rb0, cb0 = lp.predict_in_b(strip_a, strip_b, row_a, col_a)
    rb, cb = rb0 + prior[0], cb0 + prior[1]
    node = lp.Node(row_a, col_a, rb0, cb0, prior[0], prior[1], 0.0, 0.0, False)
    half_b = (size // 2 + search) / zb
    hb, wb_ = strip_b.shape
    if not (half_b <= rb < hb - half_b and half_b <= cb < wb_ - half_b):
        node.note = "predicted position too near the edge of the second strip"
        return node
    wa = strip_a.read_centered(row_a, col_a, size // za)
    if wa.valid.mean() < 0.9:
        node.note = "first window mostly invalid"
        return node
    wb = strip_b.read_centered(rb, cb, (size + 2 * search) // zb)
    if wb.valid.mean() < 0.9:
        node.note = "second window mostly invalid"
        return node
    ta, tv = upsample(wa.data, za), upsample(wa.valid.astype(np.float32), za) > 0.5
    sb, sv = upsample(wb.data, zb), upsample(wb.valid.astype(np.float32), zb) > 0.5
    d_r, d_c, corr, ratio = lp.register_arrays(ta, tv, sb, sv)
    # where the two windows' centres are, each in its own strip's pixels
    centre_ar = wa.row0 + (wa.shape[0] - 1) / 2
    centre_ac = wa.col0 + (wa.shape[1] - 1) / 2
    centre_br = wb.row0 + (wb.shape[0] - 1) / 2
    centre_bc = wb.col0 + (wb.shape[1] - 1) / 2
    k = za / zb  # B pixels per A pixel
    node.drow = centre_br + d_r / zb + (row_a - centre_ar) * k - rb0
    node.dcol = centre_bc + d_c / zb + (col_a - centre_ac) * k - cb0
    node.corr, node.peak_ratio = corr, ratio
    node.ok = corr >= MIN_CORR and ratio >= MIN_RATIO and abs(d_r) < search - SEARCH_MARGIN and abs(d_c) < search - SEARCH_MARGIN
    if not node.ok:
        node.note = "weak or ambiguous match"
    return node


def mark_outliers(nodes: list[lp.Node], min_px: float) -> None:
    """The outlier test of ``landers.persist.offset_field``: ok nodes far from the strip's median go not ok."""
    good = [n for n in nodes if n.ok]
    if len(good) < 4:
        return
    med_r = float(np.median([n.drow for n in good]))
    med_c = float(np.median([n.dcol for n in good]))
    mad = float(np.median([math.hypot(n.drow - med_r, n.dcol - med_c) for n in good])) + 1.0
    for n in good:
        if math.hypot(n.drow - med_r, n.dcol - med_c) > max(6 * mad, min_px):
            n.ok = False
            n.note = "offset far from the strip's median; outlier"


def offset_field(strip_a, strip_b, spacing_m: float = 1024.0, size: int = 384, search: int = 192) -> tuple[list[lp.Node], dict]:
    """Nodes on a grid over A's valid footprint, every ``spacing_m`` (4096 px at 0.25 m, as item 11). No nodes
    are read when no coarse offset was found: item 11 already tried this pair with no prior and got none."""
    prior_r, prior_c, rec = coarse_offset(strip_a, strip_b)
    if not rec["found"]:
        return [], {"coarse": rec}
    rec = {"coarse": rec, "prior_px": [round(prior_r, 1), round(prior_c, 1)]}
    zooms = grid_zooms(strip_a, strip_b)
    spacing = int(round(spacing_m / strip_a.label.scale_m))
    ov, step = strip_a.overview.valid, strip_a.overview_step
    half_a = size // (2 * zooms[0])
    nodes = []
    for r in range(spacing // 2, strip_a.shape[0] - spacing // 2, spacing):
        for c in range(spacing // 2, strip_a.shape[1] - spacing // 2, spacing):
            sub = ov[max(r - half_a, 0) // step : (r + half_a) // step + 1, max(c - half_a, 0) // step : (c + half_a) // step + 1]
            if sub.size == 0 or sub.mean() < 0.95:
                continue
            nodes.append(register_node(strip_a, strip_b, float(r), float(c), size, search, (prior_r, prior_c), zooms))
    mark_outliers(nodes, min_px=12.0 / zooms[1])
    return nodes, rec


# ---------------------------------------------------------------- the cache


def nodes_path(cache_dir: Path, a: str, b: str) -> Path:
    return Path(cache_dir) / f"nodes_{a}_{b}.json"


def write_nodes(cache_dir: Path, pair: list[str], km2_shared: float, source: str, directions: dict) -> Path:
    """``directions`` maps "from->to" to its {"from", "to", "registration", "nodes"} (nodes as JSON)."""
    path = nodes_path(cache_dir, pair[0], pair[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.part")
    tmp.write_text(json.dumps({"pair": pair, "km2_shared": km2_shared, "source": source, "directions": directions}, indent=1))
    tmp.replace(path)
    return path


def nodes_from_json(rows: list[dict]) -> list[lp.Node]:
    return [lp.Node(**r) for r in rows]


def is_registered(oks: list[int]) -> bool:
    """A pair counts as registered when either direction has at least 4 ok nodes, as in survivors.json."""
    return max(oks) >= 4

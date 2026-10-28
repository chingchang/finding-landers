"""Persistence: is a candidate from one date also there on another date of the same ground?

The two labels disagree by tens of metres (no ground control), so a candidate's position in the second
strip is first predicted through both map projections and then corrected by a local image registration:
a window of the first strip is template-matched against a larger window of the second around the
predicted spot. Registration is done once on a sparse grid of nodes over the strip and interpolated, so a
strip pair costs a few hundred window reads rather than one per candidate.

A candidate is "seen" on the second date when that date's own candidate list has a candidate of the same
family (bright: bright/shadow/sheet; dark: dark/dark_compact) within ``radius_px`` of the mapped position.
Seen on two dates and passing a physical test is what the brief requires for the grade "candidate"; this
module assigns that grade and nothing else raises it.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
from skimage.feature import match_template

from landers import geo
from landers.strip import Strip

FAMILY = {"bright": "bright", "shadow": "bright", "sheet": "bright", "dark": "dark", "dark_compact": "dark"}
GRADE_CANDIDATE = "candidate"
GRADE_LOOK = "needs second look"


@dataclass
class Node:
    row_a: float
    col_a: float
    row_b_pred: float
    col_b_pred: float
    drow: float  # measured position in B minus predicted, in B pixels
    dcol: float
    corr: float  # peak normalised correlation
    peak_ratio: float  # peak over the best peak more than 8 px away
    ok: bool
    note: str = ""


def predict_in_b(strip_a: Strip, strip_b: Strip, row: float, col: float) -> tuple[float, float]:
    lat, lon = geo.rowcol_to_latlon(strip_a.label, row, col)
    rb, cb = geo.latlon_to_rowcol(strip_b.label, lat, lon)
    return float(rb), float(cb)


def _normalise(data: np.ndarray, valid: np.ndarray) -> np.ndarray:
    x = data.astype(np.float32)
    if valid.sum() < 100:
        return np.zeros_like(x)
    m, s = float(x[valid].mean()), float(x[valid].std())
    x = (x - m) / max(s, 1.0)
    x[~valid] = 0.0
    return x


def register_arrays(template: np.ndarray, t_valid: np.ndarray, search_img: np.ndarray, s_valid: np.ndarray):
    """Offset (drow, dcol) of ``template`` inside ``search_img`` relative to the centred position, with the
    peak correlation and the ratio of the peak to the best peak more than 8 px away."""
    t = _normalise(template, t_valid)
    s = _normalise(search_img, s_valid)
    if not t.any() or not s.any():
        return 0.0, 0.0, 0.0, 0.0
    cc = match_template(s, t, pad_input=False)
    if cc.size == 0:
        return 0.0, 0.0, 0.0, 0.0
    pr, pc = np.unravel_index(int(np.argmax(cc)), cc.shape)
    peak = float(cc[pr, pc])
    yy, xx = np.mgrid[: cc.shape[0], : cc.shape[1]]
    far = (yy - pr) ** 2 + (xx - pc) ** 2 > 8**2
    second = float(cc[far].max()) if far.any() else -1.0
    ratio = peak / second if second > 1e-6 else float("inf")
    centre_r = (cc.shape[0] - 1) / 2
    centre_c = (cc.shape[1] - 1) / 2
    # sub-pixel refinement by a parabola through the peak's neighbours
    dr = dc = 0.0
    if 0 < pr < cc.shape[0] - 1:
        a, b, c = cc[pr - 1, pc], cc[pr, pc], cc[pr + 1, pc]
        if a - 2 * b + c < 0:
            dr = 0.5 * (a - c) / (a - 2 * b + c)
    if 0 < pc < cc.shape[1] - 1:
        a, b, c = cc[pr, pc - 1], cc[pr, pc], cc[pr, pc + 1]
        if a - 2 * b + c < 0:
            dc = 0.5 * (a - c) / (a - 2 * b + c)
    return float(pr + dr - centre_r), float(pc + dc - centre_c), peak, ratio


def coarse_offset(
    strip_a: Strip, strip_b: Strip, n_spots: int = 9, size: int = 192, search: int = 160
) -> tuple[float, float, dict]:
    """Gross offset of B from the label prediction, in full-resolution pixels, from the 1/16 overviews.
    Tried at ``n_spots`` places along the first strip whose prediction lands inside the second strip's
    footprint; the median of the good ones is returned."""
    oa, ob = strip_a.overview, strip_b.overview
    step = strip_a.overview_step
    found = []
    rows = np.linspace(size, oa.data.shape[0] - size, n_spots).round().astype(int)
    c = oa.data.shape[1] // 2
    for r in rows:
        ta = oa.data[r - size // 2 : r + size // 2, c - size // 2 : c + size // 2]
        tv = oa.valid[r - size // 2 : r + size // 2, c - size // 2 : c + size // 2]
        if tv.mean() < 0.95:
            continue
        rb, cb = predict_in_b(strip_a, strip_b, r * step + step / 2 - 0.5, c * step + step / 2 - 0.5)
        rb, cb = int(round(rb / step)), int(round(cb / step))
        if not (0 <= rb < ob.data.shape[0] and 0 <= cb < ob.data.shape[1]) or not ob.valid[rb, cb]:
            continue
        h = size // 2 + search
        r0, c0 = max(rb - h, 0), max(cb - h, 0)
        sb, sv = ob.data[r0 : rb + h, c0 : cb + h], ob.valid[r0 : rb + h, c0 : cb + h]
        if sb.shape[0] < size + 8 or sb.shape[1] < size + 8 or sv.mean() < 0.5:
            continue
        dr, dc, corr, ratio = register_arrays(ta, tv, sb, sv)
        # the search window may have been clipped at the top/left: its centre is then not at (rb, cb)
        dr += (rb - r0) - (sb.shape[0] - 1) / 2
        dc += (cb - c0) - (sb.shape[1] - 1) / 2
        if corr >= 0.3 and ratio >= 1.3:
            found.append((dr * step, dc * step, corr))
    if not found:
        return 0.0, 0.0, {"spots": 0}
    drs = np.array([f[0] for f in found])
    dcs = np.array([f[1] for f in found])
    spread = float(np.median(np.hypot(drs - np.median(drs), dcs - np.median(dcs))))
    return float(np.median(drs)), float(np.median(dcs)), {"spots": len(found), "spread_px": round(spread, 1)}


def register_at(
    strip_a: Strip,
    strip_b: Strip,
    row_a: float,
    col_a: float,
    size: int = 384,
    search: int = 192,
    prior: tuple[float, float] = (0.0, 0.0),
) -> Node:
    """Fine registration around the label prediction plus ``prior`` (the coarse offset). The node's
    drow/dcol are the total offset from the label prediction."""
    rb0, cb0 = predict_in_b(strip_a, strip_b, row_a, col_a)
    rb, cb = rb0 + prior[0], cb0 + prior[1]
    node = Node(row_a, col_a, rb0, cb0, prior[0], prior[1], 0.0, 0.0, False)
    hb, wb_ = strip_b.shape
    if not (search + size // 2 <= rb < hb - search - size // 2 and search + size // 2 <= cb < wb_ - search - size // 2):
        node.note = "predicted position too near the edge of the second strip"
        return node
    wa = strip_a.read_centered(row_a, col_a, size)
    if wa.valid.mean() < 0.9:
        node.note = "first window mostly invalid"
        return node
    wb = strip_b.read_centered(rb, cb, size + 2 * search)
    if wb.valid.mean() < 0.9:
        node.note = "second window mostly invalid"
        return node
    drow, dcol, corr, ratio = register_arrays(wa.data, wa.valid, wb.data, wb.valid)
    # read_centered rounds the centre; account for the two roundings
    drow += (round(rb) - rb) - (round(row_a) - row_a)
    dcol += (round(cb) - cb) - (round(col_a) - col_a)
    node.drow, node.dcol, node.corr, node.peak_ratio = prior[0] + drow, prior[1] + dcol, corr, ratio
    node.ok = corr >= 0.25 and ratio >= 1.15 and abs(drow) < search - 4 and abs(dcol) < search - 4
    if not node.ok:
        node.note = "weak or ambiguous match"
    return node


def offset_field(
    strip_a: Strip, strip_b: Strip, spacing: int = 4096, size: int = 384, search: int = 192, progress=None
) -> list[Node]:
    """Coarse offset from the overviews, then fine registration on a grid over the first strip's valid
    footprint; outliers against the strip's median are marked not ok."""
    prior = coarse_offset(strip_a, strip_b)[:2]
    ov = strip_a.overview.valid
    step = strip_a.overview_step
    nodes: list[Node] = []
    rows = range(spacing // 2, strip_a.shape[0] - spacing // 2, spacing)
    cols = range(spacing // 2, strip_a.shape[1] - spacing // 2, spacing)
    for r in rows:
        for c in cols:
            sub = ov[
                max(r - size, 0) // step : (r + size) // step + 1, max(c - size, 0) // step : (c + size) // step + 1
            ]
            if sub.size == 0 or sub.mean() < 0.95:
                continue
            nodes.append(register_at(strip_a, strip_b, float(r), float(c), size, search, prior))
            if progress:
                progress(len(nodes), sum(n.ok for n in nodes))
    good = [n for n in nodes if n.ok]
    if len(good) >= 4:
        med_r = float(np.median([n.drow for n in good]))
        med_c = float(np.median([n.dcol for n in good]))
        mad = float(np.median([math.hypot(n.drow - med_r, n.dcol - med_c) for n in good])) + 1.0
        for n in good:
            if math.hypot(n.drow - med_r, n.dcol - med_c) > max(6 * mad, 12.0):
                n.ok = False
                n.note = "offset far from the strip's median; outlier"
    return nodes


def interpolate(nodes: list[Node], row_a: float, col_a: float, k: int = 4) -> tuple[float, float, float]:
    """Inverse-distance weighted offset from the k nearest ok nodes; third value is the nearest distance."""
    good = [n for n in nodes if n.ok]
    if not good:
        return 0.0, 0.0, float("inf")
    d = np.array([math.hypot(n.row_a - row_a, n.col_a - col_a) for n in good])
    idx = np.argsort(d)[:k]
    w = 1.0 / (d[idx] + 1.0)
    dr = float(np.sum(w * np.array([good[i].drow for i in idx])) / w.sum())
    dc = float(np.sum(w * np.array([good[i].dcol for i in idx])) / w.sum())
    return dr, dc, float(d[idx[0]])


def map_to_b(
    strip_a: Strip, strip_b: Strip, nodes: list[Node], row_a: float, col_a: float
) -> tuple[float, float, float]:
    rb, cb = predict_in_b(strip_a, strip_b, row_a, col_a)
    dr, dc, near = interpolate(nodes, row_a, col_a)
    return rb + dr, cb + dc, near


def annotate(
    cands_a: list[dict],
    cands_b: list[dict],
    strip_a: Strip,
    strip_b: Strip,
    nodes: list[Node],
    radius_px: float,
    max_node_distance: float = 8192.0,
) -> dict:
    """Add ``extra.persist`` to each candidate of A and set the grade. Returns counts."""
    fam_b: dict[str, list[tuple[float, float, dict]]] = {"bright": [], "dark": []}
    for c in cands_b:
        fam_b[FAMILY.get(c["branch"], "bright")].append((float(c["row"]), float(c["col"]), c))
    pts = {f: np.array([(r, k) for r, k, _ in v]) if v else np.zeros((0, 2)) for f, v in fam_b.items()}
    counts = {"seen": 0, "not_seen": 0, "unregistered": 0}
    for c in cands_a:
        rb, cb, near = map_to_b(strip_a, strip_b, nodes, float(c["row"]), float(c["col"]))
        extra = c.setdefault("extra", {})
        if near > max_node_distance:
            extra["persist"] = {"seen": None, "note": "no registration node near enough"}
            counts["unregistered"] += 1
            continue
        fam = FAMILY.get(c["branch"], "bright")
        p = pts[fam]
        seen = False
        best = None
        if len(p):
            d = np.hypot(p[:, 0] - rb, p[:, 1] - cb)
            j = int(np.argmin(d))
            if d[j] <= radius_px:
                seen = True
                best = fam_b[fam][j][2]
                extra["persist"] = {
                    "seen": True,
                    "distance_px": round(float(d[j]), 1),
                    "branch_b": best["branch"],
                    "score_b": round(float(best["score"]), 3),
                    "row_b": round(rb, 1),
                    "col_b": round(cb, 1),
                }
        if not seen:
            extra["persist"] = {"seen": False, "row_b": round(rb, 1), "col_b": round(cb, 1)}
        c["grade"] = GRADE_CANDIDATE if seen else GRADE_LOOK
        counts["seen" if seen else "not_seen"] += 1
    return counts


def nodes_summary(nodes: list[Node]) -> dict:
    good = [n for n in nodes if n.ok]
    out = {"nodes": len(nodes), "ok": len(good)}
    if good:
        dr = np.array([n.drow for n in good])
        dc = np.array([n.dcol for n in good])
        out.update(
            {
                "median_drow": round(float(np.median(dr)), 1),
                "median_dcol": round(float(np.median(dc)), 1),
                "spread_px": round(float(np.median(np.hypot(dr - np.median(dr), dc - np.median(dc)))), 1),
                "median_corr": round(float(np.median([n.corr for n in good])), 3),
            }
        )
    return out


def nodes_to_json(nodes: list[Node]) -> list[dict]:
    return [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in asdict(n).items()} for n in nodes]

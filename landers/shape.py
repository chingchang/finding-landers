"""Shape and shadow features of small-object candidates (bright, shadow, dark_compact), and the versioned
rules that put some of them into the score.

Every feature is recorded on every candidate of those branches. A feature enters the score only through a
rules file (``landers/shape_v<n>.json``): a rule names a branch set, a feature, a direction and a threshold,
and carries the fraction ``p`` of that branch's false alarms on the tuning strips that pass it. A candidate
that passes gains ``-log10(p)`` on the calibrated scale, which keeps the scale's meaning (minus log10 of the
false-alarm rate): among candidates that pass, false alarms are ``p`` times rarer. A candidate that fails
keeps its score; nothing is dropped. The rules are measured by ``scripts/feature_percentiles.py`` against
the answer key and written down with the measurement they came from.

Component features (``component_features``):

- ``circularity``: 4 pi area / perimeter^2 (1 for a disc; rocks and slopes are lower).
- ``fill``: area over bounding-box area.
- ``elongation``: 1 - sqrt(minor/major) of the second moments (0 for a disc).
- ``edge_sharpness``: mean |gradient of z| on the boundary over the peak |z| (crisp edges score higher).
- ``tile_rank``: how many components of the same sign in the tile have a higher peak (0 = the strongest).

Shadow-side features (``shadow_features``), from the label's sun azimuth and incidence only: the mean z in
a band as wide as the object, at each pixel step outward from its edge, on the anti-sun side (where a
shadow would fall) and on the sun side (where nothing should be dark), out to the shadow length of a 3 m
object plus a margin.

- ``anti_sun_min_z``: darkest band value on the anti-sun side.
- ``sun_min_z``: darkest band value on the sun side.
- ``two_sided``: ``sun_min_z - anti_sun_min_z``; positive when the dark is on the anti-sun side only.
- ``shadow_run_px``: length of the dark run (band z below ``dark_z``) on the anti-sun side.
- ``shadow_height_m``: that run as a height, run * scale / tan(incidence); 0 when there is no run.
- ``sun_max_z``: brightest band value on the sun side (for a dark candidate: is there an object that
  could cast it).

Other:

- ``isolation_px``: distance to the nearest other component of the same branch family in the tile, capped
  at ``ISOLATION_CAP_PX``. Rocks come in fields; hardware tends to sit alone.
- ``saturated_px``: pixels of the component at the sensor's saturation. Natural ground is rarely
  saturated at HiRISE exposure; bright hardware often is.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

FEATURES = ("circularity", "fill", "elongation", "edge_sharpness", "tile_rank")
SHADOW_FEATURES = ("anti_sun_min_z", "sun_min_z", "two_sided", "shadow_run_px", "shadow_height_m", "sun_max_z")
ISOLATION_CAP_PX = 256.0


def component_features(lab: np.ndarray, label: int, zmap: np.ndarray, grad: np.ndarray, sl: tuple) -> dict:
    """Features of one labelled component from its bounding slice ``sl`` of the label image."""
    pad = 2
    r0, r1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, lab.shape[0])
    c0, c1 = max(sl[1].start - pad, 0), min(sl[1].stop + pad, lab.shape[1])
    m = lab[r0:r1, c0:c1] == label
    area = int(m.sum())
    if area == 0:
        return {}
    eroded = ndimage.binary_erosion(m)
    boundary = m & ~eroded
    perimeter = int(boundary.sum())
    circ = min(1.0, 4 * math.pi * area / (perimeter**2)) if perimeter > 0 else 0.0
    bh, bw = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
    fill = area / float(bh * bw)
    rr, cc = np.nonzero(m)
    if len(rr) >= 3:
        cov = np.cov(np.vstack([rr, cc]).astype(float))
        ev = np.linalg.eigvalsh(cov)
        elong = 1.0 - math.sqrt(max(ev[0], 0.0) / ev[1]) if ev[1] > 0 else 0.0
    else:
        elong = 0.0
    z = zmap[r0:r1, c0:c1]
    g = grad[r0:r1, c0:c1]
    peak = float(np.abs(z[m]).max())
    sharp = float(g[boundary].mean() / peak) if peak > 0 and boundary.any() else 0.0
    return {
        "circularity": round(circ, 3),
        "fill": round(fill, 3),
        "elongation": round(elong, 3),
        "edge_sharpness": round(sharp, 3),
    }


def gradient_magnitude(zmap: np.ndarray) -> np.ndarray:
    gy = ndimage.sobel(zmap, axis=0) / 8.0
    gx = ndimage.sobel(zmap, axis=1) / 8.0
    return np.hypot(gy, gx)


def tile_ranks(peaks: list[float]) -> list[int]:
    order = sorted(range(len(peaks)), key=lambda i: -peaks[i])
    rank = [0] * len(peaks)
    for k, i in enumerate(order):
        rank[i] = k
    return rank


# ---------------------------------------------------------------- shadow-side features


def band_profile(
    z: np.ndarray, r: float, c: float, drow: float, dcol: float, half_width: int, start: int, stop: int
) -> np.ndarray:
    """Mean of ``z`` across a band ``2 * half_width + 1`` pixels wide, centred on the ray from ``(r, c)``
    along the unit vector ``(drow, dcol)``, at each integer distance from ``start`` to ``stop`` inclusive.
    NaN where the band leaves the array."""
    h, w = z.shape
    along = np.arange(start, stop + 1, dtype=float)
    across = np.arange(-half_width, half_width + 1, dtype=float)
    prow, pcol = -dcol, drow  # perpendicular unit vector
    rr = r + along[:, None] * drow + across[None, :] * prow
    cc = c + along[:, None] * dcol + across[None, :] * pcol
    ri = np.rint(rr).astype(int)
    ci = np.rint(cc).astype(int)
    inside = (ri >= 0) & (ri < h) & (ci >= 0) & (ci < w)
    vals = np.full(ri.shape, np.nan)
    vals[inside] = z[ri[inside], ci[inside]]
    n = inside.sum(axis=1)
    out = np.full(len(along), np.nan)
    ok = n > 0
    out[ok] = np.nansum(vals[ok], axis=1) / n[ok]
    return out


def _dark_run(profile: np.ndarray, dark_z: float) -> int:
    """Length of the longest run of consecutive band values below ``dark_z``."""
    best = run = 0
    for v in profile:
        if not np.isnan(v) and v < dark_z:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def shadow_features(
    z: np.ndarray,
    r: float,
    c: float,
    radius_px: float,
    drow: float,
    dcol: float,
    reach_px: float,
    scale_m: float,
    incidence_deg: float,
    dark_z: float = -2.0,
) -> dict:
    """Shadow-side features of a component at ``(r, c)`` with equivalent radius ``radius_px``. ``reach_px``
    is how far beyond the edge to look (the shadow length of the tallest object the test allows)."""
    start = int(math.ceil(radius_px)) + 1
    stop = start + int(math.ceil(reach_px)) + 2
    half = max(1, int(round(radius_px)))
    anti = band_profile(z, r, c, drow, dcol, half, start, stop)
    sun = band_profile(z, r, c, -drow, -dcol, half, start, stop)
    if np.all(np.isnan(anti)) or np.all(np.isnan(sun)):
        return {}
    anti_min = float(np.nanmin(anti))
    sun_min = float(np.nanmin(sun))
    sun_max = float(np.nanmax(sun))
    run = _dark_run(anti, dark_z)
    tan_i = math.tan(math.radians(incidence_deg))
    height = run * scale_m / tan_i if tan_i > 0 else 0.0
    return {
        "anti_sun_min_z": round(anti_min, 2),
        "sun_min_z": round(sun_min, 2),
        "two_sided": round(sun_min - anti_min, 2),
        "shadow_run_px": int(run),
        "shadow_height_m": round(height, 2),
        "sun_max_z": round(sun_max, 2),
    }


def isolation(points: list[tuple[float, float]], cap: float = ISOLATION_CAP_PX) -> list[float]:
    """Distance from each point to its nearest other point, capped; ``cap`` when alone."""
    if len(points) < 2:
        return [cap] * len(points)
    pts = np.asarray(points, dtype=float)
    d, _ = cKDTree(pts).query(pts, k=2, distance_upper_bound=cap)
    out = d[:, 1]
    out = np.where(np.isfinite(out), out, cap)
    return [round(float(x), 1) for x in out]


def saturated_count(sat: np.ndarray, lab: np.ndarray, label: int, sl: tuple) -> int:
    sub = lab[sl] == label
    return int(sat[sl][sub].sum())


# ---------------------------------------------------------------- rules: features into the score

_OPS = {
    ">=": lambda v, t: v >= t,
    "<=": lambda v, t: v <= t,
    ">": lambda v, t: v > t,
    "<": lambda v, t: v < t,
    "in": lambda v, t: t[0] <= v <= t[1],  # threshold is [low, high], inclusive
}


@dataclass
class Condition:
    feature: str
    op: str
    threshold: float | list[float]

    def holds(self, extra: dict) -> bool | None:
        v = extra.get(self.feature)
        if v is None:
            return None
        return bool(_OPS[self.op](float(v), self.threshold))

    def __str__(self) -> str:
        return f"{self.feature} {self.op} {self.threshold}"


@dataclass
class Rule:
    """One physical test: every condition must hold. ``gain`` is added to the calibrated score of a
    candidate of a covered branch that passes; it is -log10 of the fraction of that branch's false alarms
    on the tuning strips that pass the same test (``false_alarm_pass_fraction``)."""

    name: str
    branches: list[str]
    conditions: list[Condition]
    gain: float
    false_alarm_pass_fraction: float | None = None
    basis: str = ""

    def passes(self, branch: str, extra: dict) -> bool | None:
        """True/False, or None when the candidate's branch is not covered or a feature is missing."""
        if branch not in self.branches:
            return None
        result = True
        for cnd in self.conditions:
            h = cnd.holds(extra)
            if h is None:
                return None
            result = result and h
        return result

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "branches": list(self.branches),
            "conditions": [{"feature": c.feature, "op": c.op, "threshold": c.threshold} for c in self.conditions],
            "false_alarm_pass_fraction": self.false_alarm_pass_fraction,
            "gain": self.gain,
            "basis": self.basis,
        }

    def __str__(self) -> str:
        return f"{self.name}: " + " and ".join(str(c) for c in self.conditions)


@dataclass
class ShapeRules:
    version: str
    rules: list[Rule] = field(default_factory=list)
    basis: str = ""

    @classmethod
    def load(cls, path: str | Path) -> ShapeRules:
        return cls.from_json(json.loads(Path(path).read_text()))

    @classmethod
    def from_json(cls, d: dict) -> ShapeRules:
        rules = [
            Rule(
                r["name"],
                list(r["branches"]),
                [Condition(c["feature"], c["op"], c["threshold"]) for c in r["conditions"]],
                float(r.get("gain") or 0.0),
                r.get("false_alarm_pass_fraction"),
                r.get("basis", ""),
            )
            for r in d["rules"]
        ]
        return cls(d["version"], rules, d.get("basis", ""))

    def to_json(self) -> dict:
        return {"version": self.version, "basis": self.basis, "rules": [r.to_json() for r in self.rules]}

    def adjust(self, branch: str, extra: dict) -> tuple[float, list[str]]:
        """Total gain for a candidate and the names of the rules it passed."""
        gain = 0.0
        passed = []
        for r in self.rules:
            if r.passes(branch, extra):
                gain += r.gain
                passed.append(r.name)
        return gain, passed


def apply_rules(cands, rules: ShapeRules):
    """Add each passed rule's gain to the candidate's score; record what passed in ``extra["shape_pass"]``.
    Works on ``landers.detect.Candidate`` objects. The order of the list is kept."""
    out = []
    for c in cands:
        gain, passed = rules.adjust(c.branch, c.extra)
        if not passed:
            out.append(c)
            continue
        extra = dict(c.extra)
        extra["shape_pass"] = passed
        extra["shape_gain"] = round(gain, 3)
        out.append(type(c)(c.row, c.col, c.score + gain, c.branch, c.grade, c.area_px, extra))
    return out


def apply_rules_json(cand: dict, rules: ShapeRules) -> dict:
    """The same adjustment on one candidate dict from a candidates file (``scripts/rescore.py``)."""
    extra = dict(cand.get("extra") or {})
    gain, passed = rules.adjust(cand["branch"], extra)
    if not passed:
        return cand
    extra["shape_pass"] = passed
    extra["shape_gain"] = round(gain, 3)
    return {**cand, "score": round(float(cand["score"]) + gain, 3), "extra": extra}

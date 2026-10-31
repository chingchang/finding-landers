"""Per-strip calibration with an honest tail, plan item 15; the protocol is docs/proposals/halfcal-v1-protocol.md.

A strip is split into a checkerboard of squares fixed on the ground. Each branch's rarity curve is fitted on one colour
and applied to the candidates of the other, so a candidate never lowers its own rarity and each colour checks the
other's curve. Above the top of a fitted curve nothing is extrapolated: the data say only that the rate is below one in
the colour's area, so those candidates get one cap, and frozen-v1's table score orders them without claiming a rate.

Scores only: no pixel is read here, no image identity is held, and the detector is unchanged.
"""

from __future__ import annotations

import math

import numpy as np

from landers.calibrate import TIE_BREAK, Calibration, fit_scores

BLOCK_M = 1000.0
ORDER_SPAN = 0.1


def colour(rows, cols, scale_m: float, shift_m: float = 0.0) -> np.ndarray:
    """0 or 1 for each position, on a checkerboard of BLOCK_M squares moved by ``shift_m`` along both axes."""
    step = BLOCK_M / float(scale_m)
    off = shift_m / float(scale_m)
    r = np.floor((np.asarray(rows, np.float64) + off) / step).astype(np.int64)
    c = np.floor((np.asarray(cols, np.float64) + off) / step).astype(np.int64)
    return ((r + c) % 2).astype(np.int8)


def colour_areas(valid: np.ndarray, step_px: int, scale_m: float, shift_m: float = 0.0) -> tuple[float, float]:
    """Valid km2 of each colour, from an overview mask taking every ``step_px``-th pixel of the strip."""
    rows, cols = np.nonzero(valid)
    k = colour((rows + 0.5) * step_px, (cols + 0.5) * step_px, scale_m, shift_m)
    km2 = (step_px * float(scale_m)) ** 2 / 1e6
    return float((k == 0).sum()) * km2, float((k == 1).sum()) * km2


def squash(x: np.ndarray) -> np.ndarray:
    """Any score into [0, ORDER_SPAN), keeping its order."""
    return ORDER_SPAN * (0.5 + np.arctan(np.asarray(x, np.float64)) / math.pi)


def cap_of(area_km2: float) -> float:
    return math.log10(float(area_km2) / 0.5)


def fit_population(branches: np.ndarray, raw: np.ndarray, area_km2: float) -> Calibration:
    """Every branch's empirical curve from these candidates over this area; nothing is left out of the knots."""
    by_branch = {str(b): raw[branches == b].tolist() for b in np.unique(branches)}
    return fit_scores(by_branch, area_km2, "halfcal", top_exclude=0)


def capped_scores(cal: Calibration, branches: np.ndarray, raw: np.ndarray, table: np.ndarray) -> np.ndarray:
    """The curve's rarity where the curve has data. Above its top, or with no curve for the branch, the cap plus the
    table's order. ``cal.area_km2`` is the area the curve was fitted on."""
    cap = cap_of(cal.area_km2)
    out = cap + squash(table)
    for b, curve in cal.branches.items():
        if not curve.scores:
            continue
        inside = (branches == b) & (raw <= curve.scores[0])
        out[inside] = -np.interp(raw[inside], curve.scores[::-1], curve.log_rates[::-1]) + TIE_BREAK * raw[inside]
    return out


def cross_fit(
    branches: np.ndarray, raw: np.ndarray, colours: np.ndarray, areas: tuple[float, float]
) -> tuple[Calibration, Calibration]:
    """The two colours' curves, element k fitted on colour k."""
    fitted = []
    for k in (0, 1):
        if areas[k] <= 0:
            raise ValueError(f"colour {k} has no valid area")
        sel = colours == k
        fitted.append(fit_population(branches[sel], raw[sel], areas[k]))
    return fitted[0], fitted[1]


def score_by_other(
    cals: tuple[Calibration, Calibration], branches: np.ndarray, raw: np.ndarray, table: np.ndarray, colours: np.ndarray
) -> np.ndarray:
    """Each candidate scored by the curve of the colour it does not sit on."""
    out = np.zeros(len(raw), np.float64)
    for k in (0, 1):
        sel = colours == k
        out[sel] = capped_scores(cals[1 - k], branches[sel], raw[sel], table[sel])
    return out


def realised_rates(
    scores: np.ndarray, branches: np.ndarray, area_km2: float, levels: tuple[float, ...], cap: float | None = None
) -> dict:
    """Candidates at or above each calibrated level per km2, per branch and over all branches. A level at or above
    ``cap`` says nothing and is left out."""
    names = [str(b) for b in np.unique(branches)]
    out = {}
    for lv in levels:
        if cap is not None and lv >= cap:
            continue
        above = scores >= lv
        out[lv] = {
            "all": float(above.sum()) / area_km2,
            "branches": {b: float((above & (branches == b)).sum()) / area_km2 for b in names},
            "n": int(above.sum()),
        }
    return out

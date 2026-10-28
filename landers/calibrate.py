"""One score scale for every branch: how rare a raw score is among false alarms on real tuning ground.

Each branch's raw score (a peak z, a mean z times a factor) lives on its own scale, so one threshold over
all branches keeps whichever branch happens to score high. The calibrated score is

    calibrated = -log10( false alarms per km2 with raw score >= s, in this branch )

measured on injection runs over tuning or spare strips (``scripts/inject.py``), where a false alarm is a
detection that matches no injected object. A calibrated score of 2 means that branch produces about one
false alarm per 100 km2 at that raw score. Above the highest false alarm seen, the curve is extrapolated
linearly in log-rate using the slope of the top of the distribution; below the lowest, the rate is flat
and a tiny raw-score term keeps the ranking.

Nothing here identifies an image: the table holds scores and areas only.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from landers.detect import Candidate

TIE_BREAK = 1e-3


@dataclass
class BranchCurve:
    scores: list[float]  # raw scores of false alarms, descending
    log_rates: list[float]  # log10(false alarms per km2 with raw score >= scores[i])
    slope: float  # d(log10 rate)/d(score) used above scores[0]; negative
    n: int

    def calibrated(self, s: float) -> float:
        if not self.scores:
            return math.nan
        if s >= self.scores[0]:
            return -(self.log_rates[0] + self.slope * (s - self.scores[0])) + TIE_BREAK * s
        if s <= self.scores[-1]:
            return -self.log_rates[-1] + TIE_BREAK * s
        # scores descending: interpolate on the reversed (ascending) arrays
        lr = float(np.interp(s, self.scores[::-1], self.log_rates[::-1]))
        return -lr + TIE_BREAK * s


@dataclass
class Calibration:
    version: str
    area_km2: float
    n_tiles: int
    sites: list[str]
    branches: dict[str, BranchCurve] = field(default_factory=dict)
    floor_log_rate: float = 0.0  # log10(0.5 / area): the rate below one false alarm in the fitted area

    def calibrated(self, branch: str, raw: float) -> float:
        curve = self.branches.get(branch)
        if curve is None or not curve.scores:
            # no false alarm of this branch was seen on the fitted ground: as rare as the floor allows
            return -self.floor_log_rate + TIE_BREAK * raw
        return curve.calibrated(raw)

    def to_json(self) -> dict:
        return {
            "version": self.version,
            "area_km2": round(self.area_km2, 4),
            "n_tiles": self.n_tiles,
            "sites": self.sites,
            "floor_log_rate": round(self.floor_log_rate, 4),
            "branches": {
                b: {
                    "scores": [round(x, 4) for x in c.scores],
                    "log_rates": [round(x, 4) for x in c.log_rates],
                    "slope": round(c.slope, 4),
                    "n": c.n,
                }
                for b, c in self.branches.items()
            },
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_json(), indent=1))

    @classmethod
    def load(cls, path: str | Path) -> Calibration:
        d = json.loads(Path(path).read_text())
        cal = cls(
            d["version"], float(d["area_km2"]), int(d["n_tiles"]), list(d["sites"]), {}, float(d["floor_log_rate"])
        )
        for b, c in d["branches"].items():
            cal.branches[b] = BranchCurve(list(c["scores"]), list(c["log_rates"]), float(c["slope"]), int(c["n"]))
        return cal


def _match(d: dict, truths_by_tile: dict, radius_px: float) -> bool:
    return any(
        math.hypot(float(d["row"]) - float(t["row"]), float(d["col"]) - float(t["col"])) <= radius_px
        for t in truths_by_tile.get(d["tile"], [])
    )


MAX_KNOTS = 200


def fit(runs: list[dict], version: str, min_slope: float = 0.15) -> Calibration:
    """Fit from injection run outputs that carry raw ``detections`` and ``truths`` (scripts/inject.py).
    ``min_slope`` bounds how slowly the extrapolated rate may fall per unit of raw score. Runs that were
    themselves scored with a calibration are refused: a calibration is fitted from raw scores only."""
    area = 0.0
    n_tiles = 0
    sites: set[str] = set()
    false_by_branch: dict[str, list[float]] = {}
    for run in runs:
        if run.get("detector", {}).get("calibration"):
            raise ValueError("run was scored with a calibration; fit from raw scores only")
        area += float(run["area_km2"])
        n_tiles += int(run["n_tiles"])
        sites.update(run.get("sites", []))
        radius = float(run["match_radius_px"])
        tb: dict = {}
        for t in run["truths"]:
            tb.setdefault(t["tile"], []).append(t)
        for d in run["detections"]:
            if not _match(d, tb, radius):
                false_by_branch.setdefault(d["branch"], []).append(float(d["score"]))
    if area <= 0:
        raise ValueError("no area in the runs")
    cal = Calibration(version, area, n_tiles, sorted(sites), {}, math.log10(0.5 / area))
    for b, scores in false_by_branch.items():
        s = np.array(sorted(scores, reverse=True))
        counts = np.arange(1, len(s) + 1)
        # collapse ties to the last index of each distinct score (rate with raw >= s)
        uniq, last = np.unique(s[::-1], return_index=True)
        uniq = uniq[::-1]
        idx = len(s) - 1 - last[::-1]
        log_rates = np.log10(counts[idx] / area)
        if len(uniq) > MAX_KNOTS:  # keep the file small; the top of the curve is what matters and is kept exactly
            keep = np.unique(
                np.concatenate([np.arange(0, 20), np.linspace(0, len(uniq) - 1, MAX_KNOTS - 20).round()])
            ).astype(int)
            uniq, log_rates = uniq[keep], log_rates[keep]
        k = max(3, len(uniq) // 10)
        if len(uniq) >= 3:
            top_s, top_lr = uniq[:k], log_rates[:k]
            slope = float(np.polyfit(top_s, top_lr, 1)[0]) if len(top_s) >= 2 and np.ptp(top_s) > 0 else -min_slope
        else:
            slope = -min_slope
        slope = min(slope, -min_slope)
        cal.branches[b] = BranchCurve(uniq.tolist(), log_rates.tolist(), slope, len(s))
    return cal


def apply(cands: list[Candidate], cal: Calibration) -> list[Candidate]:
    """Replace each candidate's score with its calibrated score, keeping the raw score in ``extra``."""
    out = []
    for c in cands:
        extra = dict(c.extra)
        extra["raw_score"] = round(c.score, 3)
        out.append(Candidate(c.row, c.col, cal.calibrated(c.branch, c.score), c.branch, c.grade, c.area_px, extra))
    return out

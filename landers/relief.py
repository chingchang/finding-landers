"""The two-sided test for dark candidates, docs/plan.md item 16; the protocol is docs/proposals/darkrelief-v1-protocol.md.

Works on arrays, one per feature, NaN where a candidate has no such feature. A rule is one branch's fitted threshold, its
measured pass fraction and its gain; nothing here looks at truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

BRANCHES = ("dark", "dark_compact")
NOT_DARK_Z = -2.0  # DetectorConfig.band_dark_z
HEIGHT_M = (0.5, 3.0)  # DetectorConfig.shadow_heights_m
MAX_WIDTH_M = 10.0  # the top of DetectorConfig.bright_size_m
LOWEST_T = 0.01  # features are rounded to 0.01, so this is "above 0"
P_TARGET = 0.001


@dataclass
class Rule:
    threshold: float
    fraction: float
    gain: float
    n: int
    passed: int

    def to_json(self) -> dict:
        return {
            "threshold": self.threshold,
            "fraction": round(self.fraction, 6),
            "gain": round(self.gain, 3),
            "n": self.n,
            "passed": self.passed,
        }


def fixed_conditions(f: dict[str, np.ndarray], flipped: bool = False) -> np.ndarray:
    """Conditions 2 to 4 of the test. ``flipped`` is the placebo: the sun on the wrong side."""
    side = f["relief_anti_min_z"] if flipped else f["relief_sun_min_z"]
    with np.errstate(invalid="ignore"):
        return (
            (side >= NOT_DARK_Z)
            & (f["relief_height_m"] >= HEIGHT_M[0])
            & (f["relief_height_m"] <= HEIGHT_M[1])
            & (f["relief_width_m"] <= MAX_WIDTH_M)
        )


def test_value(f: dict[str, np.ndarray], flipped: bool = False) -> np.ndarray:
    """The value compared with T, NaN where a fixed condition fails or a feature is missing."""
    v = -f["relief_dipole"] if flipped else f["relief_dipole"]
    return np.where(fixed_conditions(f, flipped), v, np.nan)


def recorded_value(f: dict[str, np.ndarray]) -> np.ndarray:
    """The comparison on the recorded features: two_sided, where the recorded shadow height is in range."""
    with np.errstate(invalid="ignore"):
        ok = (f["shadow_height_m"] >= HEIGHT_M[0]) & (f["shadow_height_m"] <= HEIGHT_M[1])
    return np.where(ok, f["two_sided"], np.nan)


def fit_rule(values: np.ndarray, p: float = P_TARGET) -> Rule | None:
    """T at which the fraction of all ``values`` at or above it comes to ``p``, never under LOWEST_T. NaN counts in the
    population and never passes. None when nothing passes at all: no rule, no gain."""
    n = len(values)
    if n == 0:
        return None
    ok = np.sort(values[np.isfinite(values) & (values >= LOWEST_T)])[::-1]
    if len(ok) == 0:
        return None
    k = max(1, int(p * n))
    t = float(ok[min(k, len(ok)) - 1])
    passed = int((ok >= t).sum())
    fraction = passed / n
    return Rule(t, fraction, -math.log10(fraction), n, passed)


def gains(values: np.ndarray, rule: Rule | None) -> np.ndarray:
    if rule is None:
        return np.zeros(len(values))
    with np.errstate(invalid="ignore"):
        return np.where(values >= rule.threshold, rule.gain, 0.0)

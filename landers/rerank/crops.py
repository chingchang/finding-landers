"""What an embedding sees: a native crop turned to a common sun, on two windows fixed on the ground.

No id, date or position reaches this code; the only things taken from a label are the sun's azimuth and the map scale.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from landers.strip import valid_mask
from landers.transplant import rotation_deg

CROP_PX = 320
WINDOWS_M = (16.0, 56.0)
CLIP = 6.0
MAD_FLOOR = 0.02  # of the median, so a noise-only crop is not stretched into texture


def cut(data: np.ndarray, row0: int, col0: int, row: float, col: float, size: int = CROP_PX) -> np.ndarray:
    """``size`` px square of a window, centred as ``landers.search.export.cut_square``. Outside the window is 0."""
    r0, c0 = int(round(row)) - size // 2 - row0, int(round(col)) - size // 2 - col0
    out = np.zeros((size, size), data.dtype)
    rs, cs = max(r0, 0), max(c0, 0)
    re, ce = min(r0 + size, data.shape[0]), min(c0 + size, data.shape[1])
    if re > rs and ce > cs:
        out[rs - r0 : re - r0, cs - c0 : ce - c0] = data[rs:re, cs:ce]
    return out


def canonical(raw: np.ndarray, sun_azimuth_deg: float) -> np.ndarray:
    """No-data pixels filled with the crop's median, then turned so the sun comes from azimuth 0 in every crop."""
    valid = valid_mask(raw)
    x = raw.astype(np.float32)
    fill = float(np.median(x[valid])) if valid.any() else 1.0
    x[raw == 0] = fill
    return ndimage.rotate(x, rotation_deg(sun_azimuth_deg, 0.0), reshape=False, order=1, mode="nearest")


def window(x: np.ndarray, metres: float, scale_m: float) -> np.ndarray:
    """The centre of a canonical crop, ``metres`` across on the ground, in [0, 1] about its median."""
    n = int(round(metres / scale_m))
    i = (x.shape[0] - n) // 2
    w = x[i : i + n, i : i + n]
    med = float(np.median(w))
    mad = 1.4826 * float(np.median(np.abs(w - med)))
    z = (w - med) / max(mad, MAD_FLOOR * max(med, 1.0))
    return (np.clip(z, -CLIP, CLIP) + CLIP) / (2 * CLIP)


def views(raw: np.ndarray, sun_azimuth_deg: float, scale_m: float) -> list[np.ndarray]:
    x = canonical(raw, sun_azimuth_deg)
    return [window(x, m, scale_m) for m in WINDOWS_M]

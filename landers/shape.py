"""Shape features of small-object candidates (bright, shadow, dark_compact).

Recorded on every candidate, not yet used in the score: the injector draws discs and ellipses, so a score
tuned to these on injected objects would learn the injector. They are measured on phase 1 injection as
information (``scripts/inject.py --features``) and will be judged against the real answer key.

- ``circularity``: 4 pi area / perimeter^2 (1 for a disc; rocks and slopes are lower).
- ``fill``: area over bounding-box area.
- ``elongation``: 1 - sqrt(minor/major) of the second moments (0 for a disc).
- ``edge_sharpness``: mean |gradient of z| on the boundary over the peak |z| (crisp edges score higher).
- ``tile_rank``: how many components of the same sign in the tile have a higher peak (0 = the strongest).
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

FEATURES = ("circularity", "fill", "elongation", "edge_sharpness", "tile_rank")


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

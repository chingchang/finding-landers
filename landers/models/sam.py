"""SAM 3.1: box prompts from the detector's blobs, and measurements from the masks it returns.

SAM supplies measurements, never a verdict. A mask gives the size and shape tests an outline to measure
instead of the detector's thresholded blob. No candidate is promoted because SAM found a mask; a test can
only pass, fail, come back unsure, or not run.

The size limits are the detector's own per-branch ranges (``DetectorConfig``), so SAM re-measures the
same physical claim the branch made. The compactness limit is provisional and proposed in
``docs/proposals/sam-tests-v0.md``; a person adopts it into ``controls/thresholds.json``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from landers.detect import DetectorConfig
from landers.models.backend import Box, SamObject, SamRequest, SamResult

MAX_OBJECTS = 16
PASS, FAIL, UNSURE, NOT_RUN = "pass", "fail", "unsure", "not run"


def box_token(b: Box, w: int, h: int) -> str:
    return f"<|box;x1={b.x1};y1={b.y1};x2={b.x2};y2={b.y2};w={w};h={h}|>"


def build_object_prompt(width: int, height: int, boxes: list[Box]) -> str:
    """The prompt string for box prompts (docs/models.md): ``<0f>`` then ``<id><box token>`` per object,
    comma separated, at most 16 objects, the image size repeated on every token."""
    if not boxes:
        raise ValueError("no boxes")
    if len(boxes) > MAX_OBJECTS:
        raise ValueError(f"at most {MAX_OBJECTS} objects per request, got {len(boxes)}")
    for b in boxes:
        if not (0 <= b.x1 <= b.x2 < width and 0 <= b.y1 <= b.y2 < height):
            raise ValueError(f"box {b} outside a {width}x{height} image")
    return "<0f>" + ",".join(f"{i + 1}{box_token(b, width, height)}" for i, b in enumerate(boxes))


def box_for_blob(row: float, col: float, area_px: float, size: int, pad: float = 1.0, min_half: int = 3) -> Box:
    """A box around a blob at (row, col) in a ``size`` px square crop whose centre is the blob: the blob's
    equivalent radius, padded by ``pad`` times itself, clipped to the crop."""
    r = math.sqrt(max(area_px, 1.0) / math.pi)
    half = max(min_half, int(math.ceil(r * (1.0 + pad))))
    cy = cx = size // 2
    return Box(max(0, cx - half), max(0, cy - half), min(size - 1, cx + half), min(size - 1, cy + half))


def sam_request(png: bytes, size: int, boxes: list[Box]) -> SamRequest:
    return SamRequest(png, size, size, boxes)


@dataclass
class SamLimits:
    """Provisional limits for the mask tests; see docs/proposals/sam-tests-v0.md."""

    max_elongation: float = 0.6  # 1 - sqrt(minor/major): 0.6 is an axis ratio of about 6 to 1
    min_confidence: float = 0.3
    min_edge_contrast: float = 1.0  # mean inside minus ring, over the ring's std


def mask_measurements(mask: np.ndarray, box: Box, scale_m: float, image: np.ndarray | None = None) -> dict:
    """Area, axes, shape and edge contrast of the mask's largest connected piece inside the box."""
    m = np.asarray(mask, bool)
    if not m.any():
        return {"area_px": 0}
    lab, n = ndimage.label(m)
    if n > 1:
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        m = lab == (int(np.argmax(sizes)) + 1)
    rr, cc = np.nonzero(m)
    area = int(len(rr))
    out: dict = {
        "area_px": area,
        "area_m2": round(area * scale_m * scale_m, 2),
        "equiv_diameter_m": round(2.0 * math.sqrt(area / math.pi) * scale_m, 2),
        "centroid_row": round(float(rr.mean()), 1),
        "centroid_col": round(float(cc.mean()), 1),
        "pieces": int(n),
    }
    if area >= 3:
        cov = np.cov(np.vstack([rr, cc]).astype(float))
        ev = np.sort(np.linalg.eigvalsh(cov))
        major = 4.0 * math.sqrt(max(ev[1], 0.0))  # full length at 2 sigma
        minor = 4.0 * math.sqrt(max(ev[0], 0.0))
        out["major_m"] = round(max(major, 1.0) * scale_m, 2)
        out["minor_m"] = round(max(minor, 1.0) * scale_m, 2)
        out["elongation"] = round(1.0 - math.sqrt(max(ev[0], 0.0) / ev[1]) if ev[1] > 0 else 0.0, 3)
    else:
        out["major_m"] = out["minor_m"] = round(math.sqrt(area) * scale_m, 2)
        out["elongation"] = 0.0
    bh, bw = rr.max() - rr.min() + 1, cc.max() - cc.min() + 1
    out["fill"] = round(area / float(bh * bw), 3)
    eroded = ndimage.binary_erosion(m)
    perim = int((m & ~eroded).sum())
    out["circularity"] = round(min(1.0, 4 * math.pi * area / perim**2), 3) if perim else 0.0
    out["touches_box_edge"] = bool(rr.min() <= box.y1 or rr.max() >= box.y2 or cc.min() <= box.x1 or cc.max() >= box.x2)
    if image is not None:
        img = np.asarray(image, float)
        ring = ndimage.binary_dilation(m, iterations=3) & ~ndimage.binary_dilation(m, iterations=1)
        if ring.any() and img[ring].std() > 0:
            out["edge_contrast"] = round(float((img[m].mean() - img[ring].mean()) / img[ring].std()), 2)
    return out


def size_shape_tests(meas: dict, branch: str, cfg: DetectorConfig, limits: SamLimits, confidence: float) -> dict:
    """The mask-based size and shape tests for one candidate, each ``{"outcome", "value", "limit"}``."""
    ranges = {
        "bright": cfg.bright_size_m,
        "shadow": cfg.bright_size_m,
        "sheet": cfg.sheet_size_m,
        "dark_compact": cfg.dark_compact_size_m,
        "dark": cfg.dark_size_m,
    }
    size_m = ranges.get(branch)
    if not meas.get("area_px") or size_m is None:
        return {
            "sam_size": {"outcome": NOT_RUN, "value": None, "limit": list(size_m) if size_m else None},
            "sam_shape": {"outcome": NOT_RUN, "value": None, "limit": limits.max_elongation},
        }
    weak = confidence < limits.min_confidence or meas.get("touches_box_edge", False)
    d = meas["equiv_diameter_m"]
    size_ok = size_m[0] <= d <= size_m[1]
    tests = {
        "sam_size": {
            "outcome": UNSURE if weak else (PASS if size_ok else FAIL),
            "value": d,
            "limit": list(size_m),
            "unit": "m, equivalent diameter",
        }
    }
    e = meas["elongation"]
    if branch in ("bright", "shadow", "dark_compact"):
        tests["sam_shape"] = {
            "outcome": UNSURE if weak else (PASS if e <= limits.max_elongation else FAIL),
            "value": e,
            "limit": limits.max_elongation,
            "unit": "elongation, 1 - sqrt(minor/major)",
        }
    else:
        tests["sam_shape"] = {"outcome": NOT_RUN, "value": e, "limit": None, "unit": "no shape claim for this branch"}
    if "edge_contrast" in meas:
        tests["sam_edge"] = {
            "outcome": UNSURE if weak else (PASS if abs(meas["edge_contrast"]) >= limits.min_edge_contrast else FAIL),
            "value": meas["edge_contrast"],
            "limit": limits.min_edge_contrast,
            "unit": "sigma of the surrounding ring",
        }
    return tests


def measure_result(result: SamResult, boxes: list[Box], scale_m: float, image: np.ndarray | None = None) -> list[dict]:
    """One measurement record per requested box, matched by object id (1-based, in box order)."""
    by_id: dict[int, SamObject] = {o.object_id: o for o in result.objects}
    out = []
    for i, box in enumerate(boxes):
        obj = by_id.get(i + 1)
        if obj is None:
            out.append({"found": False, "confidence": 0.0, "measurements": {"area_px": 0}})
            continue
        inside = obj.mask.copy()
        inside[: box.y1, :] = False
        inside[box.y2 + 1 :, :] = False
        inside[:, : box.x1] = False
        inside[:, box.x2 + 1 :] = False
        out.append(
            {
                "found": bool(inside.any()),
                "confidence": round(obj.confidence, 3),
                "measurements": mask_measurements(inside, box, scale_m, image),
            }
        )
    return out

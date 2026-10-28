"""Contact sheets and suggestions for filling the answer key.

For each tuning piece with a refined position (``controls/sites.json`` ``pieces_refined``), the top N
candidates of a detector run within a radius of that position, as a sheet of full-resolution thumbnails
and as a JSON/Markdown list of PDS line and sample. A person reads the sheet, picks the piece, and copies
its line and sample into ``controls/tuning.json``. Nothing here writes to ``controls/``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from landers.strip import Strip

CREDIT = "NASA/JPL/University of Arizona"
BLOCK = 2048


@dataclass
class Pick:
    rank: int
    row: float
    col: float
    score: float
    branch: str
    distance_m: float
    area_px: int
    extra: dict


def anchor_for(site: dict, piece: str) -> tuple[float, float, float, str]:
    """(lat, lon, precision_m, how) for a piece: its refined position, else the site's published one."""
    for p in site.get("pieces_refined", []):
        if p["piece"] == piece and p.get("lat") is not None and p.get("lon_e") is not None:
            return float(p["lat"]), float(p["lon_e"]), float(p.get("precision_m") or 1000), "refined"
    return float(site["lat"]), float(site["lon_e"]), 1000.0, "site published position (piece has none)"


def select(strip_entry: dict, scale_m: float, row0: float, col0: float, radius_m: float, top_n: int) -> list[Pick]:
    r_px = radius_m / scale_m
    picks = []
    for c in strip_entry.get("candidates", []):
        d = math.hypot(float(c["row"]) - row0, float(c["col"]) - col0)
        if d <= r_px:
            picks.append((float(c["score"]), c, d))
    picks.sort(key=lambda t: -t[0])
    return [
        Pick(
            i + 1,
            float(c["row"]),
            float(c["col"]),
            s,
            c["branch"],
            d * scale_m,
            int(c.get("area_px", 0)),
            c.get("extra", {}),
        )
        for i, (s, c, d) in enumerate(picks[:top_n])
    ]


def _stretch(a: np.ndarray, valid: np.ndarray) -> np.ndarray:
    if valid.sum() < 50:
        return np.zeros(a.shape, np.uint8)
    lo, hi = np.percentile(a[valid], [0.5, 99.5])
    x = np.clip((a.astype(np.float32) - lo) / max(hi - lo, 1.0), 0, 1)
    x[~valid] = 0
    return (x * 255).astype(np.uint8)


def thumbnails(strip: Strip, picks: list[Pick], size: int) -> list[np.ndarray]:
    """Full-resolution ``size`` px crops centred on each pick, reading each 2048 px block once."""
    half = size // 2
    blocks: dict[tuple[int, int], object] = {}
    out = []
    for p in picks:
        r, c = int(round(p.row)), int(round(p.col))
        key = ((r - half) // BLOCK, (c - half) // BLOCK)
        # a crop may straddle blocks; read a block-and-a-bit window keyed by the crop's top-left block
        if key not in blocks:
            r0, c0 = key[0] * BLOCK, key[1] * BLOCK
            blocks[key] = strip.read(max(r0, 0), r0 + BLOCK + size, max(c0, 0), c0 + BLOCK + size)
        w = blocks[key]
        rr, cc = r - half - w.row0, c - half - w.col0
        crop = np.zeros((size, size), np.uint16)
        v = np.zeros((size, size), bool)
        sr0, sc0 = max(rr, 0), max(cc, 0)
        sr1, sc1 = min(rr + size, w.data.shape[0]), min(cc + size, w.data.shape[1])
        if sr1 > sr0 and sc1 > sc0:
            crop[sr0 - rr : sr1 - rr, sc0 - cc : sc1 - cc] = w.data[sr0:sr1, sc0:sc1]
            v[sr0 - rr : sr1 - rr, sc0 - cc : sc1 - cc] = w.valid[sr0:sr1, sc0:sc1]
        out.append(_stretch(crop, v))
    return out


def render_sheet(
    strip: Strip, picks: list[Pick], thumbs: list[np.ndarray], title: str, out: Path, cols: int = 10, zoom: int = 2
) -> Path:
    if not picks:
        return out
    size = thumbs[0].shape[0] * zoom
    cell_h = size + 30
    rows = -(-len(picks) // cols)
    sheet = Image.new("RGB", (cols * size, rows * cell_h + 40), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for i, (p, t) in enumerate(zip(picks, thumbs, strict=True)):
        x, y = (i % cols) * size, (i // cols) * cell_h
        im = Image.fromarray(t).resize((size, size), Image.NEAREST).convert("RGB")
        sheet.paste(im, (x, y))
        cx, cy = x + size // 2, y + size // 2
        d.line([(cx - 8, cy), (cx - 3, cy)], fill=(0, 255, 255))
        d.line([(cx + 3, cy), (cx + 8, cy)], fill=(0, 255, 255))
        d.line([(cx, cy - 8), (cx, cy - 3)], fill=(0, 255, 255))
        d.line([(cx, cy + 3), (cx, cy + 8)], fill=(0, 255, 255))
        d.rectangle([x, y, x + size - 1, y + size - 1], outline=(70, 70, 70))
        d.text((x + 3, y + size + 2), f"#{p.rank} {p.branch} {p.score:.2f} {p.distance_m:.0f} m", fill=(255, 220, 0))
        d.text((x + 3, y + size + 15), f"l{p.row + 1:.0f} s{p.col + 1:.0f}", fill=(220, 220, 220))
    d.text((4, rows * cell_h + 4), title, fill=(255, 255, 255))
    d.text(
        (4, rows * cell_h + 20),
        f"Credit: {CREDIT}. Each tile {thumbs[0].shape[0] * strip.label.scale_m:.0f} m across at full resolution; "
        "cross marks the candidate.",
        fill=(200, 200, 200),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out

"""Contact sheets and suggestions for filling the answer key.

For each tuning piece with a refined position (``controls/sites.json`` ``pieces_refined``), the top N
candidates of a detector run within a radius of that position, as a sheet of full-resolution thumbnails,
an overview map with the same numbers drawn on it, and a JSON/Markdown list of PDS line and sample. Each
pick is also tied to the numbered 1.5 km grid tile that ``scripts/cut_grids.py`` writes for the same
piece, so a person can go from a thumbnail to the full-resolution tile around it. A person reads the
sheet, picks the piece, and copies its line and sample into ``controls/tuning.json``. Nothing here writes
to ``controls/``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from landers.strip import Strip, Window

CREDIT = "NASA/JPL/University of Arizona"
BLOCK = 2048
MAP_STEP = 8  # image pixels per map pixel: 2 m at 25 cm/px, so a 3 km map is 1500 px


@dataclass(frozen=True)
class GridLayout:
    """The numbered tile grid of ``scripts/cut_grids.py`` and ``crop_site.py --grid`` around one position:
    ``n`` x ``n`` tiles of ``tile`` px, row-major from 1, top-left image pixel (row0, col0)."""

    row0: int
    col0: int
    n: int
    tile: int

    @property
    def size(self) -> int:
        return self.n * self.tile

    def tile_of(self, row: float, col: float) -> int | None:
        """Tile number holding image pixel (row, col), or None outside the grid."""
        i, j = int(math.floor(row - self.row0)) // self.tile, int(math.floor(col - self.col0)) // self.tile
        if 0 <= i < self.n and 0 <= j < self.n:
            return i * self.n + j + 1
        return None


def grid_layout(row: float, col: float, scale_m: float, span_m: float, tile: int) -> GridLayout:
    """Where the grid tiles fall for a grid of ``span_m`` metres centred on (row, col): ``n * tile`` px
    with the centre at ``size // 2``, the top-left corner clipped to the image origin like ``Strip.read``.
    The grid renderer reads its window from this layout, so the numbering here is the numbering on the
    tiles."""
    n = -(-int(round(span_m / scale_m)) // tile)
    size = n * tile
    return GridLayout(max(int(round(row)) - size // 2, 0), max(int(round(col)) - size // 2, 0), n, tile)


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


def count_within(strip_entry: dict, scale_m: float, row0: float, col0: float, radius_m: float) -> int:
    r_px = radius_m / scale_m
    return sum(
        1
        for c in strip_entry.get("candidates", [])
        if math.hypot(float(c["row"]) - row0, float(c["col"]) - col0) <= r_px
    )


def summarise(picks: list[Pick], grid: GridLayout | None) -> dict:
    """What the key-filler wants to know before opening the sheet: branch mix, score range, how many picks
    the grid tiles cover, and how close the nearest pick is to the anchor."""
    if not picks:
        return {"n": 0}
    branches: dict[str, int] = {}
    for p in picks:
        branches[p.branch] = branches.get(p.branch, 0) + 1
    return {
        "n": len(picks),
        "branches": dict(sorted(branches.items(), key=lambda kv: -kv[1])),
        "score_top": round(picks[0].score, 3),
        "score_last": round(picks[-1].score, 3),
        "in_grid": sum(1 for p in picks if grid is not None and grid.tile_of(p.row, p.col) is not None),
        "nearest_m": round(min(p.distance_m for p in picks)),
        "nearest_rank": min(picks, key=lambda p: p.distance_m).rank,
    }


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


def draw_map(
    w: Window,
    scale_m: float,
    row0: float,
    col0: float,
    radius_m: float,
    precision_m: float,
    picks: list[Pick],
    grid: GridLayout | None,
    title: str,
) -> Image.Image:
    """The search area as one image: every pick as a numbered circle (the number is its sheet rank), the
    anchor as a cross with its precision circle, the search radius, and the numbered grid tiles when a
    grid is given. ``w`` is a reduced window (``Window.step`` image px per data px)."""
    img8 = _stretch(w.data, w.valid)
    im = Image.fromarray(img8).convert("RGB")
    d = ImageDraw.Draw(im)
    s = w.step
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:  # Pillow before 10.1 has no sized default font
        font = ImageFont.load_default()

    def xy(r: float, c: float) -> tuple[float, float]:
        return (c - w.col0) / s, (r - w.row0) / s

    if grid is not None:
        t = grid.tile / s
        for i in range(grid.n):
            for j in range(grid.n):
                x, y = xy(grid.row0 + i * grid.tile, grid.col0 + j * grid.tile)
                d.rectangle([x, y, x + t - 1, y + t - 1], outline=(90, 70, 0))
                d.text((x + 2, y + 1), str(i * grid.n + j + 1), fill=(170, 130, 0))
    ax, ay = xy(row0, col0)
    for rad_m, colour in ((radius_m, (0, 150, 255)), (precision_m, (0, 255, 255))):
        rp = rad_m / scale_m / s
        d.ellipse([ax - rp, ay - rp, ax + rp, ay + rp], outline=colour)
    d.line([(ax - 12, ay), (ax + 12, ay)], fill=(0, 255, 255))
    d.line([(ax, ay - 12), (ax, ay + 12)], fill=(0, 255, 255))
    for p in picks:
        x, y = xy(p.row, p.col)
        d.ellipse([x - 5, y - 5, x + 5, y + 5], outline=(255, 220, 0))
        d.text((x + 6, y - 8), str(p.rank), fill=(255, 255, 0), font=font)
    footer = Image.new("RGB", (im.width, 36), (0, 0, 0))
    fd = ImageDraw.Draw(footer)
    fd.text((4, 2), title, fill=(255, 255, 255))
    fd.text(
        (4, 18),
        f"Credit: {CREDIT}. {scale_m * s:.2f} m/px shown. Yellow: pick and its sheet rank; cyan: anchor and "
        f"its precision ({precision_m:.0f} m); blue: search radius ({radius_m:.0f} m); brown: grid tiles.",
        fill=(200, 200, 200),
    )
    canvas = Image.new("RGB", (im.width, im.height + 36))
    canvas.paste(im, (0, 0))
    canvas.paste(footer, (0, im.height))
    return canvas


def render_map(
    strip: Strip,
    row0: float,
    col0: float,
    radius_m: float,
    precision_m: float,
    picks: list[Pick],
    grid: GridLayout | None,
    title: str,
    out: Path,
    step: int = MAP_STEP,
) -> Path:
    r_px = int(math.ceil(radius_m / strip.label.scale_m))
    r, c = int(round(row0)), int(round(col0))
    w = strip.read_reduced(r - r_px, r + r_px, c - r_px, c + r_px, step)
    im = draw_map(w, strip.label.scale_m, row0, col0, radius_m, precision_m, picks, grid, title)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out

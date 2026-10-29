"""Contact sheets and suggestions for filling the answer key.

For each tuning piece with a refined position (``controls/sites.json`` ``pieces_refined``), the top N
candidates of a detector run within a radius of an anchor (the refined position, or the strip's own centre
where the published position is too rough), as sheets of full-resolution thumbnails, an overview map with
the same numbers drawn on it, and a JSON/Markdown list of PDS line and sample. Each pick is also tied to
the numbered 1.5 km grid tile that ``scripts/cut_grids.py`` writes for the same piece, so a person can go
from a thumbnail to the full-resolution tile around it.

Two rankings sit side by side. The first is the detector's calibrated score. The second is a two-sided
shadow test from the label's sun azimuth, measured on the pixels around every candidate in the area: a
bright compact blob with dark pixels on the anti-sun side and no dark pixels on the sun side. Raised
objects (a lander, a rock) cast a shadow away from the sun; a trough, a polygon edge or a crater wall is
bright on the far wall and dark on the near one, so its dark side faces the sun and it ranks low.

All thumbnails of one piece and strip share one brightness stretch (one pair of percentiles over every
thumbnail's valid pixels), so a bright object stands out against the others instead of every thumbnail
being stretched to its own extremes. A person reads the sheets, picks the piece, and copies its line and
sample into ``controls/tuning.json``. Nothing here writes to ``controls/``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from landers import geo
from landers.label import StripLabel
from landers.strip import Strip, Window

CREDIT = "NASA/JPL/University of Arizona"
BLOCK = 2048
MAP_STEP = 8  # image pixels per map pixel: 2 m at 25 cm/px, so a 3 km map is 1500 px
STRETCH_PERCENTILES = (0.5, 99.5)
SHADOW_MIN_INCIDENCE_DEG = 35.0  # below this shadows are too short to measure; same floor as the detector
SHADOW_MAX_HEIGHT_M = 3.0  # the probe reaches as far as a 3 m object's shadow
OBJECT_RADIUS_PX = (2.0, 16.0)  # the object disc is the candidate's own area, clamped to this


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


@dataclass(frozen=True)
class ShadowTest:
    """The two-sided shadow test of one candidate, in local z units (against an annulus of ground around
    it): the object disc, the darkest stretch of the probe on the anti-sun (shadow) side, the darkest
    stretch of the mirror probe on the sun side, and the score ``min(z_centre, -z_anti) + min(0, z_sun)``:
    bright and shadowed on the right side counts, dark on the sun side costs."""

    z_centre: float
    z_anti: float
    z_sun: float

    @property
    def score(self) -> float:
        return min(self.z_centre, -self.z_anti) + min(0.0, self.z_sun)

    def to_json(self) -> dict:
        return {
            "z_centre": round(self.z_centre, 2),
            "z_anti": round(self.z_anti, 2),
            "z_sun": round(self.z_sun, 2),
            "score": round(self.score, 2),
        }


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
    shadow: ShadowTest | None = None
    shadow_rank: int | None = None  # rank by shadow score among every candidate in the area


def anchor_for(site: dict, piece: str) -> tuple[float, float, float, str]:
    """(lat, lon, precision_m, how) for a piece: its refined position, else the site's published one."""
    for p in site.get("pieces_refined", []):
        if p["piece"] == piece and p.get("lat") is not None and p.get("lon_e") is not None:
            return float(p["lat"]), float(p["lon_e"]), float(p.get("precision_m") or 1000), "refined"
    return float(site["lat"]), float(site["lon_e"]), 1000.0, "site published position (piece has none)"


def strip_centre(strip: Strip) -> tuple[float, float]:
    """(row, col) of the centre of the strip's valid footprint, from the overview mask. The anchor for
    sites whose published position is rougher than the strip's own pointing."""
    ov = strip.overview
    rr, cc = np.nonzero(ov.valid)
    s = strip.overview_step
    return float(rr.mean() * s + s / 2 - 0.5), float(cc.mean() * s + s / 2 - 0.5)


def within(strip_entry: dict, scale_m: float, row0: float, col0: float, radius_m: float) -> list[tuple[int, float]]:
    """(index into the strip's candidate list, distance in metres) of every candidate within the radius."""
    r_px = radius_m / scale_m
    out = []
    for i, c in enumerate(strip_entry.get("candidates", [])):
        d = math.hypot(float(c["row"]) - row0, float(c["col"]) - col0)
        if d <= r_px:
            out.append((i, d * scale_m))
    return out


def _pick(rank: int, c: dict, dist_m: float, shadow: ShadowTest | None, shadow_rank: int | None) -> Pick:
    return Pick(
        rank,
        float(c["row"]),
        float(c["col"]),
        float(c["score"]),
        c["branch"],
        dist_m,
        int(c.get("area_px", 0)),
        c.get("extra", {}),
        shadow,
        shadow_rank,
    )


def rank_picks(
    strip_entry: dict,
    inside: list[tuple[int, float]],
    top_n: int,
    shadows: dict[int, ShadowTest | None] | None = None,
) -> tuple[list[Pick], list[Pick]]:
    """Two top-``top_n`` lists over the candidates ``inside`` the area: by detector score, and by the
    shadow test's score (candidates without a shadow test, at the image edge, rank last). Every pick
    carries both ranks, so the two sheets can refer to each other."""
    cands = strip_entry.get("candidates", [])
    by_score = sorted(inside, key=lambda t: -float(cands[t[0]]["score"]))
    score_rank = {i: k + 1 for k, (i, _) in enumerate(by_score)}
    shadow_rank: dict[int, int] = {}
    by_shadow: list[tuple[int, float]] = []
    if shadows:
        tested = [(i, d) for i, d in inside if shadows.get(i) is not None]
        by_shadow = sorted(tested, key=lambda t: -shadows[t[0]].score)
        shadow_rank = {i: k + 1 for k, (i, _) in enumerate(by_shadow)}

    def sh(i):
        return shadows.get(i) if shadows else None

    picks = [_pick(score_rank[i], cands[i], d, sh(i), shadow_rank.get(i)) for i, d in by_score[:top_n]]
    shadow_picks = [_pick(score_rank[i], cands[i], d, sh(i), shadow_rank[i]) for i, d in by_shadow[:top_n]]
    return picks, shadow_picks


def select(strip_entry: dict, scale_m: float, row0: float, col0: float, radius_m: float, top_n: int) -> list[Pick]:
    """Top ``top_n`` by detector score within the radius (the first ranking alone)."""
    return rank_picks(strip_entry, within(strip_entry, scale_m, row0, col0, radius_m), top_n)[0]


def count_within(strip_entry: dict, scale_m: float, row0: float, col0: float, radius_m: float) -> int:
    return len(within(strip_entry, scale_m, row0, col0, radius_m))


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


# --- the two-sided shadow test -----------------------------------------------------------------------


def object_radius_px(area_px: int) -> float:
    r = math.sqrt(max(area_px, 1) / math.pi)
    return min(max(r, OBJECT_RADIUS_PX[0]), OBJECT_RADIUS_PX[1])


def shadow_probe_px(lbl: StripLabel) -> float | None:
    """How far beyond the object the shadow probe reaches, or None when the sun is too high to test."""
    if lbl.incidence_deg < SHADOW_MIN_INCIDENCE_DEG:
        return None
    return geo.shadow_length_px(lbl, SHADOW_MAX_HEIGHT_M)


@lru_cache(maxsize=8)
def _probe_geometry(h: int, w: int, cy: float, cx: float, drow: float, dcol: float):
    """Distance along the shadow line, across it, and from the centre, for every pixel of an h x w crop;
    the same for every candidate of a strip, so computed once."""
    yy, xx = np.mgrid[:h, :w]
    dy, dx = yy - cy, xx - cx
    return dy * drow + dx * dcol, np.abs(dy * dcol - dx * drow), np.hypot(dy, dx)


def _side_profile_min(x, v, along, across, r_obj: float, lmax: float, w: float, sign: int) -> float | None:
    """Darkest 3 px stretch of the probe on one side: pixels within ``w`` of the shadow line, from the
    object's edge out to ``lmax`` beyond it, averaged per 1 px step along the line, smoothed over three
    steps, minimum taken. The same operation on both sides, so noise biases them alike."""
    a = sign * along
    m = v & (across <= w) & (a > r_obj) & (a <= r_obj + lmax + 1)
    if not m.any():
        return None
    bins = np.rint(a[m] - r_obj).astype(int)
    n = np.bincount(bins)
    s = np.bincount(bins, weights=x[m])
    ok = n > 0
    prof = s[ok] / n[ok]
    if len(prof) >= 3:
        prof = np.convolve(prof, np.ones(3) / 3.0, mode="valid")
    return float(prof.min())


def shadow_test(
    data: np.ndarray,
    valid: np.ndarray,
    r_obj: float,
    drow: float,
    dcol: float,
    lmax: float,
    centre: tuple[float, float] | None = None,
) -> ShadowTest | None:
    """The two-sided shadow test on one full-resolution crop with the candidate at ``centre`` (default
    the crop's middle). ``(drow, dcol)`` is the unit vector from an object to its shadow
    (``geo.shadow_direction``), ``lmax`` the probe length in px beyond the object's edge. The local ground
    is an annulus outside the probes; None when it has too few valid pixels (image edge, no-data)."""
    h, w_ = data.shape
    cy, cx = centre if centre is not None else (h // 2, w_ // 2)
    along, across, rad = _probe_geometry(h, w_, float(cy), float(cx), drow, dcol)
    x = data.astype(np.float32)
    inner = r_obj + lmax + 4
    outer = min(inner + 12, min(h, w_) / 2 - 1)
    ann = valid & (rad >= inner) & (rad <= outer)
    disc = valid & (rad <= r_obj)
    if ann.sum() < 50 or not disc.any():
        return None
    mu = float(x[ann].mean())
    sd = max(float(x[ann].std()), 1.0)
    w = max(1.5, 0.75 * r_obj)
    anti = _side_profile_min(x, valid, along, across, r_obj, lmax, w, +1)
    sun = _side_profile_min(x, valid, along, across, r_obj, lmax, w, -1)
    if anti is None or sun is None:
        return None
    return ShadowTest((float(x[disc].mean()) - mu) / sd, (anti - mu) / sd, (sun - mu) / sd)


def _crop(w: Window, r: int, c: int, size: int) -> tuple[np.ndarray, np.ndarray]:
    """``size`` px crop centred on image pixel (r, c) out of window ``w``, zero where the window ends."""
    half = size // 2
    rr, cc = r - half - w.row0, c - half - w.col0
    crop = np.zeros((size, size), np.uint16)
    v = np.zeros((size, size), bool)
    sr0, sc0 = max(rr, 0), max(cc, 0)
    sr1, sc1 = min(rr + size, w.data.shape[0]), min(cc + size, w.data.shape[1])
    if sr1 > sr0 and sc1 > sc0:
        crop[sr0 - rr : sr1 - rr, sc0 - cc : sc1 - cc] = w.data[sr0:sr1, sc0:sc1]
        v[sr0 - rr : sr1 - rr, sc0 - cc : sc1 - cc] = w.valid[sr0:sr1, sc0:sc1]
    return crop, v


def _by_block(points: list[tuple[int, int]], size: int) -> dict[tuple[int, int], list[int]]:
    half = size // 2
    groups: dict[tuple[int, int], list[int]] = {}
    for k, (r, c) in enumerate(points):
        groups.setdefault(((r - half) // BLOCK, (c - half) // BLOCK), []).append(k)
    return groups


def crops(strip: Strip, points: list[tuple[float, float]], size: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """Full-resolution ``size`` px (data, valid) crops centred on each (row, col), reading each 2048 px
    block once. A crop may straddle blocks, so each read is a block and a bit, keyed by the crop's
    top-left block."""
    pts = [(int(round(r)), int(round(c))) for r, c in points]
    out: list = [None] * len(pts)
    for (br, bc), idx in _by_block(pts, size).items():
        r0, c0 = br * BLOCK, bc * BLOCK
        w = strip.read(max(r0, 0), r0 + BLOCK + size, max(c0, 0), c0 + BLOCK + size)
        for k in idx:
            out[k] = _crop(w, pts[k][0], pts[k][1], size)
    return out


def shadow_tests(
    strip: Strip, cands: list[dict], indices: list[int], size: int, progress=None
) -> dict[int, ShadowTest | None]:
    """The shadow test for the listed candidates of one strip, block by block so memory stays at one
    block. Keys are candidate indices."""
    out: dict[int, ShadowTest | None] = {}
    lmax = shadow_probe_px(strip.label)
    if lmax is None:
        return dict.fromkeys(indices)
    drow, dcol = geo.shadow_direction(strip.label)
    pts = [(int(round(float(cands[i]["row"]))), int(round(float(cands[i]["col"])))) for i in indices]
    groups = _by_block(pts, size)
    for n, ((br, bc), idx) in enumerate(groups.items(), start=1):
        r0, c0 = br * BLOCK, bc * BLOCK
        w = strip.read(max(r0, 0), r0 + BLOCK + size, max(c0, 0), c0 + BLOCK + size)
        for k in idx:
            data, v = _crop(w, pts[k][0], pts[k][1], size)
            i = indices[k]
            out[i] = shadow_test(data, v, object_radius_px(int(cands[i].get("area_px", 0))), drow, dcol, lmax)
        if progress:
            progress(n, len(groups))
    return out


# --- stretch and rendering ---------------------------------------------------------------------------


def stretch_limits(crops_: list[tuple[np.ndarray, np.ndarray]]) -> tuple[float, float] | None:
    """One (lo, hi) for a whole sheet: the stretch percentiles over every thumbnail's valid pixels."""
    pool = [d[v] for d, v in crops_ if v.any()]
    if not pool:
        return None
    allv = np.concatenate(pool)
    if allv.size < 50:
        return None
    lo, hi = np.percentile(allv, STRETCH_PERCENTILES)
    return float(lo), float(hi)


def apply_stretch(data: np.ndarray, valid: np.ndarray, limits: tuple[float, float] | None) -> np.ndarray:
    if limits is None:
        return np.zeros(data.shape, np.uint8)
    lo, hi = limits
    x = np.clip((data.astype(np.float32) - lo) / max(hi - lo, 1.0), 0, 1)
    x[~valid] = 0
    return (x * 255).astype(np.uint8)


def _stretch(a: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """A single image stretched to its own percentiles (the maps; never the thumbnails of a sheet)."""
    if valid.sum() < 50:
        return np.zeros(a.shape, np.uint8)
    return apply_stretch(a, valid, stretch_limits([(a, valid)]))


def thumbnails(strip: Strip, picks: list[Pick], size: int, limits: tuple[float, float] | None = None):
    """Full-resolution ``size`` px thumbnails of the picks under one stretch. With ``limits`` None the
    stretch is taken over these thumbnails' pixels; pass the limits of a wider set to share a stretch
    between sheets. Returns (thumbnails, limits)."""
    cr = crops(strip, [(p.row, p.col) for p in picks], size)
    if limits is None:
        limits = stretch_limits(cr)
    return [apply_stretch(d, v, limits) for d, v in cr], limits


def _font():
    try:
        return ImageFont.load_default(size=14)
    except TypeError:  # Pillow before 10.1 has no sized default font
        return ImageFont.load_default()


def _shadow_arrow(d: ImageDraw.ImageDraw, x: int, y: int, lbl: StripLabel, length: int = 18):
    """A short arrow from (x, y) the way shadows fall in this image, with its label."""
    drow, dcol = geo.shadow_direction(lbl)
    x1, y1 = x + dcol * length, y + drow * length
    d.line([(x, y), (x1, y1)], fill=(255, 120, 255), width=2)
    for s in (+1, -1):
        a = math.atan2(drow, dcol) + math.pi + s * 0.5
        d.line([(x1, y1), (x1 + 6 * math.cos(a), y1 + 6 * math.sin(a))], fill=(255, 120, 255), width=2)
    d.text((x + length + 10, y - 6), "shadows fall this way", fill=(255, 120, 255))


def render_sheet(
    strip: Strip,
    picks: list[Pick],
    thumbs: list[np.ndarray],
    title: str,
    out: Path,
    cols: int = 10,
    zoom: int = 2,
    order: str = "score",
    limits: tuple[float, float] | None = None,
) -> Path:
    """One sheet of thumbnails in the order given (``picks`` already sorted by ``order``). Each cell names
    both ranks: ``#`` is the rank by detector score, ``S`` the rank by the shadow test."""
    if not picks:
        return out
    size = thumbs[0].shape[0] * zoom
    cell_h = size + 30
    rows = -(-len(picks) // cols)
    sheet = Image.new("RGB", (cols * size, rows * cell_h + 58), (0, 0, 0))
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
        srank = f"S{p.shadow_rank}" if p.shadow_rank is not None else "S-"
        sval = f"{p.shadow.score:+.1f}" if p.shadow is not None else "n/a"
        first, second = (f"#{p.rank}", srank) if order == "score" else (srank, f"#{p.rank}")
        d.text(
            (x + 3, y + size + 2), f"{first} {second} {p.branch} {p.score:.2f} {p.distance_m:.0f} m", fill=(255, 220, 0)
        )
        d.text((x + 3, y + size + 15), f"shadow {sval}  l{p.row + 1:.0f} s{p.col + 1:.0f}", fill=(220, 220, 220))
    fy = rows * cell_h
    d.text((4, fy + 4), title, fill=(255, 255, 255))
    lim = f"stretch {limits[0]:.0f}..{limits[1]:.0f} DN over the whole sheet" if limits else "no stretch"
    d.text(
        (4, fy + 20),
        f"Credit: {CREDIT}. Each tile {thumbs[0].shape[0] * strip.label.scale_m:.0f} m across at full resolution; "
        f"cross marks the candidate; {lim}. # rank by score, S rank by the two-sided shadow test "
        "(bright, dark on the anti-sun side, not dark on the sun side).",
        fill=(200, 200, 200),
    )
    _shadow_arrow(d, 14, fy + 44, strip.label)
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
    shadow_picks: list[Pick] | None = None,
    lbl: StripLabel | None = None,
) -> Image.Image:
    """The search area as one image: every pick as a numbered circle (yellow, the number is its rank by
    score; magenta with an S, its rank by the shadow test), the anchor as a cross with its precision
    circle, the search radius, and the numbered grid tiles when a grid is given. ``w`` is a reduced
    window (``Window.step`` image px per data px)."""
    img8 = _stretch(w.data, w.valid)
    im = Image.fromarray(img8).convert("RGB")
    d = ImageDraw.Draw(im)
    s = w.step
    font = _font()

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
    for p in shadow_picks or []:
        x, y = xy(p.row, p.col)
        d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=(255, 120, 255))
        d.text((x + 8, y + 2), f"S{p.shadow_rank}", fill=(255, 120, 255), font=font)
    for p in picks:
        x, y = xy(p.row, p.col)
        d.ellipse([x - 5, y - 5, x + 5, y + 5], outline=(255, 220, 0))
        d.text((x + 6, y - 8), str(p.rank), fill=(255, 255, 0), font=font)
    footer = Image.new("RGB", (im.width, 56), (0, 0, 0))
    fd = ImageDraw.Draw(footer)
    fd.text((4, 2), title, fill=(255, 255, 255))
    fd.text(
        (4, 18),
        f"Credit: {CREDIT}. {scale_m * s:.2f} m/px shown. Yellow: pick and its rank by score; magenta S: rank by the "
        f"shadow test; cyan: anchor and its precision ({precision_m:.0f} m); blue: search radius ({radius_m:.0f} m); "
        "brown: grid tiles.",
        fill=(200, 200, 200),
    )
    if lbl is not None:
        _shadow_arrow(fd, 14, 42, lbl)
    canvas = Image.new("RGB", (im.width, im.height + footer.height))
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
    shadow_picks: list[Pick] | None = None,
) -> Path:
    r_px = int(math.ceil(radius_m / strip.label.scale_m))
    r, c = int(round(row0)), int(round(col0))
    w = strip.read_reduced(r - r_px, r + r_px, c - r_px, c + r_px, step)
    im = draw_map(
        w, strip.label.scale_m, row0, col0, radius_m, precision_m, picks, grid, title, shadow_picks, strip.label
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out

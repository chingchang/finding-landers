"""Transplant injection: real hardware cut at full resolution from a tuning strip and planted into tiles of
the search strips, then scored as injection (recall at a fixed false-alarm rate).

The synthetic injector (``landers.inject``) draws discs; this one moves pixels. For every piece recorded in
the answer key, a disc of the source strip around the recorded position is cut, wide enough to hold the
object, its shadow for an object ``shadow_height_m`` tall under the source sun, and the key's own position
uncertainty. The cut is expressed as a *gain*: each pixel divided by the median of a ring of ground around
the disc, so the object stays as many times brighter or darker than its surroundings as it was at home,
under either strip's exposure. The gain is rotated so that the source's shadow direction becomes the
target's (both from the labels' sub-solar azimuth), feathered at the rim, and multiplied into the target
tile. Pixels saturated at the source stay saturated. Targets are chosen among the search strips of the
same map scale with the nearest tangent of incidence, so the shadow length is as right as the data allow;
the ratio of the two tangents is recorded on every placement because it is not always one.

Sham cuts are the control: the same procedure on a disc of plain ground near each piece, with nothing in
it. If shams are detected more often than natural ground, the seam is being found, not the hardware. Sham
detections count as false alarms.

Rules enforced here: a source must be a strip of a tuning site; a target must be a search-area strip
(manifest case ``mpl_summer``) of the same scale; nothing is cut from, or planted into, a held-out,
spare or final-exam site. Observation ids appear in the output file only; the output lives under out/.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage

from landers import config
from landers.label import StripLabel
from landers.score import piece_kind
from landers.strip import SATURATED, Strip, Window

SEARCH_CASE = "mpl_summer"


@dataclass
class TransplantConfig:
    shadow_height_m: float = 3.0  # the cut reaches the shadow of an object this tall under the source sun
    position_margin_m: float = 2.5  # the key's stated precision, added to the cut radius
    feather_px: float = 3.0  # Gaussian sigma of the rim, so the seam is softer than the optics
    ring_px: int = 24  # width of the ground ring the background median comes from
    sham_offset_m: float = 120.0  # how far from a piece its sham cut is taken
    sham_clear_m: float = 50.0  # a sham disc stays this far from every recorded piece on the strip
    placement_margin_px: int = 16  # extra clearance from the tile edge and between placements

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class Cut:
    site: str
    piece: str
    kind: str  # hardware, fabric or mark (controls/thresholds.json piece_kinds)
    source: str  # observation id of the source strip
    row: float  # 0-based source pixel of the recorded (or sham) centre
    col: float
    size_m: float
    scale_m: float
    incidence_deg: float
    sub_solar_azimuth_deg: float
    radius_px: int  # disc radius; the arrays are (2 * half + 1) square with half = radius + 3 * feather
    sham: bool
    gain: np.ndarray  # float64, 1 where nothing changes
    weight: np.ndarray  # float64 in [0, 1]: 1 inside the disc, feathered to 0
    saturated: np.ndarray  # bool: saturated at the source
    background_dn: float
    n_saturated: int
    n_nodata: int
    other_pieces_in_cut: list[str] = field(default_factory=list)

    @property
    def tan_incidence(self) -> float:
        return math.tan(math.radians(self.incidence_deg))

    @property
    def half(self) -> int:
        return self.gain.shape[0] // 2

    def to_json(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if k not in ("gain", "weight", "saturated")}
        d["row"], d["col"] = round(self.row, 1), round(self.col, 1)
        d["tan_incidence"] = round(self.tan_incidence, 3)
        d["half_px"] = self.half
        return d


# ---------------------------------------------------------------- which strips may be used


def tuning_sources(sites: dict) -> dict[str, str]:
    """observation id -> site name for every strip of a tuning site. Nothing else may be cut from."""
    return {sid: s["name"] for s in sites["sites"] if s["group"] == "tuning" for sid in s["strips"]}


def control_strips(sites: dict) -> set[str]:
    return {sid for s in sites["sites"] for sid in s["strips"]}


def search_targets(sites: dict, manifest_text: str) -> list[str]:
    """Observation ids that may be planted into: the manifest's search-area case, minus any control
    strip (none should be there; the check is cheap and the rule is absolute)."""
    controls = control_strips(sites)
    out = []
    for line in manifest_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == SEARCH_CASE and parts[1] not in controls:
            out.append(parts[1])
    return out


def nearest_targets(source_lbl: StripLabel, targets: dict[str, StripLabel], n: int) -> list[str]:
    """The ``n`` target strips of the source's map scale whose tangent of incidence is nearest the
    source's, nearest first. Empty when no target has that scale."""
    t_s = math.tan(math.radians(source_lbl.incidence_deg))
    same = [
        (abs(math.tan(math.radians(lbl.incidence_deg)) - t_s), sid)
        for sid, lbl in targets.items()
        if lbl.scale_m == source_lbl.scale_m
    ]
    return [sid for _, sid in sorted(same)[:n]]


# ---------------------------------------------------------------- cutting


def cut_radius_px(size_m: float, lbl: StripLabel, cfg: TransplantConfig) -> int:
    r_m = size_m / 2.0 + cfg.shadow_height_m * math.tan(math.radians(lbl.incidence_deg)) + cfg.position_margin_m
    return int(math.ceil(r_m / lbl.scale_m))


def _disc(n: int, radius: float) -> np.ndarray:
    c = n // 2
    yy, xx = np.mgrid[:n, :n]
    return np.hypot(yy - c, xx - c) <= radius


def cut_piece(
    strip: Strip,
    site: str,
    piece: str,
    kind: str,
    row: float,
    col: float,
    size_m: float,
    cfg: TransplantConfig,
    sham: bool = False,
) -> Cut | None:
    """Cut the disc around (row, col). None when the window is clipped by the image edge or the ring has
    too little valid ground to set a background."""
    lbl = strip.label
    radius = cut_radius_px(size_m, lbl, cfg)
    half = radius + int(math.ceil(3 * cfg.feather_px))
    n = 2 * half + 1
    r, c = int(round(row)), int(round(col))
    r0, c0 = r - half, c - half
    if r0 < 0 or c0 < 0 or r0 + n > lbl.lines or c0 + n > lbl.samples:
        return None
    outer = half + cfg.ring_px
    win = strip.read(r - outer, r + outer + 1, c - outer, c + outer + 1)
    if win.shape != (2 * outer + 1, 2 * outer + 1):
        return None
    data = win.data.astype(np.float64)
    valid = win.valid
    nn = 2 * outer + 1
    ring = _disc(nn, outer) & ~_disc(nn, half + 1) & valid
    if ring.sum() < 200:
        return None
    bg = float(np.median(data[ring]))
    if bg <= 0:
        return None
    sl = slice(outer - half, outer + half + 1)
    sub = data[sl, sl]
    sat = win.data[sl, sl] >= SATURATED
    nodata = win.data[sl, sl] == 0
    gain = np.where(nodata, 1.0, sub / bg)
    disc = _disc(n, radius).astype(np.float64)
    weight = ndimage.gaussian_filter(disc, cfg.feather_px) if cfg.feather_px > 0 else disc
    weight = np.clip(weight / max(weight.max(), 1e-9), 0.0, 1.0)
    return Cut(
        site,
        piece,
        kind,
        lbl.observation_id,
        float(row),
        float(col),
        float(size_m),
        lbl.scale_m,
        lbl.incidence_deg,
        lbl.sub_solar_azimuth_deg,
        radius,
        sham,
        gain,
        weight,
        sat,
        bg,
        int(sat.sum()),
        int(nodata.sum()),
    )


def key_pieces(answers: dict, thresholds: dict, allowed: dict[str, str]) -> list[dict]:
    """Recorded pieces of the answer key whose strip is a tuning strip: site, piece, kind, strip, row,
    col, size_m. A recorded piece on a strip that is not a tuning strip is refused, not skipped."""
    out = []
    for site in answers["sites"]:
        for pc in site["pieces"]:
            if pc.get("line") is None or pc.get("sample") is None or pc.get("strip") is None:
                continue
            if pc["strip"] not in allowed:
                raise ValueError(f"{site['name']}/{pc['piece']}: recorded on a strip that is not a tuning strip")
            out.append(
                {
                    "site": site["name"],
                    "piece": pc["piece"],
                    "kind": piece_kind(pc["piece"], thresholds),
                    "strip": pc["strip"],
                    "row": float(pc["line"]) - 1.0,
                    "col": float(pc["sample"]) - 1.0,
                    "size_m": float(pc.get("size_m") or 3.0),
                }
            )
    return out


def sham_position(
    strip: Strip,
    row: float,
    col: float,
    radius_px: int,
    pieces_on_strip: list[tuple[float, float]],
    cfg: TransplantConfig,
) -> tuple[float, float] | None:
    """A spot ``sham_offset_m`` from (row, col) whose disc is fully valid and at least ``sham_clear_m``
    from every recorded piece on the strip; eight bearings are tried."""
    lbl = strip.label
    off = cfg.sham_offset_m / lbl.scale_m
    clear = cfg.sham_clear_m / lbl.scale_m + radius_px
    for k in range(8):
        a = k * math.pi / 4
        r, c = row + off * math.sin(a), col + off * math.cos(a)
        if any(math.hypot(r - pr, c - pc) < clear for pr, pc in pieces_on_strip):
            continue
        h = radius_px + cfg.ring_px + 12
        if r - h < 0 or c - h < 0 or r + h >= lbl.lines or c + h >= lbl.samples:
            continue
        w = strip.read(int(r) - h, int(r) + h + 1, int(c) - h, int(c) + h + 1)
        if w.valid.all():
            return float(r), float(c)
    return None


# ---------------------------------------------------------------- planting


def rotation_deg(source_az: float, target_az: float) -> float:
    """Angle for ``scipy.ndimage.rotate`` that turns the source's shadow direction into the target's.
    ``ndimage.rotate(+t)`` turns a direction vector ``(sin a, cos a)`` into ``(sin(a - t), cos(a - t))``
    in (row, col), so the angle is the source azimuth minus the target azimuth."""
    return float((source_az - target_az + 180.0) % 360.0 - 180.0)


def rotated_arrays(cut: Cut, angle_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Gain, weight and saturation mask turned by ``angle_deg`` about the centre, same shape. The gain is
    interpolated linearly (a blur of under half a pixel, less than the detector's own smoothing); the
    weight is re-clipped; the saturation mask is nearest-neighbour."""
    if abs(angle_deg) < 1e-6:
        return cut.gain, cut.weight, cut.saturated
    g = ndimage.rotate(cut.gain, angle_deg, reshape=False, order=1, mode="constant", cval=1.0)
    w = np.clip(ndimage.rotate(cut.weight, angle_deg, reshape=False, order=1, mode="constant", cval=0.0), 0, 1)
    s = ndimage.rotate(cut.saturated.astype(np.uint8), angle_deg, reshape=False, order=0, mode="constant", cval=0)
    return g, w, s.astype(bool)


@dataclass
class Placement:
    tile: str  # "<target id>:<row0>:<col0>" of the tile
    target: str
    row: float  # tile-local centre, 0-based
    col: float
    cut_index: int
    site: str
    piece: str
    kind: str
    sham: bool
    rotation_deg: float
    tan_ratio: float  # target tan(incidence) / source tan(incidence)
    radius_px: int

    def to_json(self) -> dict:
        d = asdict(self)
        d["row"], d["col"] = round(self.row, 1), round(self.col, 1)
        d["rotation_deg"], d["tan_ratio"] = round(self.rotation_deg, 2), round(self.tan_ratio, 3)
        return d


def plant(data: np.ndarray, valid: np.ndarray, cut: Cut, row: int, col: int, angle_deg: float) -> bool:
    """Multiply the rotated gain into ``data`` (float64, modified in place) centred on (row, col). False,
    and nothing changed, when the footprint is not entirely valid ground."""
    g, w, s = rotated_arrays(cut, angle_deg)
    h = cut.half
    r0, c0 = row - h, col - h
    r1, c1 = r0 + g.shape[0], c0 + g.shape[1]
    if r0 < 0 or c0 < 0 or r1 > data.shape[0] or c1 > data.shape[1]:
        return False
    if not valid[r0:r1, c0:c1].all():
        return False
    region = data[r0:r1, c0:c1]
    planted = region * (1.0 + (g - 1.0) * w)
    planted = np.where(s & (w > 0.5), np.maximum(planted, float(SATURATED)), planted)
    data[r0:r1, c0:c1] = np.clip(planted, 1.0, 1023.0)
    return True


def place_in_tile(
    win: Window,
    lbl: StripLabel,
    cuts: list[Cut],
    cut_indices: list[int],
    rng: np.random.Generator,
    cfg: TransplantConfig,
    tile_id: str,
    tries: int = 300,
) -> tuple[Window, list[Placement]]:
    """Plant the listed cuts at random non-overlapping spots of the tile. Returns the planted tile and
    the placements that fit (a cut that finds no room is left out, not forced)."""
    data = win.data.astype(np.float64)
    valid = win.valid
    h, w = valid.shape
    taken: list[tuple[int, int, int]] = []
    out: list[Placement] = []
    t_tan = math.tan(math.radians(lbl.incidence_deg))
    for ci in cut_indices:
        cut = cuts[ci]
        margin = cut.half + cfg.placement_margin_px
        if h <= 2 * margin or w <= 2 * margin:
            continue
        angle = rotation_deg(cut.sub_solar_azimuth_deg, lbl.sub_solar_azimuth_deg)
        for _ in range(tries):
            r = int(rng.integers(margin, h - margin))
            c = int(rng.integers(margin, w - margin))
            if any(math.hypot(r - tr, c - tc) < (margin + tm) for tr, tc, tm in taken):
                continue
            if not valid[r - margin : r + margin + 1, c - margin : c + margin + 1].all():
                continue
            if plant(data, valid, cut, r, c, angle):
                taken.append((r, c, margin))
                out.append(
                    Placement(
                        tile_id,
                        lbl.observation_id,
                        float(r),
                        float(c),
                        ci,
                        cut.site,
                        cut.piece,
                        cut.kind,
                        cut.sham,
                        angle,
                        t_tan / cut.tan_incidence,
                        cut.radius_px,
                    )
                )
                break
    planted = np.clip(data, 0, 1023).astype(np.uint16)
    planted[~valid] = 0
    return Window(win.row0, win.col0, planted, valid.copy()), out


# ---------------------------------------------------------------- scoring


def sham_hits(detections: list[dict], placements: list[Placement], threshold: float | None, radius_of) -> dict:
    """How many sham placements have a kept detection within their match radius, and the chance rate: the
    kept density times the area of a match disc, averaged over the shams."""
    kept = [d for d in detections if threshold is None or float(d["score"]) > threshold]
    by_tile: dict[str, list[dict]] = {}
    for d in kept:
        by_tile.setdefault(d["tile"], []).append(d)
    shams = [p for p in placements if p.sham]
    hit = 0
    for p in shams:
        r = radius_of(p)
        if any(math.hypot(float(d["row"]) - p.row, float(d["col"]) - p.col) <= r for d in by_tile.get(p.tile, [])):
            hit += 1
    return {"n": len(shams), "hit": hit, "rate": round(hit / len(shams), 3) if shams else None}


def load_labels(ids: list[str]) -> dict[str, StripLabel]:
    out = {}
    for sid in ids:
        p = config.label_path(sid)
        if p is not None:
            out[sid] = StripLabel.read(p)
    return out


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1))

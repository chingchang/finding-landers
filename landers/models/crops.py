"""Blind crops: what a vision model is allowed to see.

A crop is built from pixel arrays only; this module never takes an observation id, a path, a coordinate
or a date, so it cannot put one into an image. Each PNG is three identical 8-bit channels with no text
chunk. A ``BlindCrop`` is the square at native resolution, the same centre at 4x zoom, and, when given, a
reference crop of similar ground from somewhere else that the prompt labels only as "reference". The
few-shot prompt (plan item 9d, ``landers.models.fewshot``) adds labelled example views after those.

Augmentations (per vote): a random offset of the centre, horizontal and vertical flips, and a different
percentile stretch. They are drawn from a seeded generator and recorded, so a vote can be rebuilt.
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field

import numpy as np
from PIL import Image

from landers.models import leak

STRETCHES = ((0.5, 99.5), (1.0, 99.0), (2.0, 98.0), (0.2, 99.8))


@dataclass
class Augmentation:
    drow: int = 0
    dcol: int = 0
    flip_h: bool = False
    flip_v: bool = False
    lo_pct: float = 0.5
    hi_pct: float = 99.5

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class BlindCrop:
    native_png: bytes
    zoom_png: bytes
    reference_png: bytes | None
    size: int
    zoom: int
    augmentation: Augmentation
    valid_fraction: float
    native_u8: np.ndarray = field(repr=False, default=None)
    examples: list[tuple[str, bytes]] = field(default_factory=list)  # (label, png), the few-shot prompt only

    def images(self) -> list[bytes]:
        out = [self.native_png, self.zoom_png]
        if self.reference_png is not None:
            out.append(self.reference_png)
        out.extend(png for _, png in self.examples)
        return out

    def to_json(self) -> dict:
        return {
            "size": self.size,
            "zoom": self.zoom,
            "augmentation": self.augmentation.to_json(),
            "valid_fraction": round(self.valid_fraction, 3),
            "has_reference": self.reference_png is not None,
            **({"examples": [label for label, _ in self.examples]} if self.examples else {}),
        }


def square_crop(
    data: np.ndarray, valid: np.ndarray, row: float, col: float, size: int
) -> tuple[np.ndarray, np.ndarray]:
    """``size`` px square centred on (row, col); outside the array is zero and invalid."""
    r0, c0 = int(round(row)) - size // 2, int(round(col)) - size // 2
    out = np.zeros((size, size), np.float32)
    ok = np.zeros((size, size), bool)
    rs, cs = max(r0, 0), max(c0, 0)
    re, ce = min(r0 + size, data.shape[0]), min(c0 + size, data.shape[1])
    if re > rs and ce > cs:
        out[rs - r0 : re - r0, cs - c0 : ce - c0] = data[rs:re, cs:ce]
        ok[rs - r0 : re - r0, cs - c0 : ce - c0] = valid[rs:re, cs:ce]
    return out, ok


def stretch(arr: np.ndarray, valid: np.ndarray, lo_pct: float, hi_pct: float) -> np.ndarray:
    """One global percentile stretch over the valid pixels to uint8; invalid pixels become 0."""
    u8 = np.zeros(arr.shape, np.uint8)
    if valid.sum() < 2:
        return u8
    lo, hi = np.percentile(arr[valid], [lo_pct, hi_pct])
    if hi <= lo:
        hi = lo + 1.0
    s = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
    u8[valid] = (s[valid] * 255.0 + 0.5).astype(np.uint8)
    return u8


def zoom_center(u8: np.ndarray, zoom: int) -> np.ndarray:
    """The central ``size/zoom`` square scaled up ``zoom`` times by pixel repetition (no interpolation
    invents detail)."""
    size = u8.shape[0]
    k = size // zoom
    r0 = (size - k) // 2
    core = u8[r0 : r0 + k, r0 : r0 + k]
    big = np.repeat(np.repeat(core, zoom, axis=0), zoom, axis=1)
    return big[:size, :size]


def to_png(u8: np.ndarray) -> bytes:
    """Three identical channels (grayscale is undocumented at the API), no metadata."""
    rgb = np.stack([u8, u8, u8], axis=-1)
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, format="PNG", optimize=False)
    png = buf.getvalue()
    leak.check_png(png, "crop")
    return png


def draw_augmentations(rng: np.random.Generator, n: int, size: int, first_plain: bool = True) -> list[Augmentation]:
    """``n`` augmentations; the first is the plain crop when ``first_plain`` so one vote sees the
    unaltered view."""
    out = []
    for i in range(n):
        if i == 0 and first_plain:
            out.append(Augmentation())
            continue
        lo, hi = STRETCHES[int(rng.integers(len(STRETCHES)))]
        m = size // 8
        out.append(
            Augmentation(
                int(rng.integers(-m, m + 1)),
                int(rng.integers(-m, m + 1)),
                bool(rng.integers(2)),
                bool(rng.integers(2)),
                lo,
                hi,
            )
        )
    return out


def build_crop(
    data: np.ndarray,
    valid: np.ndarray,
    row: float,
    col: float,
    size: int = 256,
    zoom: int = 4,
    aug: Augmentation | None = None,
    reference: tuple[np.ndarray, np.ndarray, float, float] | None = None,
) -> BlindCrop:
    """A blind crop of ``data`` around (row, col). ``reference`` is (data, valid, row, col) of other ground,
    stretched the same way and flipped the same way, so the two views differ only in content."""
    aug = aug or Augmentation()
    arr, ok = square_crop(data, valid, row + aug.drow, col + aug.dcol, size)
    u8 = stretch(arr, ok, aug.lo_pct, aug.hi_pct)
    ref_png = None
    if reference is not None:
        rarr, rok = square_crop(reference[0], reference[1], reference[2], reference[3], size)
        ru8 = stretch(rarr, rok, aug.lo_pct, aug.hi_pct)
        ref_png = to_png(_flip(ru8, aug))
    u8 = _flip(u8, aug)
    return BlindCrop(
        native_png=to_png(u8),
        zoom_png=to_png(zoom_center(u8, zoom)),
        reference_png=ref_png,
        size=size,
        zoom=zoom,
        augmentation=aug,
        valid_fraction=float(ok.mean()),
        native_u8=u8,
    )


def _flip(u8: np.ndarray, aug: Augmentation) -> np.ndarray:
    if aug.flip_h:
        u8 = u8[:, ::-1]
    if aug.flip_v:
        u8 = u8[::-1, :]
    return np.ascontiguousarray(u8)

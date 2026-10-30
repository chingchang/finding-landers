"""Few-shot examples for the Wonder vote (plan item 9d), behind a flag that is off by default.

An example is a labelled view of a known object from another site: a recorded piece from the key (label
"hardware") or a top false alarm of the scored list (label "natural"). It is drawn like the candidate's
image 2, the centre of a native square enlarged 4 times, after the source has been resampled to the
candidate strip's metres per pixel and turned so its sun comes from the candidate strip's direction. It is
then stretched and flipped with the candidate's own augmentation, so a flip of the candidate flips the
examples with it and the sun stays on the same side in every image.

Leave one site out: when a strip is voted on, every example comes from the other sites. The model gets the
pixels and the two labels only. Where an example comes from (strip, position, piece name) stays in the
``Example`` records, which the run writes under ``out/`` and never sends.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass

import numpy as np
from scipy import ndimage

from landers.models import crops
from landers.score import match_radius_px, piece_kind
from landers.transplant import rotation_deg

LABELS = ("hardware", "natural")
EXAMPLE_KINDS = ("hardware", "fabric")  # marks (a crash scar) are ground, not an object; not shown as hardware

Reader = Callable[[float, float, int], tuple[np.ndarray, np.ndarray]]


@dataclass(frozen=True)
class Example:
    label: str  # "hardware" or "natural"; the only part the model sees, besides the pixels
    site: str
    strip: str
    row: float  # 0-based full-resolution pixel
    col: float
    what: str  # the piece name, or "false alarm rank N"

    def to_json(self) -> dict:
        return asdict(self)


def site_of_strip(key: dict) -> dict[str, str]:
    return {sid: site["name"] for site in key["sites"] for sid in site["strips"]}


def hardware_pool(key: dict, thresholds: dict) -> list[Example]:
    """Every recorded piece of a hardware or fabric kind, at its key position."""
    out = []
    for site in key["sites"]:
        for pc in site["pieces"]:
            if pc.get("line") is None or pc.get("strip") is None:
                continue
            if piece_kind(pc["piece"], thresholds) not in EXAMPLE_KINDS:
                continue
            out.append(
                Example("hardware", site["name"], pc["strip"], float(pc["line"]) - 1.0, float(pc["sample"]) - 1.0, pc["piece"])
            )
    return out


def natural_pool(key: dict, thresholds: dict, inputs: dict, top: int = 20) -> list[Example]:
    """The false alarms in each strip's top ``top`` of the scored list: candidates farther than every
    recorded piece's match radius (the same test ``scripts/score.py`` counts hits with)."""
    sites = site_of_strip(key)
    out = []
    for sid, entry in inputs["strips"].items():
        if sid not in sites:
            continue
        scale = float(entry.get("scale_m", 0.25))
        truths = []
        for site in key["sites"]:
            for pc in site["pieces"]:
                if pc.get("strip") == sid and pc.get("line") is not None:
                    kind = piece_kind(pc["piece"], thresholds)
                    truths.append((float(pc["line"]) - 1.0, float(pc["sample"]) - 1.0, match_radius_px(thresholds, scale, kind)))
        cands = sorted(entry["candidates"], key=lambda c: -c["score"])[:top]
        for rank, c in enumerate(cands, start=1):
            if any(math.hypot(c["row"] - r, c["col"] - k) <= rad for r, k, rad in truths):
                continue
            out.append(Example("natural", sites[sid], sid, float(c["row"]), float(c["col"]), f"false alarm rank {rank}"))
    return out


def leave_site_out(pool: list[Example], site: str) -> list[Example]:
    return [e for e in pool if e.site != site]


def draw(rng: np.random.Generator, hardware: list[Example], natural: list[Example], n_each: int) -> list[Example]:
    """``n_each`` of each label without replacement, in a shuffled order so the position of an image does
    not tell its label."""
    if len(hardware) < n_each or len(natural) < n_each:
        raise ValueError(f"pools too small for {n_each} of each: {len(hardware)} hardware, {len(natural)} natural")
    picks = [hardware[int(i)] for i in rng.choice(len(hardware), n_each, replace=False)]
    picks += [natural[int(i)] for i in rng.choice(len(natural), n_each, replace=False)]
    order = rng.permutation(len(picks))
    return [picks[int(i)] for i in order]


@dataclass(frozen=True)
class View:
    """How a source strip's pixels are turned into the candidate strip's frame."""

    src_scale_m: float
    src_sun_az: float
    tgt_scale_m: float
    tgt_sun_az: float

    @property
    def factor(self) -> float:  # target pixels per source pixel
        return self.src_scale_m / self.tgt_scale_m

    @property
    def angle(self) -> float:
        return rotation_deg(self.src_sun_az, self.tgt_sun_az)


def example_u8(read: Reader, row: float, col: float, view: View, aug: crops.Augmentation, size: int = 256, zoom: int = 4) -> np.ndarray:
    """The example as the candidate's image 2: a ``size`` px square at the target scale and sun direction,
    stretched with ``aug``'s percentiles, flipped with ``aug``'s flips, centre enlarged ``zoom`` times."""
    src_size = int(math.ceil(size / view.factor * 1.5)) + 4  # room for the turn
    data, valid = read(row, col, src_size)
    data = data.astype(np.float32)
    if abs(view.factor - 1.0) > 1e-6:
        data = ndimage.zoom(data, view.factor, order=1)
        valid = ndimage.zoom(valid.astype(np.uint8), view.factor, order=0).astype(bool)
    if abs(view.angle) > 1e-6:
        data = ndimage.rotate(data, view.angle, reshape=False, order=1, mode="constant", cval=0.0)
        valid = ndimage.rotate(valid.astype(np.uint8), view.angle, reshape=False, order=0, mode="constant", cval=0).astype(bool)
    arr, ok = crops.square_crop(data, valid, data.shape[0] / 2.0, data.shape[1] / 2.0, size)
    u8 = crops._flip(crops.stretch(arr, ok, aug.lo_pct, aug.hi_pct), aug)
    return crops.zoom_center(u8, zoom)


class ExampleSource:
    """The ``examples`` hook for ``run.vote_pass``: per vote, ``n_each`` hardware and natural examples from
    the other sites, drawn with a generator seeded by (seed, rank, vote), so a vote's examples do not depend
    on which other votes ran. ``drawn`` keeps where each came from, keyed by (rank, vote), for the record."""

    def __init__(
        self,
        hardware: list[Example],
        natural: list[Example],
        readers: dict[str, Reader],
        views: dict[str, View],
        n_each: int = 2,
        seed: int = 0,
        size: int = 256,
    ):
        self.hardware, self.natural = hardware, natural
        self.readers, self.views = readers, views
        self.n_each, self.seed, self.size = n_each, seed, size
        self.drawn: dict[tuple[int, int], list[Example]] = {}
        self._windows: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}  # a pool is a few dozen objects

    def _reader(self, strip: str) -> Reader:
        def read(row: float, col: float, size: int):
            k = (strip, row, col, size)
            if k not in self._windows:
                self._windows[k] = self.readers[strip](row, col, size)
            return self._windows[k]

        return read

    def __call__(self, i: int, j: int, aug: crops.Augmentation) -> list[tuple[str, bytes]]:
        rng = np.random.default_rng([self.seed, i, j])
        picks = draw(rng, self.hardware, self.natural, self.n_each)
        self.drawn[(i, j)] = picks
        out = []
        for e in picks:
            u8 = example_u8(self._reader(e.strip), e.row, e.col, self.views[e.strip], aug, self.size)
            out.append((e.label, crops.to_png(u8)))
        return out

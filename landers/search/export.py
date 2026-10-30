"""Crop export: what must survive when the search strips' JP2 files are deleted.

For every strip of the search area and of the tuning sites: the top candidates as native-resolution crops, the
1/16 overview, and the label. For the tuning strips also a window around every recorded piece and every sham
position. For the search strips listed in the injection tuning ground (the decision of 2026-10-29 02:00), the
target tiles and no others. A strip of a blind site is refused: no agent reads one.

Crops keep the raw samples: uint16 holding 10-bit values, 0 no data, 1022 and 1023 saturated, so
``landers.strip.valid_mask`` applies. A chunk stores the low and the high bytes as two arrays because noisy
10-bit samples compress better that way (out/export/check.json has the sizes). Each file is written to a
temporary name and renamed, so a killed run leaves nothing half written, and a strip's index.json comes last:
a strip is exported when its index exists.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np

from landers import config
from landers.label import StripLabel
from landers.strip import OVERVIEW_LEVEL, Window, valid_mask

CHUNK = 100  # crops per file, best rank first, so the top of a list costs one file
BLOCK = 4096  # the strip is read in blocks of this many pixels; a window this size decodes in about a second


def exportable_strips(sites: dict, manifest_text: str, search_case: str) -> dict[str, str]:
    """observation id -> "search" or "tuning". Blind sites' strips are not in it, even if listed under the case."""
    roles = {}
    for line in manifest_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == search_case:
            roles[parts[1]] = "search"
    for s in sites["sites"]:
        for sid in s["strips"]:
            if s["group"] == "tuning":
                roles[sid] = "tuning"
            else:
                roles.pop(sid, None)
    return roles


def refuse_blind(sites: dict, observation_id: str) -> None:
    for s in sites["sites"]:
        if s["group"] != "tuning" and observation_id in s["strips"]:
            raise ValueError(f"{observation_id} belongs to a site that is not a tuning site; it is not exported")


def rank_top(candidates: list[dict], top: int) -> list[dict]:
    """Best first by score, the order of ``landers.search.persistence.survivors``, keeping only what a later
    stage needs to find a crop again."""
    ranked = sorted(candidates, key=lambda c: -float(c["score"]))[:top]
    out = []
    for i, c in enumerate(ranked):
        row = {k: c[k] for k in ("row", "col", "score", "branch", "grade", "area_px") if k in c}
        row["rank"] = i + 1
        out.append(row)
    return out


def _write_npz(path: Path, **arrays) -> None:
    tmp = path.with_name(path.name + ".part.npz")
    np.savez_compressed(tmp, **arrays)
    tmp.replace(path)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def split_bytes(x: np.ndarray) -> dict:
    u = x.astype(np.uint16)
    return {"low": (u & 255).astype(np.uint8), "high": (u >> 8).astype(np.uint8)}


def join_bytes(low: np.ndarray, high: np.ndarray) -> np.ndarray:
    return low.astype(np.uint16) | (high.astype(np.uint16) << 8)


def cut_square(win: Window, row: float, col: float, size: int) -> np.ndarray:
    """``size`` px square centred as ``landers.models.crops.square_crop`` centres it. Outside the window is 0, no data."""
    r0, c0 = int(round(row)) - size // 2, int(round(col)) - size // 2
    out = np.zeros((size, size), np.uint16)
    rs, cs = max(r0, win.row0), max(c0, win.col0)
    re, ce = min(r0 + size, win.row0 + win.shape[0]), min(c0 + size, win.col0 + win.shape[1])
    if re > rs and ce > cs:
        out[rs - r0 : re - r0, cs - c0 : ce - c0] = win.data[rs - win.row0 : re - win.row0, cs - win.col0 : ce - win.col0]
    return out


def read_blocks(strip, rows: list[dict], size: int):
    """Yield (window, indices of rows inside it): the rows grouped by block, each block read once, so 2,000 crops
    cost a few hundred reads."""
    groups: dict[tuple[int, int], list[int]] = {}
    for i, c in enumerate(rows):
        groups.setdefault((int(c["row"]) // BLOCK, int(c["col"]) // BLOCK), []).append(i)
    for (_, _), idx in sorted(groups.items()):
        r0 = min(int(round(rows[i]["row"])) for i in idx) - size // 2
        c0 = min(int(round(rows[i]["col"])) for i in idx) - size // 2
        r1 = max(int(round(rows[i]["row"])) for i in idx) - size // 2 + size
        c1 = max(int(round(rows[i]["col"])) for i in idx) - size // 2 + size
        yield _clipped_read(strip, r0, r1, c0, c1), idx


def _clipped_read(strip, r0: int, r1: int, c0: int, c1: int) -> Window:
    """A window that may hang over the image edge; an all-outside request returns an empty window."""
    h, w = strip.shape
    if r1 <= 0 or c1 <= 0 or r0 >= h or c0 >= w:
        return Window(r0, c0, np.zeros((0, 0), np.uint16), np.zeros((0, 0), bool))
    return strip.read(r0, r1, c0, c1)


def export_strip(strip, rows: list[dict], size: int, dest: Path, meta: dict) -> dict:
    """Write the crops of ``rows`` (ranked) under ``dest`` and the index last. ``dest`` is replaced whole on a rerun."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    stack = np.zeros((len(rows), size, size), np.uint16)
    reads = 0
    for win, idx in read_blocks(strip, rows, size):
        reads += 1
        for i in idx:
            stack[i] = cut_square(win, rows[i]["row"], rows[i]["col"], size)
    files = []
    for start in range(0, len(rows), CHUNK):
        chunk = stack[start : start + CHUNK]
        name = f"crops_{start // CHUNK:04d}.npz"
        _write_npz(dest / name, **split_bytes(chunk), ranks=np.array([r["rank"] for r in rows[start : start + CHUNK]]))
        files.append({"file": name, "first_rank": start + 1, "n": len(chunk), "sha256": sha256(dest / name)})
    ov = strip.overview
    _write_npz(dest / "overview.npz", **split_bytes(ov.data))
    index = {**meta, "observation_id": strip.label.observation_id, "scale_m": strip.label.scale_m,
             "crop_size_px": size, "n_crops": len(rows), "block_reads": reads, "chunks": files,
             "overview_sha256": sha256(dest / "overview.npz"), "rows": rows}
    tmp = dest / "index.json.part"
    tmp.write_text(json.dumps(index))
    tmp.replace(dest / "index.json")
    return index


def write_window(path: Path, data: np.ndarray, row0: int, col0: int) -> None:
    _write_npz(path, **split_bytes(data), row0=np.array(row0), col0=np.array(col0))


def read_window(path: Path) -> Window:
    with np.load(path) as z:
        data = join_bytes(z["low"], z["high"])
        return Window(int(z["row0"]), int(z["col0"]), data, valid_mask(data))


def copy_label(strip_jp2: Path, labels_dir: Path) -> Path:
    labels_dir.mkdir(parents=True, exist_ok=True)
    src = Path(strip_jp2).with_suffix(".LBL")
    dst = labels_dir / src.name
    shutil.copyfile(src, dst)
    return dst


@dataclass
class ExportedStrip:
    """A strip after its JP2 is gone: the label, the overview and the crops. Takes the place of
    ``landers.strip.Strip`` in ``landers.persist.map_to_b`` and ``landers.search.persistence.look_up``."""

    root: Path  # the export root, holding labels/ and strips/
    observation_id: str

    @cached_property
    def label(self) -> StripLabel:
        return StripLabel.read(self.root / "labels" / f"{self.observation_id}_RED.LBL")

    @cached_property
    def index(self) -> dict:
        return json.loads((self.root / "strips" / self.observation_id / "index.json").read_text())

    @property
    def shape(self) -> tuple[int, int]:
        return self.label.lines, self.label.samples

    @cached_property
    def overview(self) -> Window:
        with np.load(self.root / "strips" / self.observation_id / "overview.npz") as z:
            data = join_bytes(z["low"], z["high"])
        return Window(0, 0, data, valid_mask(data))

    @property
    def overview_step(self) -> int:
        return 2**OVERVIEW_LEVEL

    def crop(self, rank: int) -> np.ndarray:
        """The raw crop of the candidate at ``rank`` (1 is the best)."""
        k = (rank - 1) // CHUNK
        with np.load(self.root / "strips" / self.observation_id / f"crops_{k:04d}.npz") as z:
            i = (rank - 1) - k * CHUNK
            return join_bytes(z["low"][i], z["high"][i])


class WindowStrip:
    """Enough of a strip for ``landers.transplant.cut_piece`` to run from an exported window."""

    def __init__(self, label, win: Window):
        self.label, self.win = label, win

    def read(self, r0, r1, c0, c1) -> Window:
        w = self.win
        i0, j0 = r0 - w.row0, c0 - w.col0
        if i0 < 0 or j0 < 0 or r1 - w.row0 > w.shape[0] or c1 - w.col0 > w.shape[1]:
            raise ValueError("outside the exported window")
        data = w.data[i0 : r1 - w.row0, j0 : c1 - w.col0]
        return Window(r0, c0, data, w.valid[i0 : r1 - w.row0, j0 : c1 - w.col0])


def strip_on_disk(observation_id: str) -> Path | None:
    return config.find_strip(observation_id)

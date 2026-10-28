"""Write a PNG crop of a control site so a person can find the hardware and record pixel positions.

    uv run scripts/crop_site.py viking1                 # 4096 px at the published position, shown 4x reduced
    uv run scripts/crop_site.py viking1 --size 512      # full resolution, 512 px
    uv run scripts/crop_site.py viking1 --center 41234,15210 --size 512

The grid labels are PDS line and sample (1-based), which is what controls/tuning.json records. Sites in the
heldout and final_exam groups are refused unless --heldout-run is given by the person running that evaluation.
Output goes to out/crops/ (never committed) with the NASA/JPL/University of Arizona credit line.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config, geo  # noqa: E402
from landers.strip import Strip  # noqa: E402

CREDIT = "NASA/JPL/University of Arizona"


def to_uint8(data: np.ndarray, valid: np.ndarray) -> np.ndarray:
    if valid.sum() < 100:
        return np.zeros(data.shape, np.uint8)
    lo, hi = np.percentile(data[valid], [0.5, 99.5])
    out = np.clip((data.astype(np.float32) - lo) / max(hi - lo, 1.0), 0, 1)
    out[~valid] = 0
    return (out * 255).astype(np.uint8)


def block_reduce(a: np.ndarray, n: int) -> np.ndarray:
    if n == 1:
        return a
    h, w = (a.shape[0] // n) * n, (a.shape[1] // n) * n
    return a[:h, :w].reshape(h // n, n, w // n, n).mean(axis=(1, 3))


def render(strip: Strip, row: float, col: float, size: int, reduce: int, out: Path, title: str) -> Path:
    w = strip.read_centered(row, col, size)
    img8 = to_uint8(
        block_reduce(w.data.astype(np.float32), reduce), block_reduce(w.valid.astype(np.float32), reduce) > 0.5
    )
    im = Image.fromarray(img8).convert("RGB")
    d = ImageDraw.Draw(im)
    grid = max(64, (size // reduce) // 8)
    for k in range(0, im.width, grid):
        d.line([(k, 0), (k, im.height)], fill=(255, 200, 0), width=1)
        d.text((k + 2, 2), f"s{w.col0 + k * reduce + 1}", fill=(255, 200, 0))
    for k in range(0, im.height, grid):
        d.line([(0, k), (im.width, k)], fill=(255, 200, 0), width=1)
        d.text((2, k + 2), f"l{w.row0 + k * reduce + 1}", fill=(255, 200, 0))
    cx, cy = im.width // 2, im.height // 2
    d.line([(cx - 20, cy), (cx + 20, cy)], fill=(0, 255, 255), width=1)
    d.line([(cx, cy - 20), (cx, cy + 20)], fill=(0, 255, 255), width=1)
    footer = Image.new("RGB", (im.width, 36), (0, 0, 0))
    fd = ImageDraw.Draw(footer)
    fd.text((4, 2), title, fill=(255, 255, 255))
    fd.text(
        (4, 18),
        f"Credit: {CREDIT}. {strip.label.scale_m * reduce:.2f} m/px shown; grid every {grid * reduce} px.",
        fill=(200, 200, 200),
    )
    canvas = Image.new("RGB", (im.width, im.height + footer.height))
    canvas.paste(im, (0, 0))
    canvas.paste(footer, (0, im.height))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site")
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--size", type=int, default=4096, help="window size in image pixels")
    ap.add_argument("--reduce", type=int, default=None, help="block-mean factor; default keeps the output near 1024 px")
    ap.add_argument("--center", default=None, help="LINE,SAMPLE (PDS, 1-based) instead of the published position")
    ap.add_argument("--strip", default=None, help="one observation id of the site (default: all on disk)")
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out" / "crops"))
    ap.add_argument("--heldout-run", action="store_true", help="a person is running the held-out evaluation")
    a = ap.parse_args(argv)

    sites = {s["name"]: s for s in json.loads(Path(a.sites).read_text())["sites"]}
    if a.site not in sites:
        print(f"unknown site {a.site!r}; known: {', '.join(sites)}", file=sys.stderr)
        return 2
    site = sites[a.site]
    if site["group"] in ("heldout", "final_exam") and not a.heldout_run:
        print(f"{a.site} is in the {site['group']} group: refused without --heldout-run", file=sys.stderr)
        return 3
    reduce = a.reduce or max(1, a.size // 1024)
    wrote = 0
    for sid in site["strips"]:
        if a.strip and sid != a.strip:
            continue
        if config.find_strip(sid) is None:
            print(f"{sid}: not on disk, skipped")
            continue
        strip = Strip.open(sid)
        if a.center:
            line, sample = (float(x) for x in a.center.split(","))
            row, col = line - 1, sample - 1
            how = "given centre"
        else:
            row, col = (float(x) for x in geo.latlon_to_rowcol(strip.label, site["lat"], site["lon_e"]))
            how = "published position (about 1 km precision)"
        if not (0 <= row < strip.shape[0] and 0 <= col < strip.shape[1]):
            print(f"{sid}: centre line {row + 1:.0f} sample {col + 1:.0f} is outside the image {strip.shape}")
            continue
        centre = f"centre line {row + 1:.0f} sample {col + 1:.0f}"
        title = f"{a.site} {sid}  {centre}  ({how})  incidence {strip.label.incidence_deg:.1f} deg"
        out = Path(a.out) / f"{a.site}_{sid}_{a.size}px_r{reduce}.png"
        render(strip, row, col, a.size, reduce, out, title)
        print(f"{sid}: wrote {out}  centre line {row + 1:.1f} sample {col + 1:.1f}")
        wrote += 1
    return 0 if wrote else 1


if __name__ == "__main__":
    sys.exit(main())

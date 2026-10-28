"""Numbered full-resolution grids around every refined piece position, for filling the answer key.

    uv run scripts/cut_grids.py                      # all tuning sites, 1.5 km, 512 px tiles
    uv run scripts/cut_grids.py --site phoenix --grid-m 1000

For each entry of ``pieces_refined`` in controls/sites.json that has a position, and each strip listed for
that site (by observation id, so strips in the same folder that the sites file does not name stay out),
writes out/grids/<site>/<piece>/<strip id>/ with tile_NNN.png and index.png. Entries without a position
are listed and skipped. Sealed sites are refused.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from crop_site import render_grid  # noqa: E402

from landers import config, geo  # noqa: E402
from landers.strip import Strip  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--site", action="append", default=[])
    ap.add_argument("--grid-m", type=float, default=1500.0)
    ap.add_argument("--tile", type=int, default=512)
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out" / "grids"))
    a = ap.parse_args(argv)

    sites = json.loads(Path(a.sites).read_text())["sites"]
    skipped, written = [], []
    strips: dict[str, Strip] = {}
    for site in sites:
        name = site["name"]
        if a.site and name not in a.site:
            continue
        if site["group"] in ("heldout", "final_exam"):
            continue
        for piece in site.get("pieces_refined", []):
            if piece.get("lat") is None or piece.get("lon_e") is None:
                skipped.append(f"{name}/{piece['piece']}: no refined position ({piece.get('basis', '')[:60]})")
                continue
            for sid in site["strips"]:
                if sid not in strips:
                    if config.find_strip(sid) is None:
                        skipped.append(f"{name}/{piece['piece']}/{sid}: strip not on disk")
                        continue
                    strips[sid] = Strip.open(sid)
                strip = strips[sid]
                row, col = (float(x) for x in geo.latlon_to_rowcol(strip.label, piece["lat"], piece["lon_e"]))
                if not (0 <= row < strip.shape[0] and 0 <= col < strip.shape[1]):
                    skipped.append(f"{name}/{piece['piece']}/{sid}: refined position outside the image")
                    continue
                out_dir = Path(a.out) / name / piece["piece"] / sid
                precision = piece.get("precision_m")
                title = (
                    f"{name} / {piece['piece']} / {sid}  centre line {row + 1:.0f} sample {col + 1:.0f}  "
                    f"(refined, precision {precision} m)  incidence {strip.label.incidence_deg:.1f} deg"
                )
                k = render_grid(strip, row, col, a.grid_m, a.tile, out_dir, title)
                written.append(
                    f"{name}/{piece['piece']}/{sid}: {k} tiles, centre line {row + 1:.0f} sample {col + 1:.0f}"
                )
                print(written[-1], flush=True)
    summary = {"grid_m": a.grid_m, "tile": a.tile, "written": written, "skipped": skipped}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"\n{len(written)} grids written, {len(skipped)} skipped:")
    for s in skipped:
        print(f"  {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Contact sheets and a suggestions file for filling controls/tuning.json.

    uv run scripts/contact_sheets.py out/baseline_v1/candidates_baseline_v1.json --out out/baseline_v1/sheets
    uv run scripts/contact_sheets.py <candidates.json> --site viking1 --radius-m 1500 --top 50

For every tuning piece: the top candidates within --radius-m of its refined position (controls/sites.json
pieces_refined; the site's published position when the piece has none), one sheet per piece per strip, and
suggestions.json / suggestions.md listing PDS line and sample so a person can copy the right one into
controls/tuning.json. This never writes under controls/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config, geo, sheets  # noqa: E402
from landers.strip import Strip  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--key", default=str(config.REPO_ROOT / "controls" / "tuning.json"), help="which pieces to list")
    ap.add_argument("--site", action="append", default=[])
    ap.add_argument("--radius-m", type=float, default=1500.0)
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--thumb-px", type=int, default=96)
    ap.add_argument("--out", default=None, help="default: <candidates dir>/sheets")
    a = ap.parse_args(argv)

    run = json.loads(Path(a.candidates).read_text())
    strips = run["strips"]
    sites = {s["name"]: s for s in json.loads(Path(a.sites).read_text())["sites"]}
    key = json.loads(Path(a.key).read_text())
    out_dir = Path(a.out) if a.out else Path(a.candidates).parent / "sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    suggestions = {
        "candidates_file": str(a.candidates),
        "git_commit": run.get("git_commit"),
        "radius_m": a.radius_m,
        "top": a.top,
        "sites": [],
    }
    md = [
        "# Suggestions for the answer key\n",
        f"From `{a.candidates}` (commit {run.get('git_commit')}), top {a.top} within {a.radius_m:.0f} m.",
        "Line and sample are PDS 1-based, ready for controls/tuning.json. Nothing here is a claim; a person decides.\n",
    ]
    opened: dict[str, Strip] = {}
    for ks in key["sites"]:
        name = ks["name"]
        if a.site and name not in a.site:
            continue
        site = sites[name]
        if site["group"] != "tuning":
            continue
        entry = {"site": name, "pieces": []}
        md.append(f"\n## {name}\n")
        for piece in [p["piece"] for p in ks["pieces"]]:
            lat, lon, precision, how = sheets.anchor_for(site, piece)
            pe = {
                "piece": piece,
                "anchor": {"lat": lat, "lon_e": lon, "precision_m": precision, "how": how},
                "strips": [],
            }
            md.append(f"### {piece}  (anchor {lat:.5f}, {lon:.5f}; {how}; precision {precision:.0f} m)\n")
            for sid in site["strips"]:
                if sid not in strips:
                    md.append(f"- {sid}: not in this run\n")
                    continue
                if sid not in opened:
                    if config.find_strip(sid) is None:
                        md.append(f"- {sid}: not on disk\n")
                        continue
                    opened[sid] = Strip.open(sid)
                strip = opened[sid]
                row0, col0 = (float(x) for x in geo.latlon_to_rowcol(strip.label, lat, lon))
                picks = sheets.select(strips[sid], strip.label.scale_m, row0, col0, a.radius_m, a.top)
                anchor = f"anchor line {row0 + 1:.0f} sample {col0 + 1:.0f} ({how}, {precision:.0f} m)"
                title = f"{name} / {piece} / {sid}  {anchor}  top {len(picks)} within {a.radius_m:.0f} m"
                png = out_dir / f"{name}_{piece}_{sid}.png"
                if picks:
                    thumbs = sheets.thumbnails(strip, picks, a.thumb_px)
                    sheets.render_sheet(strip, picks, thumbs, title, png)
                pe["strips"].append(
                    {
                        "strip": sid,
                        "anchor_line": round(row0 + 1, 1),
                        "anchor_sample": round(col0 + 1, 1),
                        "sheet": png.name if picks else None,
                        "picks": [
                            {
                                "rank": p.rank,
                                "line": round(p.row + 1, 1),
                                "sample": round(p.col + 1, 1),
                                "score": round(p.score, 3),
                                "branch": p.branch,
                                "distance_m": round(p.distance_m),
                                "area_px": p.area_px,
                                **({"also": p.extra["also"]} if "also" in p.extra else {}),
                            }
                            for p in picks
                        ],
                    }
                )
                md.append(
                    f"- {sid}: anchor line {row0 + 1:.0f} sample {col0 + 1:.0f}; {len(picks)} candidates; "
                    f"sheet `{png.name if picks else '-'}`\n"
                )
                if picks:
                    md.append("  | # | line | sample | score | branch | dist m |\n  |---|---|---|---|---|---|\n")
                    for p in picks[:10]:
                        md.append(
                            f"  | {p.rank} | {p.row + 1:.0f} | {p.col + 1:.0f} | {p.score:.2f} | {p.branch} "
                            f"| {p.distance_m:.0f} |\n"
                        )
                print(f"{name}/{piece}/{sid}: {len(picks)} candidates -> {png.name if picks else 'no sheet'}")
            entry["pieces"].append(pe)
        suggestions["sites"].append(entry)
    (out_dir / "suggestions.json").write_text(json.dumps(suggestions, indent=1))
    (out_dir / "suggestions.md").write_text("".join(md))
    print(f"written: {out_dir / 'suggestions.json'}, {out_dir / 'suggestions.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

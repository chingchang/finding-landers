"""Contact sheets and a suggestions file for filling controls/tuning.json.

    uv run scripts/contact_sheets.py out/baseline_v1/candidates_baseline_v1.json --out out/baseline_v1/sheets
    uv run scripts/contact_sheets.py <candidates.json> --site viking1 --radius-m 1500 --top 50
    uv run scripts/contact_sheets.py <candidates.json> --strip-centre schiaparelli --radius-for schiaparelli=3000

For every tuning piece: the candidates within --radius-m of its anchor (controls/sites.json pieces_refined;
the site's published position when the piece has none; the strip's own footprint centre for sites named
with --strip-centre, whose published position is rougher than the strip's pointing), ranked two ways. One
sheet of thumbnails holds the top --top by calibrated score, a second the top --top by the two-sided
shadow test from the label's sun azimuth (landers.sheets), one overview map carries both sets, and
suggestions.json / suggestions.md list PDS line and sample so a person can copy the right one into
controls/tuning.json. All thumbnails of a piece and strip share one brightness stretch. Each pick also
names the tile of the scripts/cut_grids.py grid (same --grid-m and --tile, always around the refined
position) it falls in, or none when it lies outside that square. This never writes under controls/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config, geo, sheets  # noqa: E402
from landers.strip import Strip  # noqa: E402


def pick_json(p: sheets.Pick, grid: sheets.GridLayout) -> dict:
    return {
        "rank": p.rank,
        "shadow_rank": p.shadow_rank,
        "line": round(p.row + 1, 1),
        "sample": round(p.col + 1, 1),
        "score": round(p.score, 3),
        "branch": p.branch,
        "distance_m": round(p.distance_m),
        "area_px": p.area_px,
        "grid_tile": grid.tile_of(p.row, p.col),
        "shadow": p.shadow.to_json() if p.shadow is not None else None,
        **({"also": p.extra["also"]} if "also" in p.extra else {}),
    }


def table(picks: list[sheets.Pick], grid: sheets.GridLayout, n: int = 10) -> list[str]:
    out = [
        "  | # | S | line | sample | score | shadow | branch | dist m | grid |\n",
        "  |---|---|---|---|---|---|---|---|---|\n",
    ]
    for p in picks[:n]:
        g = grid.tile_of(p.row, p.col)
        s = f"{p.shadow.score:+.1f}" if p.shadow is not None else "n/a"
        sr = p.shadow_rank if p.shadow_rank is not None else "-"
        out.append(
            f"  | {p.rank} | {sr} | {p.row + 1:.0f} | {p.col + 1:.0f} | {p.score:.2f} | {s} | {p.branch} "
            f"| {p.distance_m:.0f} | {g if g is not None else '-'} |\n"
        )
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--key", default=str(config.REPO_ROOT / "controls" / "tuning.json"), help="which pieces to list")
    ap.add_argument("--site", action="append", default=[])
    ap.add_argument("--radius-m", type=float, default=1500.0)
    ap.add_argument("--radius-for", action="append", default=[], metavar="SITE=M", help="radius for one site")
    ap.add_argument(
        "--strip-centre",
        action="append",
        default=[],
        metavar="SITE",
        help="anchor every piece of SITE at each strip's own centre",
    )
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--thumb-px", type=int, default=128, help="thumbnail side in image px (32 m at 25 cm/px)")
    ap.add_argument("--grid-m", type=float, default=1500.0, help="span of the cut_grids.py grid, for tile numbers")
    ap.add_argument("--tile", type=int, default=512, help="tile size of the cut_grids.py grid")
    ap.add_argument("--no-map", action="store_true", help="skip the overview maps (about 10 s each)")
    ap.add_argument(
        "--no-shadow", action="store_true", help="skip the shadow test (one full-resolution pass per strip)"
    )
    ap.add_argument("--out", default=None, help="default: <candidates dir>/sheets")
    a = ap.parse_args(argv)

    radius_for = {}
    for item in a.radius_for:
        name, _, m = item.partition("=")
        radius_for[name] = float(m)
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
        "radius_for": radius_for,
        "strip_centre_sites": a.strip_centre,
        "top": a.top,
        "thumb_px": a.thumb_px,
        "grid": {"grid_m": a.grid_m, "tile": a.tile},
        "shadow_test": None
        if a.no_shadow
        else {
            "score": "min(z_centre, -z_anti) + min(0, z_sun)",
            "max_height_m": sheets.SHADOW_MAX_HEIGHT_M,
            "min_incidence_deg": sheets.SHADOW_MIN_INCIDENCE_DEG,
            "object_radius_px": list(sheets.OBJECT_RADIUS_PX),
        },
        "stretch_percentiles": list(sheets.STRETCH_PERCENTILES),
        "sites": [],
    }
    md = [
        "# Suggestions for the answer key\n\n",
        f"From `{a.candidates}` (commit {run.get('git_commit')}), top {a.top} within {a.radius_m:.0f} m"
        + "".join(f"; {k} {v:.0f} m" for k, v in radius_for.items())
        + (f"; anchored at the strip centre for {', '.join(a.strip_centre)}" if a.strip_centre else "")
        + ".\n",
        "Line and sample are PDS 1-based, ready for controls/tuning.json. Nothing here is a claim; a person decides.\n",
        "`#` is the rank by calibrated score, `S` the rank by the two-sided shadow test (bright, dark on the anti-sun "
        "side, not dark on the sun side; `shadow` is its score), each over every candidate in the area.\n",
        f"`grid` is the tile number in the {a.grid_m:.0f} m / {a.tile} px grid of scripts/cut_grids.py "
        "for the same piece and strip (- when outside it).\n",
    ]
    opened: dict[str, Strip] = {}
    centres: dict[str, tuple[float, float]] = {}

    def strip_for(sid: str) -> Strip | None:
        if sid not in opened:
            if config.find_strip(sid) is None:
                return None
            opened[sid] = Strip.open(sid)
        return opened[sid]

    def anchor(site: dict, piece: str, strip: Strip):
        """(row, col, precision_m, how) of the search anchor, and (row, col) of the grid centre."""
        lat, lon, precision, how = sheets.anchor_for(site, piece)
        grow, gcol = (float(x) for x in geo.latlon_to_rowcol(strip.label, lat, lon))
        if site["name"] in a.strip_centre:
            sid = strip.label.observation_id
            if sid not in centres:
                centres[sid] = sheets.strip_centre(strip)
            r, c = centres[sid]
            return r, c, precision, "strip centre", grow, gcol
        return grow, gcol, precision, how, grow, gcol

    for ks in key["sites"]:
        name = ks["name"]
        if a.site and name not in a.site:
            continue
        site = sites[name]
        if site["group"] != "tuning":
            continue
        radius = radius_for.get(name, a.radius_m)
        pieces = [p["piece"] for p in ks["pieces"]]
        # one shadow pass per strip over the union of every piece's area
        shadows: dict[str, dict[int, sheets.ShadowTest | None]] = {}
        for sid in site["strips"]:
            strip = strip_for(sid) if sid in strips else None
            if strip is None or a.no_shadow:
                continue
            need: set[int] = set()
            for piece in pieces:
                r, c, *_ = anchor(site, piece, strip)
                if 0 <= r < strip.shape[0] and 0 <= c < strip.shape[1]:
                    need.update(i for i, _ in sheets.within(strips[sid], strip.label.scale_m, r, c, radius))
            t0 = time.time()
            shadows[sid] = sheets.shadow_tests(strip, strips[sid]["candidates"], sorted(need), a.thumb_px)
            print(f"{name}/{sid}: shadow test on {len(need)} candidates in {time.time() - t0:.0f} s", flush=True)
        entry = {"site": name, "radius_m": radius, "pieces": []}
        md.append(f"\n## {name}\n")
        for piece in pieces:
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
                strip = strip_for(sid)
                if strip is None:
                    md.append(f"- {sid}: not on disk\n")
                    continue
                row0, col0, precision, how, grow, gcol = anchor(site, piece, strip)
                if not (0 <= row0 < strip.shape[0] and 0 <= col0 < strip.shape[1]):
                    md.append(f"- {sid}: anchor outside the image\n")
                    pe["strips"].append({"strip": sid, "outside_image": True, "picks": []})
                    continue
                inside = sheets.within(strips[sid], strip.label.scale_m, row0, col0, radius)
                picks, shadow_picks = sheets.rank_picks(strips[sid], inside, a.top, shadows.get(sid))
                grid = sheets.grid_layout(grow, gcol, strip.label.scale_m, a.grid_m, a.tile)
                anchor_txt = f"anchor line {row0 + 1:.0f} sample {col0 + 1:.0f} ({how}, {precision:.0f} m)"
                title = (
                    f"{name} / {piece} / {sid}  {anchor_txt}  top {len(picks)} of {len(inside)} within {radius:.0f} m"
                )
                png = out_dir / f"{name}_{piece}_{sid}.png"
                shadow_png = out_dir / f"{name}_{piece}_{sid}_shadow.png"
                map_png = out_dir / f"{name}_{piece}_{sid}_map.png"
                limits = None
                if picks:
                    # one read of every thumbnail of both sheets, one stretch over all of them
                    both = picks + [p for p in shadow_picks if p.rank > a.top]
                    cr = dict(
                        zip(
                            [p.rank for p in both],
                            sheets.crops(strip, [(p.row, p.col) for p in both], a.thumb_px),
                            strict=True,
                        )
                    )
                    limits = sheets.stretch_limits(list(cr.values()))
                    thumbs = [sheets.apply_stretch(*cr[p.rank], limits) for p in picks]
                    sheets.render_sheet(strip, picks, thumbs, title + "  by score", png, limits=limits)
                    if shadow_picks:
                        thumbs = [sheets.apply_stretch(*cr[p.rank], limits) for p in shadow_picks]
                        sheets.render_sheet(
                            strip,
                            shadow_picks,
                            thumbs,
                            title + "  by shadow test",
                            shadow_png,
                            order="shadow",
                            limits=limits,
                        )
                if not a.no_map:
                    sheets.render_map(
                        strip, row0, col0, radius, precision, picks, grid, title, map_png, shadow_picks=shadow_picks
                    )
                pe["strips"].append(
                    {
                        "strip": sid,
                        "anchor_line": round(row0 + 1, 1),
                        "anchor_sample": round(col0 + 1, 1),
                        "anchor_how": how,
                        "grid_centre_line": round(grow + 1, 1),
                        "grid_centre_sample": round(gcol + 1, 1),
                        "radius_m": radius,
                        "sheet": png.name if picks else None,
                        "shadow_sheet": shadow_png.name if shadow_picks else None,
                        "map": None if a.no_map else map_png.name,
                        "stretch_dn": list(limits) if limits else None,
                        "candidates_in_strip": len(strips[sid].get("candidates", [])),
                        "within_radius": len(inside),
                        "shadow_tested": sum(1 for i, _ in inside if shadows.get(sid, {}).get(i) is not None),
                        "summary": sheets.summarise(picks, grid),
                        "shadow_summary": sheets.summarise(shadow_picks, grid),
                        "picks": [pick_json(p, grid) for p in picks],
                        "shadow_picks": [pick_json(p, grid) for p in shadow_picks],
                    }
                )
                files = (
                    f"sheet `{png.name if picks else '-'}`; shadow sheet `{shadow_png.name if shadow_picks else '-'}`; "
                    f"map `{'-' if a.no_map else map_png.name}`"
                )
                md.append(
                    f"- {sid}: anchor line {row0 + 1:.0f} sample {col0 + 1:.0f} ({how}); top {len(picks)} of "
                    f"{len(inside)} within {radius:.0f} m; {files}\n"
                )
                if picks:
                    md.append("  By score:\n\n")
                    md.extend(table(picks, grid))
                if shadow_picks:
                    md.append("\n  By shadow test:\n\n")
                    md.extend(table(shadow_picks, grid))
                print(
                    f"{name}/{piece}/{sid}: {len(picks)} by score, {len(shadow_picks)} by shadow -> "
                    f"{png.name if picks else 'no sheet'}",
                    flush=True,
                )
            entry["pieces"].append(pe)
        suggestions["sites"].append(entry)
    (out_dir / "suggestions.json").write_text(json.dumps(suggestions, indent=1))
    (out_dir / "suggestions.md").write_text("".join(md))
    print(f"written: {out_dir / 'suggestions.json'}, {out_dir / 'suggestions.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

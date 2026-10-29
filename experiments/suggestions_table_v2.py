"""Scratch: one markdown row per piece and strip from a second-pass suggestions.json (two rankings)."""

import json
import sys

sug = json.load(open(sys.argv[1]))
print(
    "| site | piece | strip | within | shadow tested | by score: branches, top | by shadow: branches, top, "
    "best (#, dist) | in both top 50 | stretch DN |"
)
print("|---|---|---|---|---|---|---|---|---|")
for site in sug["sites"]:
    for piece in site["pieces"]:
        for st in piece["strips"]:
            s, sh = st.get("summary", {}), st.get("shadow_summary", {})
            head = f"| {site['site']} | {piece['piece']} | {st['strip']} | {st.get('within_radius', '-')} |"
            if not s.get("n"):
                print(f"{head} - | - | - | - | - |")
                continue
            br = " ".join(f"{k} {v}" for k, v in s["branches"].items())
            sbr = " ".join(f"{k} {v}" for k, v in sh.get("branches", {}).items())
            top_sh = st["shadow_picks"][0] if st["shadow_picks"] else None
            best = f"{top_sh['shadow']['score']:+.1f} (#{top_sh['rank']}, {top_sh['distance_m']} m)" if top_sh else "-"
            both = len({p["rank"] for p in st["picks"]} & {p["rank"] for p in st["shadow_picks"]})
            lo, hi = st["stretch_dn"]
            print(
                f"{head} {st['shadow_tested']} | {br}, {s['score_top']:.2f} | {sbr}, {best} | {both} | "
                f"{lo:.0f}..{hi:.0f} |"
            )

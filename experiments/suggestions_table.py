"""Scratch: one markdown row per piece and strip from a contact-sheet suggestions.json, for a report."""

import json
import sys

sug = json.load(open(sys.argv[1]))
print("| site | piece | strip | within 1.5 km | top 50 branches | score top..50th | in grid | nearest pick |")
print("|---|---|---|---|---|---|---|---|")
for site in sug["sites"]:
    for piece in site["pieces"]:
        for st in piece["strips"]:
            s = st.get("summary", {})
            head = f"| {site['site']} | {piece['piece']} | {st['strip']} | {st.get('within_radius', '-')} |"
            if not s.get("n"):
                print(f"{head} - | - | - | - |")
                continue
            br = " ".join(f"{k} {v}" for k, v in s["branches"].items())
            scores = f"{s['score_top']:.2f}..{s['score_last']:.2f}"
            print(f"{head} {br} | {scores} | {s['in_grid']} | #{s['nearest_rank']} at {s['nearest_m']} m |")

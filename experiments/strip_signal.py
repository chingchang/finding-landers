"""How much of each search strip's pixel variance is ground rather than noise.

Sensor noise is white, so a noise-only image has no correlation between pixels two apart; ground texture has. For
nine windows along each strip: remove a 32 px Gaussian background, then correlate each pixel with the one two
rows on and the one two columns on, and take the median over the windows. Output out/search/strip_signal.json,
with the same split of the injection board (transplant_t4_v3) by target strip, because a planted gain is
multiplied in whatever the state of the atmosphere over the target. Measures only; changes no list.

    uv run --env-file out/landers.env experiments/strip_signal.py
"""

import json
from pathlib import Path

import numpy as np
from scipy import ndimage

from landers.strip import Strip


def lag2(window) -> float:
    x = window.data.astype(np.float32)
    x = x - ndimage.gaussian_filter(x, 32.0)
    v = window.valid
    vals = []
    for a, b, ok in ((x[:-2, :], x[2:, :], v[:-2, :] & v[2:, :]), (x[:, :-2], x[:, 2:], v[:, :-2] & v[:, 2:])):
        vals.append(float(np.corrcoef(a[ok], b[ok])[0, 1]))
    return float(np.mean(vals))


inv = json.loads(Path("out/search/inventory.json").read_text())
rows = []
for rec in inv["strips"]:
    sid = rec["observation_id"]
    s = Strip.open(sid)
    ov = s.overview.valid
    r16, c16 = np.nonzero(ov)
    picks = np.linspace(0, len(r16) - 1, 11).astype(int)[1:-1]
    vals, stds = [], []
    for i in picks[:9]:
        w = s.read_centered(float(r16[i]) * 16, float(c16[i]) * 16, 512)
        if w.valid.mean() < 0.9:
            continue
        vals.append(lag2(w))
        stds.append(float(w.data[w.valid].std()))
    rows.append({"strip": sid, "date": rec.get("date"), "windows": len(vals), "lag2_median": round(float(np.median(vals)), 3),
                 "lag2_min": round(min(vals), 3), "lag2_max": round(max(vals), 3), "std_dn_median": round(float(np.median(stds)), 1)})
    print(rows[-1], flush=True)

t = json.loads(Path("out/transplant_t4_v3/transplant_t4_v3.json").read_text())
board: dict = {}
for p in t["placements"]:
    if p["sham"]:
        continue
    e = board.setdefault(p["target"], {"placements": 0, "found": 0, "by_kind": {}})
    e["placements"] += 1
    e["found"] += bool(p["found_at_threshold"])
    k = e["by_kind"].setdefault(p["kind"], [0, 0])
    k[0] += bool(p["found_at_threshold"])
    k[1] += 1
out = {"what": __doc__.split("\n\n")[0], "strips": rows, "injection_by_target": {"file": "out/transplant_t4_v3/transplant_t4_v3.json", "targets": board}}
Path("out/search/strip_signal.json").write_text(json.dumps(out, indent=1))
print(json.dumps(board))

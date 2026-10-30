"""Scene contrast of every search strip, from its 1/16 overview: the spread of valid DN (robust: the 5th to 95th
percentile range, and the standard deviation), to see whether the strips with almost no candidates and no
registration are low-contrast images.

    uv run --env-file out/landers.env experiments/search_strip_contrast.py
Writes out/search/strip_contrast.json.
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.strip import Strip  # noqa: E402

out = config.REPO_ROOT / "out" / "search"
inv = json.loads((out / "inventory.json").read_text())
rows = []
for s in inv["strips"]:
    st = Strip.open(s["observation_id"])
    v = st.overview.data[st.overview.valid].astype(np.float64)
    p5, p50, p95 = np.percentile(v, [5, 50, 95])
    rows.append({"observation_id": s["observation_id"], "date": s["date"], "p5": round(p5, 1), "median": round(p50, 1),
                 "p95": round(p95, 1), "p95_minus_p5": round(p95 - p5, 1), "std": round(float(v.std()), 1),
                 "relative_range": round((p95 - p5) / max(p50, 1.0), 3)})
    print(rows[-1])
(out / "strip_contrast.json").write_text(json.dumps({"what": __doc__.strip().splitlines()[0], "strips": rows}, indent=1))

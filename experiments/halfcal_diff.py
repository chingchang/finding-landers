"""Why a rerun on item 13's saved planted tile differs from its record: writes the differing detections and whether the
saved tile holds the planted samples exactly (integer samples, or rounded from floats)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rerank as rr  # noqa: E402

from landers import config  # noqa: E402
from landers.detect import DetectorConfig, detect_tile, finish_tile, load_calibration, load_shape_rules  # noqa: E402
from landers.search import export as ex  # noqa: E402

name = sys.argv[1]
t = next(x for x in rr.load(rr.EXPORT / "tiles.json")["tiles"] if x["file"] == name)
dcfg = DetectorConfig(
    calibration=str(config.REPO_ROOT / "landers/calibration_v0.json"),
    shape_rules=str(config.REPO_ROOT / "landers/shape_v3.json"),
)
cal, rules = load_calibration(dcfg), load_shape_rules(dcfg)
win = ex.read_window(rr.RUN / "tiles" / name)
rec = rr.load(rr.RUN / "tiles" / f"{name[:-4]}.json")
print("saved dtype", win.data.dtype, "all integer", bool(np.all(win.data == np.round(win.data))))
cands = finish_tile(detect_tile(win, rr.label_of(t["strip"]), dcfg), dcfg, cal, rules)
now = {(round(c.row - t["row0"], 1), round(c.col - t["col0"], 1), c.branch): round(c.score, 4) for c in cands}
was = {(d["row"], d["col"], d["branch"]): d["score"] for d in rec["detections"]}
print("now", len(now), "was", len(was), "same keys", len(now.keys() & was.keys()))
print("only now", sorted(now.keys() - was.keys())[:10])
print("only was", sorted(was.keys() - now.keys())[:10])
print("score differs", [(k, now[k], was[k]) for k in now.keys() & was.keys() if now[k] != was[k]][:10])
print(
    "order same",
    [(round(c.row - t["row0"], 1), round(c.col - t["col0"], 1), c.branch) for c in cands]
    == [(d["row"], d["col"], d["branch"]) for d in rec["detections"]],
)

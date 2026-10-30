"""Two controls on the item 13 re-ranker. Neither decides anything.

repeat: the pinned encoder on the first 100 crops of one strip against the embeddings the run saved.
shuffle: the same folds with the positives drawn at random from the training rows, as many as the real ones, per fold. If
the key board's rise came from a leak or from the proposer's score alone, shuffled labels would reach it too.

    uv run --group rerank experiments/rerank_controls.py repeat
    uv run experiments/rerank_controls.py shuffle --n 20

Output out/rerank/controls/.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rerank as rr  # noqa: E402

from landers.rerank import model as rm  # noqa: E402
from landers.search import export as ex  # noqa: E402

OUT = rr.OUT / "controls"


def repeat() -> None:
    from landers.rerank.embed import REVISION, Dino

    sites, thresholds, answers = rr.controls()
    sid = rr.strips_with_pieces(sites, thresholds, answers)[0]
    d = Dino(str(rr.OUT / "hf"))
    with np.load(rr.EXPORT / "strips" / sid / "crops_0000.npz") as z:
        stack = ex.join_bytes(z["low"], z["high"])
    new = rr.embed_rows(d, list(stack), rr.label_of(sid)).astype(np.float32)
    with np.load(rr.EMB / f"strip_{sid}.npz") as z:
        old = z["emb"][: len(new)]
    out = {"revision": REVISION, "strip": sid, "crops": len(new), "max_abs_difference": float(np.abs(new - old).max()), "identical": bool(np.array_equal(new, old))}
    rr.write_json(OUT / "repeat.json", out)
    print(out)


def shuffle(n: int) -> None:
    sites, thresholds, answers = rr.controls()
    t = rr.build_table(sites, thresholds, answers)
    tb = t["table"]
    groups = rr.site_strips(sites)
    pos = rm.is_positive(tb.source)
    rows = []
    for seed in range(n):
        rng = np.random.default_rng(seed)
        ranks: dict = {}
        for site, strips in groups.items():
            mask = rm.training_mask(tb.source, tb.site, tb.target, site, None)
            idx = np.flatnonzero(mask)
            y = np.zeros(len(idx))
            y[rng.choice(len(idx), int(pos[mask].sum()), replace=False)] = 1
            m = rm.fit(tb.emb[idx], tb.score[idx], tb.nov[idx], y, np.where(y > 0, 0.5 / y.sum(), 0.5 / (1 - y).sum()), "primary")
            held = (tb.target == "") & (tb.site == site)
            off = np.zeros(tb.n)
            off[held] = m.decision(tb.emb[held], tb.score[held], tb.nov[held])
            lists = {sid: [{**x, "score": float(off[i])} for x, i in zip(t["lists"][sid]["rows"], t["lists"][sid]["idx"], strict=True)] for sid in strips if sid in t["lists"]}
            ranks.update(rr.key_ranks(lists, {**answers, "sites": [s for s in answers["sites"] if s["name"] == site]}, thresholds))
        rows.append(rr.curve(ranks.values()))
        print(seed, rows[-1], flush=True)
    at20 = [r["20"] for r in rows]
    out = {"what": "key board with shuffled positives, all else as the primary variant", "n": n, "key_at_20": at20, "median": statistics.median(at20), "max": max(at20), "min": min(at20), "curves": rows}
    rr.write_json(OUT / "shuffle.json", out)
    print(json.dumps({k: out[k] for k in ("key_at_20", "median", "max", "min")}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["repeat", "shuffle"])
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    if a.cmd == "repeat":
        repeat()
    else:
        shuffle(a.n)

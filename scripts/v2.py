"""v2 end to end, plan item 16a. One command, on strips by observation id:

    uv run --group rerank scripts/v2.py STRIP [STRIP ...] --out out/v2/NAME [--jobs 3]
    uv run --group rerank scripts/v2.py STRIP --out out/v2/NAME --detections STRIP=out/search/candidates/FILE.json
    uv run --group rerank scripts/v2.py STRIP --out out/v2/NAME --backend real --max-usd 5 --probe 3

Writes OUT/candidates_v2.json, the list scripts/score.py and the board read, and every step's file as it lands: rerun the
same command to go on from there. Detection comes from the full strip unless --detections names an existing frozen-v1 list
for it. The model stage follows landers/v2.json; when it is on, name a backend.

This command refuses to start unless the tag frozen-v2 exists and landers/, this file, the thresholds and uv.lock are as
tagged, because a person freezes v2 before it runs on any strip. It reads no key and no index: landers/v2.py refuses them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import v2  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="+", help="observation ids")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=3, help="detector worker processes (3 at most on 8 GB)")
    ap.add_argument("--detections", nargs="*", default=[], metavar="STRIP=FILE", help="use this frozen-v1 list instead of detecting")
    ap.add_argument("--backend", choices=("fake", "dry-run", "real"), default=None, help="the model stage's backend, when landers/v2.json turns it on")
    ap.add_argument("--max-usd", type=float, default=10.0, help="this run's own limit; the ledger's cumulative cap also holds")
    ap.add_argument("--probe", type=int, default=0, help="recognition probe on the top N of each strip, recorded, stops nothing")
    a = ap.parse_args(argv)
    why = v2.frozen_check()
    if why:
        print(f"refused: {why}", file=sys.stderr)
        return 3
    cfg = v2.load_config()
    if cfg["model_stage"]["on"] and not a.backend:
        print("the model stage is on in landers/v2.json: name a --backend", file=sys.stderr)
        return 2
    detections = dict(x.split("=", 1) for x in a.detections)
    v2.run_strips(a.ids, Path(a.out), cfg=cfg, backend=a.backend, frozen=True, jobs=a.jobs, detections=detections, probe=a.probe, max_usd=a.max_usd)
    return 0


if __name__ == "__main__":
    sys.exit(main())

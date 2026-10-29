"""SAM 3.1 pass over the top candidates of one strip: a box prompt per candidate, mask measurements and
the size and shape tests.

    uv run scripts/models_sam.py out/<run>/candidates_<run>.json --strip <id> --top 20 --backend fake
    uv run scripts/models_sam.py ... --backend dry-run     # writes out/models/model_requests/, sends nothing
    uv run scripts/models_sam.py ... --backend real        # only with MODEL_API_KEY and LANDERS_REAL_CALLS=1

Writes out/models/sam_<strip>.json (candidate ids c000..., box, measurements, tests) and a manifest
out/models/manifest_<strip>.json mapping ids to pixel positions. The manifest never enters a prompt and
stays under out/. The ledger is out/models/ledger.json.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers.models import run  # noqa: E402
from landers.models.sam import SamLimits  # noqa: E402
from landers.score import load_json  # noqa: E402
from landers.strip import Strip  # noqa: E402

BACKENDS = ("fake", "dry-run", "recorded", "real")


def strip_reader(strip: Strip):
    def read(row, col, size):
        w = strip.read_centered(row, col, size)
        return w.data.astype("float32"), w.valid

    return read


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--strip", required=True)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--backend", choices=BACKENDS, default="fake")
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--out-dir", default="out/models")
    a = ap.parse_args(argv)

    data = load_json(a.candidates)
    if a.strip not in data["strips"]:
        print(f"{a.strip}: not in this run", file=sys.stderr)
        return 2
    s = data["strips"][a.strip]
    cands = run.top_candidates(s["candidates"], a.top)
    strip = Strip.open(a.strip)
    client = run.open_client(a.backend, Path(a.out_dir))
    print(f"backend {client.backend.name}; sam remaining {client.ledger.remaining('sam')}; {len(cands)} candidates")
    recs = run.sam_pass(client, strip_reader(strip), cands, strip.label.scale_m, run.SamPassConfig(size=a.size))
    out = Path(a.out_dir)
    run.write_json(
        out / f"sam_{a.strip}.json",
        {"run": data.get("run"), "backend": client.backend.name, "limits": SamLimits().__dict__, "records": recs},
    )
    run.write_json(
        out / f"manifest_{a.strip}.json",
        {
            "strip": a.strip,
            "ids": {run.candidate_id(i): {"row": c["row"], "col": c["col"]} for i, c in enumerate(cands)},
        },
    )
    found = sum(1 for r in recs if r.get("found"))
    outcomes = {}
    for r in recs:
        for t, v in r["tests"].items():
            outcomes.setdefault(t, {}).setdefault(v["outcome"], 0)
            outcomes[t][v["outcome"]] += 1
    print(f"found {found} of {len(recs)}; outcomes {outcomes}; cost so far ${client.ledger.total_cost_usd()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

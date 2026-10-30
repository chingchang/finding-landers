"""Muse Wonder on blind crops of the top candidates of one strip: the recognition probe, or three
advisory votes per candidate.

    uv run scripts/models_wonder.py <candidates.json> --strip <id> --top 3 --probe --backend fake
    uv run scripts/models_wonder.py <candidates.json> --strip <id> --top 3 --reference-strip <id2> --backend dry-run

The probe runs first and separately (plan item 9b: on two famous sites before any vote). A reference crop
of similar ground comes from a seeded valid spot of --reference-strip, labelled only "reference". Writes
out/models/probe_<strip>.json or out/models/votes_<strip>.json and the id manifest; votes carry the grade
before and after apply_votes, which can only go down.

--fewshot (off by default; plan item 9d) adds two hardware and two natural examples to every vote, from the
other sites only (landers.models.fewshot); where each example came from goes in fewshot_<strip>.json beside
the votes, under --out-dir, and never into a prompt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.models import fewshot, run  # noqa: E402
from landers.score import load_json  # noqa: E402
from landers.strip import Strip  # noqa: E402
from scripts.models_sam import BACKENDS, strip_reader  # noqa: E402


def reference_spot(strip: Strip, seed: int) -> tuple[float, float]:
    """The centre of a seeded tile with mostly valid ground, away from the strip's edges."""
    tiles = list(strip.tiles(2048, 0, min_valid_fraction=0.9))
    if not tiles:
        tiles = list(strip.tiles(2048, 0))
    r0, r1, c0, c1 = tiles[int(np.random.default_rng(seed).integers(len(tiles)))]
    return (r0 + r1) / 2.0, (c0 + c1) / 2.0


def fewshot_source(data: dict, sid: str, strip: Strip, seed: int, n_each: int = 2) -> fewshot.ExampleSource:
    """Examples for votes on ``strip``: recorded pieces and top-20 false alarms of every other site."""
    key = load_json(config.REPO_ROOT / "controls" / "tuning.json")
    thresholds = load_json(config.REPO_ROOT / "controls" / "thresholds.json")
    site = fewshot.site_of_strip(key)[sid]
    hw = fewshot.leave_site_out(fewshot.hardware_pool(key, thresholds), site)
    nat = fewshot.leave_site_out(fewshot.natural_pool(key, thresholds, data), site)
    readers, views = {}, {}
    for other in sorted({e.strip for e in hw + nat}):
        src = Strip.open(other)
        readers[other] = strip_reader(src)
        views[other] = fewshot.View(
            src.label.scale_m, src.label.sub_solar_azimuth_deg, strip.label.scale_m, strip.label.sub_solar_azimuth_deg
        )
    return fewshot.ExampleSource(hw, nat, readers, views, n_each, seed)


def drawn_record(src: fewshot.ExampleSource) -> dict:
    return {f"{run.candidate_id(i)}/{j}": [e.to_json() for e in ex] for (i, j), ex in sorted(src.drawn.items())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--strip", required=True)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--votes", type=int, default=3)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--reference-strip", default=None)
    ap.add_argument("--backend", choices=BACKENDS, default="fake")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fewshot", action="store_true", help="few-shot prompt (plan item 9d); off by default")
    ap.add_argument("--tag", default="", help="suffix for the output and manifest names (one ledger, several runs)")
    ap.add_argument("--out-dir", default="out/models")
    a = ap.parse_args(argv)

    data = load_json(a.candidates)
    if a.strip not in data["strips"]:
        print(f"{a.strip}: not in this run", file=sys.stderr)
        return 2
    cands = run.top_candidates(data["strips"][a.strip]["candidates"], a.top)
    strip = Strip.open(a.strip)
    ref = ref_at = None
    if a.reference_strip:
        rs = Strip.open(a.reference_strip)
        ref, ref_at = strip_reader(rs), reference_spot(rs, a.seed)
    client = run.open_client(a.backend, Path(a.out_dir))
    print(
        f"backend {client.backend.name}; wonder remaining {client.ledger.remaining('wonder')}; {len(cands)} candidates"
    )
    src = fewshot_source(data, a.strip, strip, a.seed) if a.fewshot else None
    recs = run.vote_pass(
        client, strip_reader(strip), cands, ref, ref_at, a.votes, seed=a.seed, probe=a.probe, examples=src
    )
    out = Path(a.out_dir)
    if src is not None:
        run.write_json(out / f"fewshot_{a.strip}{a.tag}.json", {"strip": a.strip, "examples": drawn_record(src)})
    kind = "probe" if a.probe else "votes"
    run.write_json(
        out / f"{kind}_{a.strip}{a.tag}.json",
        {"run": data.get("run"), "backend": client.backend.name, "seed": a.seed, "records": recs},
    )
    run.write_json(
        out / f"manifest_{a.strip}{a.tag}.json",
        {
            "strip": a.strip,
            "ids": {run.candidate_id(i): {"row": c["row"], "col": c["col"]} for i, c in enumerate(cands)},
        },
    )
    if a.probe:
        rec = sum(r.get("summary", {}).get("recognised", 0) for r in recs)
        print(f"probe: {rec} recognised answers over {sum(r.get('summary', {}).get('n', 0) for r in recs)} crops")
    else:
        lowered = sum(1 for r in recs if r.get("grade_after") != r.get("grade_before"))
        print(f"votes: {lowered} of {len(recs)} grades lowered")
    print(f"cost so far ${client.ledger.total_cost_usd()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

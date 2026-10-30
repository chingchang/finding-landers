"""Driver for plan item 14, the deeper model pass, on one ledger in ``--out-dir``.

    uv run experiments/deep14_run.py --reference ID --reference-for-reference ID --probe ID:3 ID:3 \
        --backend dry-run --out-dir out/deep14_dry
    uv run --env-file out/caps.env experiments/deep14_run.py ... --backend real --out-dir out/deep14
    ... --backend real --out-dir out/deep14 --billing-usd X     goes on past the pause; X is what the Billing page shows

Input: out/deep14/inputs (experiments/deep14_inputs.py). Crops come from out/export; the reference crop, one per run,
from the strip named, as in item 9c.

The stages, in order:

1. ``probe``: the recognition probe on the new crops, three views each. Recorded and reported; it stops nothing.
2. ``votes``: one vote per candidate under docs/proposals/vote-single-v1.md on the top --top of each strip, rank by rank
   across the strips, so if money runs out every strip has been voted to about the same depth. Before anything is sent,
   one vote per candidate is reserved on the ledger; no check may spend those calls.
3. ``transplant``: the same votes on the planted tiles' vote set.
4. ``review``: one Spark review per strip, of the top 20 with lowered candidates set aside. Every verdict in one turn after
   the fetches. The only check is more_votes, at most --checks per strip.

Limits. The ledger refuses a call past the model caps, past the reservation, past the cumulative dollar cap (over every run
on docs/reports/ledgers.json) and past the pause. A real run stops at --pause calls and writes CHECKPOINT.json; it goes
on only with --billing-usd, the figure a person read from the Billing page, which goes in the checkpoint file. --max-usd
stops this run's own spending.

Each record is written as it lands; a rerun skips the ids already written and sends nothing twice. A real run needs
MODEL_API_KEY and LANDERS_REAL_CALLS=1, both exported by a person.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.models import run, spark  # noqa: E402
from landers.models.ledger import CapError, PauseError  # noqa: E402
from landers.search import export as ex  # noqa: E402
from landers.strip import Strip, valid_mask  # noqa: E402
from scripts.models_sam import strip_reader  # noqa: E402
from scripts.models_wonder import reference_spot  # noqa: E402

EXPORT = config.REPO_ROOT / "out" / "export"
INPUTS = config.REPO_ROOT / "out" / "deep14" / "inputs"
SEED, CROP = 0, 320
REVIEW_TOP, REVIEW_TURNS = 20, 6
BACKENDS = ("fake", "dry-run", "real")
ITEM = "14"


def load(path) -> dict:
    return json.loads(Path(path).read_text())


def load_doc(path: Path) -> dict:
    return load(path) if path.exists() else {"records": []}


class CropBank:
    """The exported crops of one strip's top candidates, by position, read once. Answers the same window a strip would,
    out to the export's own size."""

    def __init__(self, sid: str, cands: list[dict]):
        es = ex.ExportedStrip(EXPORT, sid)
        self.by_at = {}
        wanted: dict[int, list[dict]] = {}
        for c in cands:
            wanted.setdefault((c["export_rank"] - 1) // ex.CHUNK, []).append(c)
        for k, group in sorted(wanted.items()):
            with np.load(EXPORT / "strips" / sid / f"crops_{k:04d}.npz") as z:
                stack = ex.join_bytes(z["low"], z["high"])
            for c in group:
                self.by_at[(c["row"], c["col"])] = stack[(c["export_rank"] - 1) % ex.CHUNK].copy()

    def read(self, row: float, col: float, size: int):
        return centred(self.by_at[(row, col)], size)


def centred(raw: np.ndarray, size: int):
    """A ``size`` px window on the crop's centre. Past the export is no data; a 256 px view, with its largest offset of 32
    px, stays inside the export's 320 px, so a vote from an export is the vote from the strip."""
    n = raw.shape[0]
    if size > n:
        pad = (size - n) // 2
        w = np.pad(raw, (pad, size - n - pad))
    else:
        i = (n - size) // 2
        w = raw[i : i + size, i : i + size]
    return w.astype(np.float32), valid_mask(w)


class TileBank:
    """The planted tiles of the transplant run. A crop past a tile's edge is no data, as in the re-ranker's crops."""

    def __init__(self):
        self.windows = {}

    def read_at(self, det: dict, size: int):
        from landers.rerank.crops import cut

        strip, row0, col0 = det["tile"].split(":")
        name = f"{strip}_{row0}_{col0}.npz"
        if name not in self.windows:
            self.windows[name] = ex.read_window(config.REPO_ROOT / "out" / "rerank" / "t10" / "tiles" / name)
        return centred(cut(self.windows[name].data, 0, 0, det["row"], det["col"], size), size)


def checkpoint(out: Path, client, note: str) -> None:
    path = out / "CHECKPOINT.json"
    doc = load(path) if path.exists() else {"events": []}
    doc["events"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "note": note, "calls_this_run": client.ledger.units_total(),
                          "this_run_usd": client.ledger.total_cost_usd(), "other_runs_usd": client.ledger.prior_usd,
                          "all_runs_usd": round(client.ledger.prior_usd + client.ledger.total_cost_usd(), 4)})
    run.write_json(path, doc)


class Stop(Exception):
    pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", required=True, choices=BACKENDS)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--reference", required=True, help="strip the reference crop comes from")
    ap.add_argument("--reference-for-reference", required=True, help="the reference for that strip itself")
    ap.add_argument("--probe", nargs="*", default=[], metavar="STRIP:N")
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--checks", type=int, default=3, help="more_votes checks per review")
    ap.add_argument("--pause", type=int, default=100, help="calls at which a real run stops for the bill to be checked")
    ap.add_argument("--billing-usd", type=float, default=None, help="the figure a person read from the Billing page")
    ap.add_argument("--max-usd", type=float, default=36.0, help="this run's own limit")
    ap.add_argument("--strips", nargs="*", default=None, help="default: every strip of the combined list")
    a = ap.parse_args(argv)

    data = load(INPUTS / "candidates_combined.json")
    strips = a.strips or list(data["strips"])
    thresholds = load(config.REPO_ROOT / "controls" / "thresholds.json")
    out = Path(a.out_dir)
    client = run.open_client(a.backend, out, item=ITEM)
    led = client.ledger
    print(f"backend {client.backend.name}; other runs {led.prior_usd} USD; this run {led.total_cost_usd()} USD; cap {led.total_cap_usd}")
    if a.backend == "real":
        if a.billing_usd is not None:
            checkpoint(out, client, f"a person read {a.billing_usd} USD on the Billing page; going on")
        elif led.units_total() >= a.pause or (out / "CHECKPOINT.json").exists():
            print("already at the pause; give --billing-usd with the figure a person read", file=sys.stderr)
            return 3
        else:
            led.pause_at_units = a.pause
    bank = {sid: CropBank(sid, data["strips"][sid]["candidates"][: a.top]) for sid in strips}

    # the reference crops, read once, the same pixels whatever the rank
    refs, ref_views = {}, {}
    for ref_id in {a.reference, a.reference_for_reference}:
        rs = Strip.open(ref_id)
        reader, at = strip_reader(rs), reference_spot(rs, SEED)
        data_r, valid_r = reader(at[0], at[1], CROP)
        refs[ref_id] = (data_r, valid_r, data_r.shape[0] / 2.0, data_r.shape[1] / 2.0)
        ref_views[ref_id] = (reader, at)

    def ref_id_for(sid):
        return a.reference_for_reference if sid == a.reference else a.reference

    def ref_for(sid):
        return refs[ref_id_for(sid)]

    def keep(path, doc, rec):
        doc["records"].append(rec)
        run.write_json(path, doc)

    def guard():
        if led.total_cost_usd() >= a.max_usd:
            raise Stop(f"this run reached its limit of {a.max_usd} USD")

    voted = {sid: load_doc(out / f"votes_{sid}.json") | {"strip": sid, "backend": client.backend.name, "seed": SEED} for sid in strips}
    done = {sid: {r["id"] for r in voted[sid]["records"]} for sid in strips}
    left = sum(1 for sid in strips for i in range(len(data["strips"][sid]["candidates"][: a.top])) if run.candidate_id(i) not in done[sid])
    tp_doc = load_doc(out / "votes_transplant.json") | {"backend": client.backend.name, "seed": SEED}
    tp_done = {r["detection"] for r in tp_doc["records"]}
    tp_set = [d for d in load(INPUTS / "transplant_votes.json")["detections"] if d not in tp_done]

    try:
        led.reserve("wonder", left + len(tp_set))
        print(f"candidates to vote on {left}; transplant detections {len(tp_set)}; reserved {left + len(tp_set)} Wonder calls of {led.remaining('wonder')} left")

        # 1. the recognition probe
        for spec in a.probe:
            sid, n = spec.split(":")
            path = out / f"probe_{sid}.json"
            if path.exists():
                continue
            cands = data["strips"][sid]["candidates"][: int(n)]
            reader, at = ref_views[ref_id_for(sid)]
            recs = run.vote_pass(client, bank[sid].read, cands, reader, at, 3, seed=SEED, probe=True, saturated_bright=True)
            if any("not_run" in r for r in recs):
                raise CapError(next(r["not_run"] for r in recs if "not_run" in r))
            run.write_json(path, {"strip": sid, "backend": client.backend.name, "seed": SEED, "records": recs})

        # 2. votes, rank by rank across the strips
        with led.spending_reserved():
            for i in range(a.top):
                for sid in strips:
                    cands = data["strips"][sid]["candidates"]
                    cid = run.candidate_id(i)
                    if i >= len(cands) or cid in done[sid]:
                        continue
                    guard()
                    rec = run.single_vote(client, bank[sid].read, cands[i], i, ref_for(sid), seed=SEED)
                    keep(out / f"votes_{sid}.json", voted[sid], rec)
                    done[sid].add(cid)
                if (i + 1) % 10 == 0:
                    print(f"votes through rank {i + 1}: {led.total_cost_usd()} USD, {led.units_total()} calls", flush=True)

            # 3. the planted tiles
            dets = load(INPUTS / "transplant_detections.json")["detections"]
            tiles = TileBank()
            for d in tp_set:
                guard()
                det = dets[d]
                rec = run.single_vote(client, lambda row, col, size, det=det: tiles.read_at(det, size), {"row": det["row"], "col": det["col"], "branch": det["branch"], "grade": "needs second look"}, d, ref_for(""), seed=SEED)
                keep(out / "votes_transplant.json", tp_doc, rec | {"detection": d})
        for sid in strips:
            run.write_json(out / f"manifest_{sid}.json", {"strip": sid, "ids": {run.candidate_id(i): {"row": c["row"], "col": c["col"]} for i, c in enumerate(data["strips"][sid]["candidates"][: a.top])}})

        # 4. the reviews
        for sid in strips:
            path = out / f"review_{sid}.json"
            if path.exists():
                continue
            guard()
            recs = {r["id"]: r for r in voted[sid]["records"]}
            cands = data["strips"][sid]["candidates"][: a.top]
            kept = [i for i, c in enumerate(cands) if recs[run.candidate_id(i)]["grade_after"] == c["grade"]][: REVIEW_TOP]
            view = [cands[i] for i in kept]
            view_votes = [recs[run.candidate_id(i)] | {"id": run.candidate_id(j)} for j, i in enumerate(kept)]
            checks = bounded_checks(run.check_runner(client, bank[sid].read, view, data["strips"][sid]["scale_m"], saturated_bright=True), a.checks)
            store = run.build_store(view, thresholds, "strip_a", vote_records=view_votes, checks=checks)
            result = spark.review(client, store, "strip_a", REVIEW_TURNS, one_turn=True)
            run.write_json(path, {"strip": sid, "backend": client.backend.name, "ranks": kept, **result.to_json(), "checks": store.check_log})
    except PauseError as e:
        checkpoint(out, client, str(e))
        print(f"PAUSED: {e}; ledger {led.total_cost_usd()} USD this run, {led.prior_usd} other runs. A person compares this with the Billing page.", file=sys.stderr)
        return 0
    except (Stop, CapError) as e:
        checkpoint(out, client, str(e))
        print(f"STOPPED: {e}", file=sys.stderr)
        return 4
    print(f"done: {led.units_total()} calls, {led.total_cost_usd()} USD this run, {round(led.prior_usd + led.total_cost_usd(), 4)} USD over all runs")
    return 0


def bounded_checks(runner, limit: int):
    """more_votes only, ``limit`` times; anything else comes back to the reviewer as a refusal."""
    used = {"n": 0}

    def check(cid: str, kind: str) -> dict:
        if kind != "more_votes":
            raise ValueError(f"{kind} is not available in this run; more_votes is")
        if used["n"] >= limit:
            raise ValueError(f"this review has used its {limit} checks")
        used["n"] += 1
        return runner(cid, kind)

    return check


if __name__ == "__main__":
    sys.exit(main())

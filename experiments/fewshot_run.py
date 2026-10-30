"""Driver for the few-shot Wonder comparison (plan item 9d), votes only, on one ledger in ``--out-dir``.

    uv run --env-file out/caps.env experiments/fewshot_run.py out/scoreboard/inputs/candidates_frozen_v1.json \
        --fill-from out/scoreboard --reference <9c's reference strip> --reference-for-reference <its own reference> \
        --probe <strip>:3 <strip>:2 --backend dry-run --out-dir out/fewshot_dry
    ... --backend real --out-dir out/fewshot

The strip ids are arguments, not code; the report names the ones used.

Three stages, in this order:

1. ``probe``: the recognition probe with examples attached, on the top n of each ``--probe strip:n`` (item
   9d: the two strips item 9b probed, top 3 and top 2, three crops each, 15 calls). Stop rule, written before the run: if any answer with
   ``recognised`` true names a site or a mission (any named place or spacecraft, on Mars or elsewhere; "Mars"
   or a terrain type alone is not a name), the driver stops after this stage and nothing else runs. The
   driver flags answers by the leak guard's name list (which holds the sealed sites' names) and a short extra
   list; the report reads every answer.
2. ``fill``: the plain (item 9c) votes that 9c's Wonder cap left out on the top 10, with 9c's exact set-up
   (seed 0, three votes, the reference crop from ``--reference``), so a filled vote is the request 9c would
   have sent. Before the first call, one of 9c's own requests on a filled strip is rebuilt and its recording
   must exist under ``--fill-from``; otherwise the set-up differs and the driver stops.
3. ``fewshot``: the few-shot votes (prompt ``vote-fewshot-v1``) on the top 10 of every strip, same seed,
   same reference crop, two hardware and two natural examples per vote from the other sites.

Every stage's calls are counted before anything is sent: if the ledger's Wonder remainder is below what all
remaining stages need, nothing runs. Each record is written as it lands (``votes_*.json``); a rerun skips
the ids already written, so a run killed part way continues without sending a request twice.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers.models import crops, leak, run, wonder  # noqa: E402
from landers.models.backend import request_hash  # noqa: E402
from landers.strip import Strip  # noqa: E402
from scripts.models_sam import BACKENDS, strip_reader  # noqa: E402
from scripts.models_wonder import drawn_record, fewshot_source, reference_spot  # noqa: E402

TOP, VOTES, SEED = 10, 3, 0
EXTRA_NAMES = ("jezero", "mars 2020", "ingenuity", "tianwen", "elysium", "philae", "rosetta", "comet", "67p",
               "acidalia", "arcadia", "hellas", "argyre", "tharsis", "olympus", "valles", "apollo", "luna",
               "lunokhod", "surveyor", "chang'e")


def names_something(ans: dict) -> str | None:
    text = f"{ans.get('place', '')} {ans.get('shows', '')}"
    hit = leak.find_leak(text)
    if hit and "name" in hit:
        return hit
    low = text.lower()
    return next((w for w in EXTRA_NAMES if w in low), None)


def load_records(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {"records": []}


def missing_plain(fill_from: Path, sid: str) -> set[int]:
    """Top-10 ranks with no 9c vote on ``sid`` (no votes file means none was cast)."""
    p = fill_from / f"votes_{sid}.json"
    done = {r["id"] for r in load_records(p)["records"] if "votes" in r}
    return {i for i in range(TOP) if run.candidate_id(i) not in done}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--fill-from", required=True, help="item 9c's out dir: its votes and recordings")
    ap.add_argument("--backend", required=True, choices=BACKENDS)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--reference", required=True, help="9c's reference strip")
    ap.add_argument("--reference-for-reference", required=True, help="the reference for that strip itself")
    ap.add_argument("--probe", nargs="+", required=True, metavar="STRIP:N", help="probe the top N of STRIP")
    a = ap.parse_args(argv)

    probe_n = {p.split(":")[0]: int(p.split(":")[1]) for p in a.probe}
    data = json.loads(Path(a.candidates).read_text())
    strips = list(data["strips"])
    out, fill_from = Path(a.out_dir), Path(a.fill_from)
    client = run.open_client(a.backend, out)
    opened: dict[str, Strip] = {}

    def strip(sid):
        if sid not in opened:
            opened[sid] = Strip.open(sid)
        return opened[sid]

    def top(sid, n=TOP):
        return run.top_candidates(data["strips"][sid]["candidates"], n)

    def reference(sid):
        ref_id = a.reference_for_reference if sid == a.reference else a.reference
        rs = strip(ref_id)
        return strip_reader(rs), reference_spot(rs, SEED)

    def done_ids(path):
        return {r["id"] for r in load_records(path)["records"] if "votes" in r or "probe" in r}

    # what is left to send, per stage
    probe_left = {s: n for s, n in probe_n.items() if not (out / f"probe_fewshot_{s}.json").exists()}
    fill_left = {}
    for s in strips:
        need = missing_plain(fill_from, s) - {int(i[1:]) for i in done_ids(out / f"votes_plain_{s}.json")}
        if need:
            fill_left[s] = need
    few_left = {s: set(range(TOP)) - {int(i[1:]) for i in done_ids(out / f"votes_fewshot_{s}.json")} for s in strips}
    need = (
        sum(n * VOTES for n in probe_left.values())
        + sum(len(v) * VOTES for v in fill_left.values())
        + sum(len(v) * VOTES for v in few_left.values())
    )
    remaining = client.ledger.remaining("wonder")
    print(f"backend {client.backend.name}; wonder remaining {remaining}; this run needs {need}")
    print(f"  probe {probe_left}; fill {{{', '.join(f'{s}: {len(v)}' for s, v in fill_left.items())}}}; "
          f"fewshot {sum(len(v) for v in few_left.values())} ids")
    if need > remaining:
        print("not enough Wonder calls left for every stage; nothing sent", file=sys.stderr)
        return 2

    # 1. probe with examples
    for sid, n in probe_left.items():
        src = fewshot_source(data, sid, strip(sid), SEED)
        ref, ref_at = reference(sid)
        recs = run.vote_pass(client, strip_reader(strip(sid)), top(sid, n), ref, ref_at, VOTES, seed=SEED,
                             probe=True, examples=src)
        run.write_json(out / f"probe_fewshot_{sid}.json", {"run": data.get("run"), "backend": client.backend.name,
                                                            "seed": SEED, "records": recs})
        run.write_json(out / f"fewshot_probe_{sid}.json", {"strip": sid, "examples": drawn_record(src)})
    flags = []
    for sid in probe_n:
        for r in load_records(out / f"probe_fewshot_{sid}.json")["records"]:
            for k, ans in enumerate(r.get("probe", [])):
                print(f"probe {sid} {r['id']}/{k}: recognised {ans['recognised']} {ans['confidence']:.2f} "
                      f"place={ans['place']!r} shows={ans['shows']!r}")
                hit = names_something(ans)
                if ans["recognised"] and hit:
                    flags.append(f"{sid} {r['id']}/{k}: {hit}")
    if flags:
        (out / "STOPPED.txt").write_text("probe named a site or mission:\n" + "\n".join(flags) + "\n")
        print("STOP: the probe with examples named a site or mission; see STOPPED.txt", file=sys.stderr)
        return 3

    # 2. the plain votes 9c's cap left out, with 9c's set-up
    if fill_left:
        check = next((s for s in fill_left if missing_plain(fill_from, s) != set(range(TOP))), None)
        if check is None:
            print("no partly voted strip to check 9c's set-up against", file=sys.stderr)
            return 4
        ref, ref_at = reference(check)
        c0 = top(check)[0]
        rng = np.random.default_rng(SEED)
        aug = crops.draw_augmentations(rng, VOTES, 256)[0]
        d, v = strip_reader(strip(check))(c0["row"], c0["col"], 384)
        rd, rv = ref(ref_at[0], ref_at[1], 384)
        view = crops.build_crop(d, v, d.shape[0] / 2.0, d.shape[1] / 2.0, 256, 4, aug, (rd, rv, rd.shape[0] / 2.0, rd.shape[1] / 2.0))
        h = request_hash(wonder.vote_request(view))
        if not (fill_from / "model_recordings" / f"wonder_{h}.json").exists():
            print(f"9c's request for {check} c000 vote 0 (hash {h}) is not in {fill_from}: set-up differs", file=sys.stderr)
            return 4
        print(f"set-up check: {check} c000 vote 0 rebuilt, hash {h} found in 9c's recordings")
    for sid, idx in fill_left.items():
        path = out / f"votes_plain_{sid}.json"
        doc = load_records(path) | {"run": data.get("run"), "backend": client.backend.name, "seed": SEED,
                                    "prompt": wonder.PLAIN_VERSION}
        ref, ref_at = reference(sid)

        def keep(rec, doc=doc, path=path):
            doc["records"].append(rec)
            run.write_json(path, doc)

        print(f"{sid} fill: {len(idx)} ids", flush=True)
        run.vote_pass(client, strip_reader(strip(sid)), top(sid), ref, ref_at, VOTES, seed=SEED, only=idx, on_record=keep)

    # 3. few-shot votes on the top 10 of every strip
    for sid, idx in few_left.items():
        if not idx:
            continue
        path = out / f"votes_fewshot_{sid}.json"
        doc = load_records(path) | {"run": data.get("run"), "backend": client.backend.name, "seed": SEED,
                                    "prompt": wonder.FEWSHOT_VERSION}
        src = fewshot_source(data, sid, strip(sid), SEED)
        ref, ref_at = reference(sid)
        ex_path = out / f"fewshot_{sid}.json"
        drawn = load_records(ex_path).get("examples", {})

        def keep(rec, doc=doc, path=path, src=src, drawn=drawn, ex_path=ex_path, sid=sid):
            doc["records"].append(rec)
            run.write_json(path, doc)
            drawn.update(drawn_record(src))
            run.write_json(ex_path, {"strip": sid, "examples": drawn})

        print(f"{sid} fewshot: {len(idx)} ids", flush=True)
        run.vote_pass(client, strip_reader(strip(sid)), top(sid), ref, ref_at, VOTES, seed=SEED, examples=src,
                      only=idx, on_record=keep)
    for sid in strips:
        run.write_json(out / f"manifest_{sid}.json",
                       {"strip": sid, "ids": {run.candidate_id(i): {"row": c["row"], "col": c["col"]}
                                              for i, c in enumerate(top(sid))}})
    print(f"cost so far ${client.ledger.total_cost_usd()}; wonder remaining {client.ledger.remaining('wonder')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

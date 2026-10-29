"""Summary of the first real model run (plan item 9b) from its published copy, for the report.

    uv run experiments/first_run_summary.py docs/reports/<dir> --models out/models --strip ESP_... > <dir>/summary.txt

Reads the published (redacted) records; the id-to-position manifests and the input lists under
``--models`` are used only to say which candidate id is a recorded piece (the key is readable in
reports, never in prompts). Every number the report quotes comes from this output.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402


def load(p: Path):
    return json.loads(p.read_text())


def key_pieces(key: dict, strip: str) -> list[tuple[str, float, float]]:
    out = []
    for site in key["sites"]:
        for pc in site["pieces"]:
            if pc.get("strip") == strip and pc.get("line") is not None:
                out.append((f"{site['name']}:{pc['piece']}", float(pc["line"]) - 1.0, float(pc["sample"]) - 1.0))
    return out


def matches(manifest: dict, pieces, radius_px: float = 20.0) -> dict[str, str]:
    out = {}
    for cid, pos in manifest["ids"].items():
        best = None
        for name, r, c in pieces:
            d = math.hypot(pos["row"] - r, pos["col"] - c)
            if d <= radius_px and (best is None or d < best[1]):
                best = (name, d)
        if best:
            out[cid] = f"{best[0]} ({best[1]:.1f} px)"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("published")
    ap.add_argument("--models", default="out/models")
    ap.add_argument("--strip", required=True, help="the strip of the SAM, votes and review records")
    ap.add_argument("--key", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    a = ap.parse_args(argv)
    pub, models = Path(a.published), Path(a.models)
    key = load(Path(a.key))

    print("# Recognition probes")
    for p in sorted(pub.glob("probe_*.json")):
        d = load(p)
        strip = p.stem[len("probe_") :]
        tag = ""
        if strip.endswith("_key"):
            strip, tag = strip[: -len("_key")], "_key"
        man = models / f"manifest_{strip}{tag}.json"
        who = {}
        if tag:
            inputs = load(models / "inputs" / "key_pieces.json")["strips"][strip]["candidates"]
            who = {f"c{i:03d}": c["extra"]["piece"] for i, c in enumerate(inputs)}
        elif man.exists():
            who = matches(load(man), key_pieces(key, strip))
        n = sum(r["summary"]["n"] for r in d["records"])
        rec = sum(r["summary"]["recognised"] for r in d["records"])
        print(f"{p.name}: strip {strip}, {len(d['records'])} crops positions, {n} answers, {rec} recognised")
        for r in d["records"]:
            s = r["summary"]
            print(f"  {r['id']} {who.get(r['id'], 'no recorded piece within 20 px')}: {s['recognised']} of {s['n']} recognised, max confidence {s['max_confidence']}")
            for q in r["probe"]:
                print(f"    recognised={q['recognised']} confidence={q['confidence']} place={q['place']!r}")
                print(f"      shows={q['shows']!r}")

    print()
    print("# SAM")
    sp = pub / f"sam_{a.strip}.json"
    d = load(sp)
    who = matches(load(models / f"manifest_{a.strip}.json"), key_pieces(key, a.strip))
    recs = d["records"]
    confs = [r["confidence"] for r in recs if r.get("found")]
    print(f"{sp.name}: {len(recs)} records, found {sum(1 for r in recs if r.get('found'))}, limits {d['limits']}")
    print(f"confidence min {min(confs)} median {statistics.median(confs)} max {max(confs)}")
    print(f"touches_box_edge: {sum(1 for r in recs if r['measurements'].get('touches_box_edge'))} of {len(recs)}")
    pieces = [r["measurements"].get("pieces", 0) for r in recs]
    print(f"mask pieces min {min(pieces)} median {statistics.median(pieces)} max {max(pieces)}")
    outcomes: dict = {}
    for r in recs:
        for t, v in r["tests"].items():
            outcomes.setdefault(t, {}).setdefault(v["outcome"], 0)
            outcomes[t][v["outcome"]] += 1
    print(f"outcomes {outcomes}")
    print("id branch box_px conf equiv_diameter_m elongation edge_contrast touches pieces tests | recorded piece")
    for r in recs:
        m, b = r["measurements"], r["box"]
        print(
            f"  {r['id']} {r['branch']} {b['x2'] - b['x1'] + 1} {r['confidence']} {m.get('equiv_diameter_m')} "
            f"{m.get('elongation')} {m.get('edge_contrast')} {m.get('touches_box_edge')} {m.get('pieces')} "
            f"{ {t: v['outcome'] for t, v in r['tests'].items()} } | {who.get(r['id'], '-')}"
        )

    print()
    print("# Votes")
    vp = pub / f"votes_{a.strip}.json"
    if vp.exists():
        d = load(vp)
        for r in d["records"]:
            print(f"{r['id']} {r['branch']} {who.get(r['id'], '-')}: {r['grade_before']} -> {r['grade_after']} | {r['note']}")
            for v in r["votes"]:
                print(f"    {v['verdict']} {v['confidence']} tokens {v['tokens']} :: {v['reason']}")

    print()
    print("# Review")
    rp = pub / f"review_{a.strip}.json"
    if rp.exists():
        d = load(rp)
        print(f"stopped: {d['stopped']} after {d['turns']} turns; {len(d['verdicts'])} verdicts; final {'parsed' if d['final'] else 'none'}")
        changed = {k: g for k, g in d["grades"].items() if g["after"] != g["before"]}
        print(f"grades lowered: {len(changed)} {changed}")
        for cid, v in d["verdicts"].items():
            print(f"  {cid} {who.get(cid, '-')}: {v['action']} cites {v['cites']} :: {v['reason']}")
        print(f"checks ordered: {[(c['id'], c['kind'], 'refused' if 'refused' in c else 'ran') for c in d['checks']]}")
        tools = {}
        for t in d["tool_log"]:
            tools[t["tool"]] = tools.get(t["tool"], 0) + 1
        print(f"tool calls: {tools}")

    print()
    print("# Ledger")
    led = load(pub / "ledger.json")
    print(f"caps {led['caps']}; total_cost_usd {led['total_cost_usd']}")
    for m, e in led["entries"].items():
        print(f"  {m}: units {e['units']} ok {e['ok']} failed {e['failed']} refused {e['refused']} tokens in {e['input_tokens']} out {e['output_tokens']} cost_usd {e['cost_usd']}")
    pubrec = load(pub / "PUBLISHED.json")
    print(f"published files {len(pubrec['files'])}, redactions {pubrec['total_redactions']} in "
          f"{[n for n, f in pubrec['files'].items() if f['redactions']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

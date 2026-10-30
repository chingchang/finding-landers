"""The model-layer scoreboard (plan item 9c) from the published records: what SAM, the Wonder votes and the
Spark review did to the top 20 of each tuning strip, against controls/tuning.json.

    uv run experiments/scoreboard_summary.py docs/reports/<dir> --inputs out/scoreboard/inputs/candidates_frozen_v1.json \
        > docs/reports/<dir>/summary.txt

Reads the published (redacted) votes, SAM and review records and the ledger. A top-20 id is "on a piece"
when it lies within that piece's match radius (controls/thresholds.json, by kind and strip scale), as
scripts/score.py counts hits; every other id is a false alarm. The positions come from the review record's
id list and are compared with the key only here, in a report script; they never entered a prompt.

Per id the grade path is: the detector's grade, then the vote rule (votes record), then the review
(review record, whose "before" already carries the vote result). An id is "lowered" when its final grade is
below the detector's, "kept" when a stage looked at it and left it ("by review" when the review recorded a
verdict, "by votes only" when three votes were cast and no verdict was recorded), and "unassessed" when
neither a vote nor a verdict reached it. SAM changes no grade by itself; its test outcomes are listed as
evidence. Writes ``summary.json`` beside the records and prints the same numbers as text.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.score import match_radius_px, piece_kind  # noqa: E402


def load(p: Path):
    return json.loads(Path(p).read_text())


def pieces_on(key: dict, thresholds: dict, strip: str, scale_m: float) -> list[dict]:
    out = []
    for site in key["sites"]:
        for pc in site["pieces"]:
            if pc.get("strip") != strip or pc.get("line") is None:
                continue
            kind = piece_kind(pc["piece"], thresholds)
            out.append(
                {
                    "piece": f"{site['name']}:{pc['piece']}",
                    "kind": kind,
                    "row": float(pc["line"]) - 1.0,
                    "col": float(pc["sample"]) - 1.0,
                    "radius": match_radius_px(thresholds, scale_m, kind),
                }
            )
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("published")
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--key", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    a = ap.parse_args(argv)

    pub = Path(a.published)
    withheld = load(pub / "PUBLISHED.json").get("withheld", {})

    def record(name: str):
        """A published record, or its out/ source when it was withheld (experiments/withhold.py)."""
        return load(withheld[name]["source"]) if name in withheld else load(pub / name)

    inputs = load(a.inputs)
    key, thresholds = load(a.key), load(a.thresholds)
    ledger = load(pub / "ledger.json")
    rows, strips_out = [], []
    print(f"# Model-layer scoreboard from {pub}")
    key_name = Path(a.key).resolve()
    key_name = key_name.relative_to(config.REPO_ROOT) if key_name.is_relative_to(config.REPO_ROOT) else key_name
    print(f"inputs {a.inputs} (rules {inputs['detector'].get('shape_rules')}); key {key_name}")
    print(f"ledger: total ${ledger['total_cost_usd']}; " + "; ".join(
        f"{m} {e['units']} {ledger['units'][m]} (refused {e['refused']}, ${e['cost_usd']})"
        for m, e in ledger["entries"].items()
    ))
    print()
    for sid, entry in inputs["strips"].items():
        votes = {r["id"]: r for r in record(f"votes_{sid}.json")["records"]}
        sam = {r["id"]: r for r in record(f"sam_{sid}.json")["records"]}
        review = record(f"review_{sid}.json")
        checks_by, check_results = {}, {}
        for ch in review.get("checks", []):
            checks_by.setdefault(ch["id"], []).append(ch["kind"])
            if ch["kind"] == "more_votes" and "votes" in ch.get("result", {}):
                check_results.setdefault(ch["id"], []).append(ch["result"])
        pcs = pieces_on(key, thresholds, sid, float(entry.get("scale_m", 0.25)))
        strip_rows = []
        for rank, (cid, pos) in enumerate(review["ids"].items(), start=1):
            near = [p for p in pcs if math.hypot(pos["row"] - p["row"], pos["col"] - p["col"]) <= p["radius"]]
            v = votes.get(cid)
            g = review["grades"].get(cid, {})
            verdict = review["verdicts"].get(cid)
            detector_grade = (v or {}).get("grade_before") or g.get("before")
            vote_grade = (v or {}).get("grade_after") if v and "votes" in v else None
            final = g.get("after") or vote_grade or detector_grade
            lowered_by = []
            if vote_grade and vote_grade != v["grade_before"]:
                lowered_by.append("votes")
            if g and g["after"] != g["before"]:
                lowered_by.append("review")
            voted = bool(v and "votes" in v)
            if lowered_by:
                status = "lowered"
            elif verdict:
                status = "kept by review"
            elif voted:
                status = "kept by votes only"
            else:
                status = "unassessed"
            s = sam.get(cid, {})
            row = {
                "strip": sid,
                "rank": rank,
                "id": cid,
                "branch": s.get("branch") or (v or {}).get("branch"),
                "on_piece": [p["piece"] for p in near],
                "kinds": sorted({p["kind"] for p in near}),
                "grade_detector": detector_grade,
                "grade_after_votes": vote_grade,
                "grade_final": final,
                "lowered_by": lowered_by,
                "status": status,
                "votes": [(x["verdict"], x["confidence"]) for x in (v or {}).get("votes", [])],
                "vote_note": (v or {}).get("note"),
                "vote_not_run": (v or {}).get("not_run"),
                "verdict": verdict,
                "checks": checks_by.get(cid, []),
                "more_votes": [
                    {"votes": [(x["verdict"], x["confidence"]) for x in r["votes"]], "rule": r["grade_after"]}
                    for r in check_results.get(cid, [])
                ],
                "sam_tests": {t: o["outcome"] for t, o in s.get("tests", {}).items()},
                "sam_equiv_diameter_m": (s.get("measurements") or {}).get("equiv_diameter_m"),
            }
            strip_rows.append(row)
        rows.extend(strip_rows)
        fa = [r for r in strip_rows if not r["on_piece"]]
        on = [r for r in strip_rows if r["on_piece"]]
        c = Counter(r["status"] for r in fa)
        so = {
            "strip": sid,
            "review_stopped": review["stopped"],
            "review_turns": review["turns"],
            "review_verdicts": len(review["verdicts"]),
            "review_checks": dict(Counter(ch["kind"] for ch in review.get("checks", []))),
            "voted_ids": sum(1 for r in strip_rows if r["votes"]),
            "on_piece_ids": len(on),
            "false_alarms": len(fa),
            "fa_lowered": c["lowered"],
            "fa_lowered_by_votes": sum(1 for r in fa if "votes" in r["lowered_by"]),
            "fa_lowered_by_review": sum(1 for r in fa if "review" in r["lowered_by"]),
            "fa_kept_by_review": c["kept by review"],
            "fa_kept_by_votes_only": c["kept by votes only"],
            "fa_unassessed": c["unassessed"],
            "pieces_lowered": sum(1 for r in on if r["lowered_by"]),
        }
        strips_out.append(so)
        print(
            f"{sid}: review {so['review_stopped']} after {so['review_turns']} turns, {so['review_verdicts']} verdicts, checks {so['review_checks']}; "
            f"votes on {so['voted_ids']} ids; top 20 = {so['on_piece_ids']} on a piece + {so['false_alarms']} false alarms"
        )
        print(
            f"  false alarms: lowered {so['fa_lowered']} (votes {so['fa_lowered_by_votes']}, review "
            f"{so['fa_lowered_by_review']}), kept by review {so['fa_kept_by_review']}, kept by votes only "
            f"{so['fa_kept_by_votes_only']}, unassessed {so['fa_unassessed']}"
        )
        for r in on:
            vt = ", ".join(f"{k} {c_:.2f}" for k, c_ in r["votes"]) or (r["vote_not_run"] and "not run") or "none"
            print(
                f"  rank {r['rank']:2d} {r['id']} {'+'.join(r['on_piece'])} ({r['branch']}): {r['grade_detector']} -> "
                f"{r['grade_final']} [{r['status']}{' by ' + '+'.join(r['lowered_by']) if r['lowered_by'] else ''}]"
            )
            print(f"    votes: {vt}; sam {r['sam_tests']} d={r['sam_equiv_diameter_m']} m; checks {r['checks']}")
            for mv in r["more_votes"]:
                print(f"    more votes: {', '.join(f'{k} {c_:.2f}' for k, c_ in mv['votes'])}; rule says {mv['rule']}")
            if r["verdict"]:
                print(f"    verdict {r['verdict']['action']} cites {r['verdict']['cites']}: {r['verdict']['reason']}")
    on_all = [r for r in rows if r["on_piece"]]
    fa_all = [r for r in rows if not r["on_piece"]]
    lowered_fa = sum(1 for r in fa_all if r["lowered_by"])
    tot = {
        "strips": len(strips_out),
        "ids": len(rows),
        "on_piece_ids": len(on_all),
        "pieces_in_top20": sorted({p for r in on_all for p in r["on_piece"]}),
        "pieces_lowered": [(r["strip"], r["id"], r["on_piece"], r["lowered_by"]) for r in on_all if r["lowered_by"]],
        "false_alarms": len(fa_all),
        "fa_status": dict(Counter(r["status"] for r in fa_all)),
        "fa_lowered_by_votes": sum(1 for r in fa_all if "votes" in r["lowered_by"]),
        "fa_lowered_by_review": sum(1 for r in fa_all if "review" in r["lowered_by"]),
        "fa_lowered_by_both": sum(1 for r in fa_all if len(r["lowered_by"]) == 2),
        "voted_ids": sum(1 for r in rows if r["votes"]),
        "voted_false_alarms": sum(1 for r in fa_all if r["votes"]),
        "checks_ordered": dict(Counter(k for r in rows for k in r["checks"])),
        "more_votes_rule_likely_natural": sum(1 for r in rows for mv in r["more_votes"] if mv["rule"] == "likely natural"),
        "more_votes_rule_likely_natural_unacted": sum(
            1 for r in rows if any(mv["rule"] == "likely natural" for mv in r["more_votes"]) and not r["lowered_by"]
        ),
        "total_cost_usd": ledger["total_cost_usd"],
        "cost_per_fa_lowered_usd": round(ledger["total_cost_usd"] / lowered_fa, 4) if lowered_fa else None,
        "fa_sam_tests": {
            t: dict(Counter(r["sam_tests"].get(t) for r in fa_all)) for t in ("sam_size", "sam_edge", "sam_shape")
        },
        "piece_sam_tests": {
            t: dict(Counter(r["sam_tests"].get(t) for r in on_all)) for t in ("sam_size", "sam_edge", "sam_shape")
        },
    }
    print()
    print(f"# Totals over {tot['strips']} strips, {tot['ids']} top-20 ids")
    print(f"on a piece: {tot['on_piece_ids']} ids covering {len(tot['pieces_in_top20'])} pieces {tot['pieces_in_top20']}")
    print(f"pieces lowered: {len(tot['pieces_lowered'])} {tot['pieces_lowered']}")
    print(
        f"false alarms: {tot['false_alarms']}; {tot['fa_status']}; lowered by votes {tot['fa_lowered_by_votes']}, "
        f"by review {tot['fa_lowered_by_review']}, by both {tot['fa_lowered_by_both']}"
    )
    print(f"votes cast on {tot['voted_ids']} ids, {tot['voted_false_alarms']} of them false alarms")
    print(
        f"checks ordered by the reviews: {tot['checks_ordered']}; more-votes checks whose rule said likely natural "
        f"{tot['more_votes_rule_likely_natural']}, of which the id was not lowered {tot['more_votes_rule_likely_natural_unacted']}"
    )
    print(f"cost: ${tot['total_cost_usd']} by the ledger; ${tot['cost_per_fa_lowered_usd']} per false alarm lowered")
    print(f"SAM tests on false alarms: {tot['fa_sam_tests']}")
    print(f"SAM tests on piece ids: {tot['piece_sam_tests']}")
    (pub / "summary.json").write_text(json.dumps({"totals": tot, "strips": strips_out, "ids": rows}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

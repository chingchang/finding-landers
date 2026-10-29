"""The tuning loop's judge (docs/plan.md item 8): one candidate rules file, two scoreboards, one verdict.

A rules change is scored without re-detecting. The key board rescores an unruled candidates file of the
tuning strips (what ``scripts/rescore.py`` does) and scores it against ``controls/tuning.json``. The
injection board re-applies the rules to the features recorded on every detection of an unruled transplant
run (``scripts/transplant.py``) and recomputes recall at the thresholds' false-alarm rate. A detector change
needs fresh files for both boards and is judged the same way.

Rule gains are never typed by hand: ``fit`` measures each candidate rule's pass fraction over the same-branch
false alarms of the tuning strips (``landers.features_eval``) and sets the gain to minus log10 of it, so the
candidate file only has to say the test.

The bar is the one a person wrote in docs/plan.md item 8, kept in ``BAR`` and applied by ``verdict``:

- hardware recall at N on the key does not drop;
- injection recall at the false-alarm rate does not drop, overall and for hardware on its own;
- no recorded piece that was inside the top N leaves it;
- every rule that is not in the reference file (same branches and conditions) passes at most
  ``BAR["max_rule_pass_fraction"]`` of same-branch false alarms on the tuning strips, pooled.

What passes is still only a proposal: a rules file the loop wants adopted goes to docs/proposals/ for a person.
"""

from __future__ import annotations

import math
from dataclasses import asdict

from landers.features_eval import measure
from landers.score import Score, match_radius_px, recall_at_false_alarm_rate, score
from landers.shape import ShapeRules, apply_rules_json

BAR = {"max_rule_pass_fraction": 0.05}
DEFAULT_SCALE_M = 0.25


# ---------------------------------------------------------------- rules


def rule_signature(rule) -> tuple:
    return (tuple(rule.branches), tuple(str(c) for c in rule.conditions))


def new_rules(candidate: ShapeRules, reference: ShapeRules | None) -> list[str]:
    """Names of the candidate's rules whose test is not in the reference (a changed threshold counts as new)."""
    seen = {rule_signature(r) for r in reference.rules} if reference is not None else set()
    return [r.name for r in candidate.rules if rule_signature(r) not in seen]


def fit(key_cands: dict, answers: dict, thresholds: dict, rules: ShapeRules) -> tuple[ShapeRules, list[dict]]:
    """The rules with their pass fraction and gain measured on the key run's false alarms, and the
    per-rule measurement rows (pooled and per strip, and which piece candidates pass)."""
    if key_cands.get("detector", {}).get("shape_rules"):
        raise ValueError("the key candidates file already carries shape rules; fit on the unruled run")
    m = measure(key_cands, answers, thresholds, rules)
    return ShapeRules.from_json(m["rules"]["fitted_rules"]), m["rules"]["rows"]


# ---------------------------------------------------------------- the key board


def key_board(key_cands: dict, answers: dict, thresholds: dict, rules: ShapeRules | None) -> Score:
    """Score of the key run with ``rules`` applied to every candidate's recorded features (no re-detection)."""
    if rules is None:
        return score(key_cands, answers, thresholds)
    strips = {
        sid: {**entry, "candidates": [apply_rules_json(c, rules) for c in entry.get("candidates", [])]}
        for sid, entry in key_cands.get("strips", {}).items()
    }
    return score({**key_cands, "strips": strips}, answers, thresholds)


def pieces_in_top(s: Score) -> set[tuple[str, str]]:
    return {(p.site, p.piece) for p in s.pieces if p.rank is not None and p.rank <= s.top_n}


# ---------------------------------------------------------------- the injection board


def injection_truths(run: dict, thresholds: dict) -> list[dict]:
    cuts = run["cuts"]
    truths = []
    for i, p in enumerate(run["placements"]):
        if p.get("sham"):
            continue
        cut = cuts[p["cut_index"]]
        truths.append(
            {
                "tile": p["tile"],
                "row": p["row"],
                "col": p["col"],
                "kind": p["kind"],
                "site": p["site"],
                "piece": p["piece"],
                "size_m": cut["size_m"],
                "radius_px": p.get("match_radius_px") or match_radius_px(thresholds, cut["scale_m"], p["kind"]),
                "placement": i,
            }
        )
    return truths


def apply_to_detections(detections: list[dict], rules: ShapeRules | None) -> list[dict]:
    """The rules' gains added to recorded detections, from the features each one carries."""
    if rules is None:
        return list(detections)
    out = []
    for d in detections:
        gain, passed = rules.adjust(d["branch"], d.get("features") or {})
        if not passed:
            out.append(d)
            continue
        feats = dict(d.get("features") or {})
        feats["shape_pass"] = passed
        feats["shape_gain"] = round(gain, 3)
        out.append({**d, "score": round(float(d["score"]) + gain, 4), "features": feats})
    return out


def injection_board(run: dict, thresholds: dict, rules: ShapeRules | None) -> dict:
    """Recall at the run's false-alarm rate with ``rules`` applied to its recorded detections, by piece and
    by kind, plus the sham control at the resulting threshold."""
    if run.get("detector", {}).get("shape_rules"):
        raise ValueError("the injection run already carries shape rules; judge from an unruled run")
    if rules is not None and not any(d.get("features") for d in run["detections"]):
        raise ValueError("the injection run's detections carry no features; rerun scripts/transplant.py")
    dets = apply_to_detections(run["detections"], rules)
    truths = injection_truths(run, thresholds)
    area = float(run["area_km2"])
    fa = float(run["fa_per_km2_target"])
    radius_default = match_radius_px(thresholds, DEFAULT_SCALE_M)

    def scored(group):
        return recall_at_false_alarm_rate(dets, truths, area, radius_default, fa, group=group)

    by_piece = scored(lambda t: (t["kind"], f"{t['site']}/{t['piece']}"))
    by_kind = scored(lambda t: (t["kind"], "all"))
    thr = by_piece["score_threshold"]
    kept = [d for d in dets if thr is None or float(d["score"]) > thr]
    by_tile: dict[str, list[dict]] = {}
    for d in kept:
        by_tile.setdefault(d["tile"], []).append(d)
    sham_n = sham_hit = 0
    for p in run["placements"]:
        if not p.get("sham"):
            continue
        sham_n += 1
        r = float(p["match_radius_px"])
        if any(
            math.hypot(float(d["row"]) - p["row"], float(d["col"]) - p["col"]) <= r for d in by_tile.get(p["tile"], [])
        ):
            sham_hit += 1
    return {
        "score": by_piece,
        "score_by_kind": by_kind,
        "sham": {"n": sham_n, "hit": sham_hit, "rate": round(sham_hit / sham_n, 3) if sham_n else None},
    }


def kind_row(board: dict, kind: str) -> dict | None:
    return next((r for r in board["score_by_kind"]["rows"] if r["kind"] == kind), None)


# ---------------------------------------------------------------- the verdict


def verdict(ref_key: Score, cand_key: Score, ref_inj: dict, cand_inj: dict, new_rule_rows: list[dict]) -> dict:
    checks = []

    def check(name: str, ok: bool, ref, cand):
        checks.append({"check": name, "pass": bool(ok), "reference": ref, "candidate": cand})

    rh, ch = ref_key.recall_by_kind.get("hardware", {}), cand_key.recall_by_kind.get("hardware", {})
    check(
        "key hardware recall@N does not drop",
        ch.get("found", 0) >= rh.get("found", 0),
        rh.get("found"),
        ch.get("found"),
    )
    r_all, c_all = ref_inj["score_by_kind"]["recall_overall"], cand_inj["score_by_kind"]["recall_overall"]
    check("injection recall does not drop", (c_all or 0) >= (r_all or 0), r_all, c_all)
    rk, ck = kind_row(ref_inj, "hardware"), kind_row(cand_inj, "hardware")
    check(
        "injection hardware recall does not drop",
        (ck["found"] if ck else 0) >= (rk["found"] if rk else 0),
        rk["found"] if rk else None,
        ck["found"] if ck else None,
    )
    left = sorted(pieces_in_top(ref_key) - pieces_in_top(cand_key))
    check("no recorded piece leaves the top N", not left, sorted(pieces_in_top(ref_key)), left)
    for row in new_rule_rows:
        frac = row["pooled"]["fraction"]
        check(
            f"new rule {row['name']} passes at most {BAR['max_rule_pass_fraction']} of false alarms",
            frac is not None and frac <= BAR["max_rule_pass_fraction"],
            BAR["max_rule_pass_fraction"],
            frac,
        )
    return {"keep": all(c["pass"] for c in checks), "checks": checks}


# ---------------------------------------------------------------- one experiment


def compare(
    name: str,
    key_cands: dict,
    answers: dict,
    thresholds: dict,
    inj_run: dict,
    reference: ShapeRules | None,
    candidate: ShapeRules | None,
    refit_reference: bool = False,
) -> dict:
    """Both boards under the reference rules and under the candidate rules (gains refit on the key run's
    false alarms), and the verdict. ``candidate`` None judges the reference against no rules at all."""
    ref_rows: list[dict] = []
    if reference is not None and refit_reference:
        reference, ref_rows = fit(key_cands, answers, thresholds, reference)
    cand_rows: list[dict] = []
    if candidate is not None:
        candidate, cand_rows = fit(key_cands, answers, thresholds, candidate)
    ref_key = key_board(key_cands, answers, thresholds, reference)
    cand_key = key_board(key_cands, answers, thresholds, candidate)
    ref_inj = injection_board(inj_run, thresholds, reference)
    cand_inj = injection_board(inj_run, thresholds, candidate)
    fresh = new_rules(candidate, reference) if candidate is not None else []
    v = verdict(ref_key, cand_key, ref_inj, cand_inj, [r for r in cand_rows if r["name"] in fresh])
    ranks = {}
    for p, q in zip(ref_key.pieces, cand_key.pieces, strict=True):
        ranks[f"{p.site}/{p.piece}"] = {"kind": p.kind, "reference": p.rank, "candidate": q.rank, "branch": q.branch}
    inj_pieces = {}
    for r_row in ref_inj["score"]["rows"]:
        c_row = next(x for x in cand_inj["score"]["rows"] if x["size_bin"] == r_row["size_bin"])
        inj_pieces[r_row["size_bin"]] = {
            "kind": r_row["kind"],
            "n": r_row["n"],
            "reference": r_row["found"],
            "candidate": c_row["found"],
        }
    return {
        "name": name,
        "keep": v["keep"],
        "checks": v["checks"],
        "bar": BAR,
        "reference_rules": reference.to_json() if reference is not None else None,
        "candidate_rules": candidate.to_json() if candidate is not None else None,
        "new_rules": fresh,
        "rule_rows": {"reference": ref_rows, "candidate": cand_rows},
        "key": {"reference": asdict(ref_key), "candidate": asdict(cand_key), "ranks": ranks},
        "injection": {"reference": ref_inj, "candidate": cand_inj, "pieces": inj_pieces},
    }


def _kind_cell(s: dict, kind: str) -> str:
    d = s.get("recall_by_kind", {}).get(kind)
    return "-" if not d else f"{d['found']}/{d['recorded']}"


def summary_line(r: dict) -> str:
    """One line for docs/experiments.md or a report."""
    rk, ck = r["key"]["reference"], r["key"]["candidate"]
    ri, ci = r["injection"]["reference"]["score_by_kind"], r["injection"]["candidate"]["score_by_kind"]

    def inj(b: dict) -> str:
        return " ".join(f"{row['kind']} {row['found']}/{row['n']}" for row in b["rows"])

    return (
        f"{r['name']}: key recall@{ck['top_n']} {ck['n_pieces_found']}/{ck['n_pieces_recorded']} "
        f"(hardware {_kind_cell(ck, 'hardware')}) against {rk['n_pieces_found']}/{rk['n_pieces_recorded']} "
        f"(hardware {_kind_cell(rk, 'hardware')}); injection {inj(ci)} against {inj(ri)}; "
        f"{'KEEP' if r['keep'] else 'REVERT'}"
    )


def format_compare(r: dict) -> str:
    lines = [summary_line(r), ""]
    lines.append(f"{'site/piece':28s} {'kind':9s} {'reference':>10s} {'candidate':>10s}  branch")
    for key, d in r["key"]["ranks"].items():
        ref = "-" if d["reference"] is None else str(d["reference"])
        cand = "-" if d["candidate"] is None else str(d["candidate"])
        lines.append(f"{key:28s} {d['kind']:9s} {ref:>10s} {cand:>10s}  {d['branch'] or '-'}")
    lines.append("")
    ri, ci = r["injection"]["reference"], r["injection"]["candidate"]
    lines.append(
        f"injection threshold {ri['score']['score_threshold']} -> {ci['score']['score_threshold']}; "
        f"sham hits {ri['sham']['hit']}/{ri['sham']['n']} -> {ci['sham']['hit']}/{ci['sham']['n']}"
    )
    lines.append(f"{'planting':28s} {'kind':9s} {'n':>3s} {'reference':>10s} {'candidate':>10s}")
    for key, d in r["injection"]["pieces"].items():
        lines.append(f"{key:28s} {d['kind']:9s} {d['n']:3d} {d['reference']:10d} {d['candidate']:10d}")
    lines.append("")
    for row in r["rule_rows"]["candidate"]:
        po = row["pooled"]
        tag = "new" if row["name"] in r["new_rules"] else "as reference"
        lines.append(
            f"rule {row['test']} [{','.join(row['branches'])}] ({tag}): false alarms pass "
            f"{po['n_pass']}/{po['n_false']} = {po['fraction']}, gain {row['gain_if_adopted']}, "
            f"piece candidates passing {row['piece_candidates_passing']}"
        )
    lines.append("")
    for c in r["checks"]:
        lines.append(
            f"[{'pass' if c['pass'] else 'FAIL'}] {c['check']}: reference {c['reference']}, candidate {c['candidate']}"
        )
    lines.append("")
    lines.append("verdict: " + ("KEEP (a proposal for a person; nothing is adopted here)" if r["keep"] else "REVERT"))
    return "\n".join(lines)

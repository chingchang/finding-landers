"""Leave-one-site-out check of a shape rules file (docs/plan.md item 8).

The tuning loop fits every rule's pass fraction and gain on the false alarms of all six tuning sites and
then scores the same six sites, so a rule can look good because it was shaped on the pieces it is scored
against. This check holds one site back at a time: each rule is re-fitted on the other sites' false alarms
only (``landers.tune.fit`` on the key run without the held-back site's strips, every strip of the site
including dates without a recorded piece) and the held-back site's pieces are scored under those gains.
Pooling the six folds gives a held-out key board; the injection board is scored the same way, counting only
the plantings cut from the held-back site, with the fold's gains applied to every recorded detection.

A rule's lift is measured by ablation under the same folds: the pooled held-out boards with every rule
against the same boards with that rule left out. ``verdict`` says a rule holds when, on sites it was not
fitted on, leaving it out does not make the board better: pooled key recall at N (hardware and all) and
injection recall (hardware and all) are no higher without it, no held-out piece is pushed out of the top
N by it, and its pass fraction stays under the bar on every fold. A rule that fails is withdrawn in a
proposal for a person; nothing here edits landers/shape_v*.json.
"""

from __future__ import annotations

from dataclasses import asdict

from landers.score import Score
from landers.shape import ShapeRules
from landers.tune import BAR, fit, injection_board, key_board, pieces_in_top

WITHOUT = "without_"


def tuning_site_strips(sites: dict) -> dict[str, list[str]]:
    """site name -> its strips, tuning group only (controls/sites.json)."""
    return {s["name"]: list(s["strips"]) for s in sites["sites"] if s.get("group") == "tuning"}


def drop_rule(rules: ShapeRules, name: str) -> ShapeRules:
    return ShapeRules(rules.version, [r for r in rules.rules if r.name != name], rules.basis)


def _variants(fitted: ShapeRules) -> dict[str, ShapeRules | None]:
    out: dict[str, ShapeRules | None] = {"none": None, "all": fitted}
    for r in fitted.rules:
        out[WITHOUT + r.name] = drop_rule(fitted, r.name)
    return out


def _site_rows(board: dict, site: str) -> list[dict]:
    return [r for r in board["score"]["rows"] if r["size_bin"].startswith(site + "/")]


def fold(
    site: str,
    strips: list[str],
    key_cands: dict,
    answers: dict,
    thresholds: dict,
    inj_run: dict | None,
    rules: ShapeRules,
) -> dict | None:
    """One site held back: the rules re-fitted on the other strips, the held-back site's pieces scored
    under every variant (no rules, all rules, all but one), on the key and on the injection run."""
    held = {sid: e for sid, e in key_cands.get("strips", {}).items() if sid in strips}
    rest = {sid: e for sid, e in key_cands.get("strips", {}).items() if sid not in strips}
    if not held or not rest:
        return None
    fitted, rows = fit({**key_cands, "strips": rest}, answers, thresholds, rules)
    held_run = {**key_cands, "strips": held}
    held_answers = {**answers, "sites": [s for s in answers["sites"] if s["name"] == site]}
    key: dict[str, Score] = {}
    inj: dict[str, dict] = {}
    for name, variant in _variants(fitted).items():
        key[name] = key_board(held_run, held_answers, thresholds, variant)
        if inj_run is not None:
            board = injection_board(inj_run, thresholds, variant)
            inj[name] = {
                "score_threshold": board["score"]["score_threshold"],
                "rows": _site_rows(board, site),
                "sham": board["sham"],
            }
    return {
        "site": site,
        "strips": sorted(held),
        "fitted_on": sorted(rest),
        "fitted_rules": fitted.to_json(),
        "rule_rows": [
            {"name": r["name"], "test": r["test"], "pooled": r["pooled"], "gain": r["gain_if_adopted"]} for r in rows
        ],
        "key": {name: asdict(s) for name, s in key.items()},
        "key_scores": key,
        "injection": inj,
    }


def pool_key(folds: list[dict], variant: str, top_n: int) -> dict:
    """Pieces found at N over all held-back sites, by kind and in all."""
    out: dict = {"recorded": 0, "found": 0, "by_kind": {}}
    for f in folds:
        s: Score = f["key_scores"][variant]
        for p in s.pieces:
            if p.strip not in f["strips"]:
                continue
            d = out["by_kind"].setdefault(p.kind, {"recorded": 0, "found": 0})
            d["recorded"] += 1
            out["recorded"] += 1
            if p.rank is not None and p.rank <= top_n:
                d["found"] += 1
                out["found"] += 1
    out["recall"] = round(out["found"] / out["recorded"], 3) if out["recorded"] else None
    return out


def pool_injection(folds: list[dict], variant: str) -> dict | None:
    if not folds or not folds[0]["injection"]:
        return None
    out: dict = {"n": 0, "found": 0, "by_kind": {}}
    for f in folds:
        for r in f["injection"][variant]["rows"]:
            d = out["by_kind"].setdefault(r["kind"], {"n": 0, "found": 0})
            d["n"] += r["n"]
            d["found"] += r["found"]
            out["n"] += r["n"]
            out["found"] += r["found"]
    out["recall"] = round(out["found"] / out["n"], 3) if out["n"] else None
    return out


def _found(pooled: dict | None, kind: str | None) -> int:
    if pooled is None:
        return 0
    return pooled["found"] if kind is None else pooled["by_kind"].get(kind, {}).get("found", 0)


def verdict(folds: list[dict], rules: ShapeRules, top_n: int, per_strip: dict[str, dict]) -> dict:
    """Per rule, two questions kept apart. ``lift_holds`` is the plan's condition: on the sites it was not
    fitted on, leaving the rule out makes no board better and pushes no piece out of the top N.
    ``pass_fraction_stable`` is stricter than the bar as written (which pools the tuning strips): the
    fraction fitted on every fold, and on every single strip, stays at or under the bar. ``holds`` is both.
    ``per_strip`` is each rule's pass fraction per strip from the all-sites fit."""
    pooled_key = {v: pool_key(folds, v, top_n) for v in ["none", "all"] + [WITHOUT + r.name for r in rules.rules]}
    pooled_inj = {v: pool_injection(folds, v) for v in pooled_key}
    bar = BAR["max_rule_pass_fraction"]
    per_rule = {}
    for r in rules.rules:
        w = WITHOUT + r.name
        lift: list[dict] = []
        stable: list[dict] = []

        def check(where: list[dict], name: str, ok: bool, with_rule, without_rule):
            where.append({"check": name, "pass": bool(ok), "with": with_rule, "without": without_rule})

        for kind in (None, "hardware"):
            label = "all" if kind is None else kind
            a, b = _found(pooled_key["all"], kind), _found(pooled_key[w], kind)
            check(lift, f"held-out key {label} found at {top_n} is no lower with the rule", a >= b, a, b)
        if pooled_inj["all"] is not None:
            for kind in (None, "hardware"):
                label = "all" if kind is None else kind
                a, b = _found(pooled_inj["all"], kind), _found(pooled_inj[w], kind)
                check(lift, f"held-out injection {label} found is no lower with the rule", a >= b, a, b)
        pushed = []
        for f in folds:
            s_with, s_without = f["key_scores"]["all"], f["key_scores"][w]
            pushed += sorted(pieces_in_top(s_without) - pieces_in_top(s_with))
        check(lift, f"no held-out piece leaves the top {top_n} because of the rule", not pushed, [], pushed)
        fracs = {}
        for f in folds:
            row = next(x for x in f["rule_rows"] if x["name"] == r.name)
            fracs[f["site"]] = row["pooled"]["fraction"]
        worst = max((v for v in fracs.values() if v is not None), default=None)
        check(stable, f"pass fraction at most {bar} on every fold", worst is not None and worst <= bar, fracs, bar)
        strips = {sid: s["fraction"] for sid, s in per_strip.get(r.name, {}).items()}
        over = sorted(sid for sid, v in strips.items() if v is not None and v > bar)
        check(stable, f"pass fraction at most {bar} on every strip", not over, strips, over)
        lifted = []
        for f in folds:
            for p, q in zip(f["key_scores"]["all"].pieces, f["key_scores"][w].pieces, strict=True):
                if p.rank != q.rank:
                    lifted.append({"site": p.site, "piece": p.piece, "kind": p.kind, "with": p.rank, "without": q.rank})
        per_rule[r.name] = {
            "holds": all(c["pass"] for c in lift + stable),
            "lift_holds": all(c["pass"] for c in lift),
            "pass_fraction_stable": all(c["pass"] for c in stable),
            "checks": lift + stable,
            "pass_fraction_by_fold": fracs,
            "pass_fraction_by_strip": strips,
            "gain_by_fold": {f["site"]: next(x for x in f["rule_rows"] if x["name"] == r.name)["gain"] for f in folds},
            "held_out_pieces_moved": lifted,
        }
    return {"pooled_key": pooled_key, "pooled_injection": pooled_inj, "rules": per_rule}


def leave_one_site_out(
    name: str,
    key_cands: dict,
    answers: dict,
    thresholds: dict,
    inj_run: dict | None,
    rules: ShapeRules,
    site_strips: dict[str, list[str]],
) -> dict:
    folds = []
    for site, strips in site_strips.items():
        f = fold(site, strips, key_cands, answers, thresholds, inj_run, rules)
        if f is not None:
            folds.append(f)
    top_n = int(thresholds["top_n"])
    _, all_rows = fit(key_cands, answers, thresholds, rules)
    per_strip = {row["name"]: row["per_strip"] for row in all_rows}
    v = verdict(folds, rules, top_n, per_strip)
    ranks = {}
    for f in folds:
        for p in f["key_scores"]["none"].pieces:
            if p.strip not in f["strips"]:
                continue
            row = {"kind": p.kind, "none": p.rank}
            for variant, s in f["key_scores"].items():
                if variant == "none":
                    continue
                q = next(x for x in s.pieces if x.site == p.site and x.piece == p.piece)
                row[variant] = q.rank
            ranks[f"{p.site}/{p.piece}"] = row
    for f in folds:
        f.pop("key_scores")
    return {
        "name": name,
        "rules_version": rules.version,
        "top_n": top_n,
        "bar": BAR,
        "folds": folds,
        "held_out_ranks": ranks,
        **v,
    }


def _cell(p: dict | None, kind: str | None, n_key: str) -> str:
    if p is None:
        return "-"
    d = p if kind is None else p["by_kind"].get(kind, {"found": 0, n_key: 0})
    return f"{d['found']}/{d[n_key]}"


def format_loso(r: dict) -> str:
    lines = [f"leave-one-site-out, {r['rules_version']}: {len(r['folds'])} folds, pooled held-out boards", ""]
    head = f"{'variant':24s} {'key@N':>8s} {'hardware':>9s} {'fabric':>8s}"
    lines.append(head + f" {'inj':>8s} {'hardware':>9s} {'fabric':>8s}")
    for v, pk in r["pooled_key"].items():
        pi = r["pooled_injection"].get(v)
        lines.append(
            f"{v:24s} {_cell(pk, None, 'recorded'):>8s} {_cell(pk, 'hardware', 'recorded'):>9s} "
            f"{_cell(pk, 'fabric', 'recorded'):>8s} {_cell(pi, None, 'n'):>8s} {_cell(pi, 'hardware', 'n'):>9s} "
            f"{_cell(pi, 'fabric', 'n'):>8s}"
        )
    lines.append("")
    variants = list(r["pooled_key"])
    lines.append(f"{'site/piece':28s} {'kind':9s} " + " ".join(f"{v[:12]:>12s}" for v in variants))
    for key, row in r["held_out_ranks"].items():
        cells = " ".join(f"{'-' if row.get(v) is None else row[v]:>12}" for v in variants)
        lines.append(f"{key:28s} {row['kind']:9s} {cells}")
    lines.append("")
    for name, d in r["rules"].items():
        lift = "lift holds" if d["lift_holds"] else "lift does not hold"
        stable = "pass fraction stable" if d["pass_fraction_stable"] else "pass fraction not stable"
        lines.append(f"rule {name}: {'HOLDS' if d['holds'] else 'FAILS'} on held-out sites ({lift}; {stable})")
        for what in ("pass_fraction_by_fold", "pass_fraction_by_strip", "gain_by_fold"):
            lines.append(f"  {what.replace('_', ' ')}: " + ", ".join(f"{s} {v}" for s, v in d[what].items()))
        for c in d["checks"]:
            tag = "pass" if c["pass"] else "FAIL"
            lines.append(f"  [{tag}] {c['check']}: with {c['with']}, without {c['without']}")
        for m in d["held_out_pieces_moved"]:
            lines.append(f"  moved {m['site']}/{m['piece']} ({m['kind']}): {m['without']} -> {m['with']}")
    return "\n".join(lines)

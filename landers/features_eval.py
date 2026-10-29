"""Where the real pieces sit in each feature's distribution of false alarms, on the same strip.

This is the measurement that decides which shape features may enter the score (docs/plan.md item 6): a
feature earns a place only where the recorded pieces sit in the top few percent of that feature's false
alarms of the same branch on the same strip. It reads the answer key, so it belongs with the scoring side,
never inside the detector. It does not change ``landers.score``.

``measure`` returns, per recorded piece, every candidate within the match radius with its features and,
for each feature, the fraction of the strip's same-branch false alarms at or above the value (``frac_ge``)
and at or below it (``frac_le``). A false alarm is a candidate not within the match radius of any recorded
piece on that strip; on strips with no recorded piece every candidate counts as one, which overstates the
rate slightly if unrecorded hardware is present there.

With a rules file it also reports, per rule, the false-alarm pass fraction on each strip and pooled over
the run, and whether each piece candidate passes; ``fitted_rules`` is the rules file with the pooled
fraction and the gain ``-log10(p)`` filled in, ready to be copied to ``landers/shape_v<n>.json``.
"""

from __future__ import annotations

import bisect
import math

from landers.score import match_radius_px

SKIP_KEYS = {"also", "raw_score", "shape_pass", "shape_gain"}
FLOOR_PASSES = 0.5  # when no false alarm passes a rule, p is taken as half a count over the count


def _numeric_features(extra: dict) -> dict:
    out = {}
    for k, v in (extra or {}).items():
        if k in SKIP_KEYS or isinstance(v, bool | str | list | dict) or v is None:
            continue
        out[k] = float(v)
    return out


def _within(c: dict, truths: list[tuple[float, float]], radius: float) -> bool:
    return any(math.hypot(float(c["row"]) - r, float(c["col"]) - k) <= radius for r, k in truths)


def measure(candidates: dict, answers: dict, thresholds: dict, rules=None) -> dict:
    strips = candidates.get("strips", {})
    truth_by_strip: dict[str, list[tuple[str, str, float, float]]] = {}
    for site in answers["sites"]:
        for pc in site["pieces"]:
            if pc.get("line") is None or pc.get("sample") is None or pc.get("strip") is None:
                continue
            truth_by_strip.setdefault(pc["strip"], []).append(
                (site["name"], pc["piece"], float(pc["line"]) - 1.0, float(pc["sample"]) - 1.0)
            )

    pieces = []
    fa_values: dict[str, dict[str, dict[str, list[float]]]] = {}  # strip -> branch -> feature -> sorted values
    fa_counts: dict[str, dict[str, int]] = {}
    fa_extras: dict[str, dict[str, list[dict]]] = {}  # strip -> branch -> extras (for rule pass fractions)
    for sid, entry in strips.items():
        radius = match_radius_px(thresholds, entry.get("scale_m", 0.25))
        truths = truth_by_strip.get(sid, [])
        pts = [(r, c) for _, _, r, c in truths]
        ranked = sorted(entry.get("candidates", []), key=lambda c: -float(c.get("score", 0.0)))
        per_branch: dict[str, dict[str, list[float]]] = {}
        counts: dict[str, int] = {}
        extras: dict[str, list[dict]] = {}
        hits: dict[int, dict] = {}
        for i, c in enumerate(ranked, start=1):
            if pts and _within(c, pts, radius):
                hits[i] = c
                continue
            b = c["branch"]
            counts[b] = counts.get(b, 0) + 1
            extras.setdefault(b, []).append(c.get("extra") or {})
            for k, v in _numeric_features(c.get("extra")).items():
                per_branch.setdefault(b, {}).setdefault(k, []).append(v)
        for b in per_branch:
            for k in per_branch[b]:
                per_branch[b][k].sort()
        fa_values[sid], fa_counts[sid], fa_extras[sid] = per_branch, counts, extras

        for site, piece, r, k in truths:
            within = []
            for i, c in hits.items():
                d = math.hypot(float(c["row"]) - r, float(c["col"]) - k)
                if d > radius:
                    continue
                b = c["branch"]
                feats = _numeric_features(c.get("extra"))
                pct = {}
                for name, v in feats.items():
                    vals = per_branch.get(b, {}).get(name, [])
                    if not vals:
                        pct[name] = None
                        continue
                    n = len(vals)
                    ge = (n - bisect.bisect_left(vals, v)) / n
                    le = bisect.bisect_right(vals, v) / n
                    pct[name] = {"value": v, "frac_ge": round(ge, 4), "frac_le": round(le, 4), "n_false": n}
                rec = {
                    "rank": i,
                    "branch": b,
                    "score": c.get("score"),
                    "raw_score": (c.get("extra") or {}).get("raw_score"),
                    "distance_px": round(d, 1),
                    "features": pct,
                }
                if rules is not None:
                    rec["rules"] = {ru.name: ru.passes(b, c.get("extra") or {}) for ru in rules.rules}
                within.append(rec)
            within.sort(key=lambda x: x["rank"])
            pieces.append({"site": site, "piece": piece, "strip": sid, "candidates": within})

    out = {"pieces": pieces, "false_alarms_by_strip": {sid: fa_counts[sid] for sid in strips}}
    if rules is not None:
        out["rules"] = _rule_stats(rules, fa_extras, fa_counts, pieces)
    return out


def _rule_stats(rules, fa_extras, fa_counts, pieces) -> dict:
    rows = []
    fitted = []
    for ru in rules.rules:
        per_strip = {}
        n_all = p_all = 0
        for sid, by_branch in fa_extras.items():
            n = p = 0
            for b in ru.branches:
                for extra in by_branch.get(b, []):
                    r = ru.passes(b, extra)
                    if r is None:
                        continue
                    n += 1
                    p += int(r)
            if n:
                per_strip[sid] = {"n_false": n, "n_pass": p, "fraction": round(p / n, 5)}
            n_all += n
            p_all += p
        frac = (p_all / n_all) if n_all else None
        p_eff = (max(p_all, FLOOR_PASSES) / n_all) if n_all else None
        gain = round(-math.log10(p_eff), 3) if p_eff else 0.0
        piece_pass = []
        for pc in pieces:
            for c in pc["candidates"]:
                r = c.get("rules", {}).get(ru.name)
                if r is not None:
                    piece_pass.append(
                        {"site": pc["site"], "piece": pc["piece"], "branch": c["branch"], "rank": c["rank"], "pass": r}
                    )
        n_pp = sum(1 for x in piece_pass if x["pass"])
        rows.append(
            {
                "name": ru.name,
                "test": str(ru),
                "branches": ru.branches,
                "pooled": {"n_false": n_all, "n_pass": p_all, "fraction": None if frac is None else round(frac, 5)},
                "gain_if_adopted": gain,
                "per_strip": per_strip,
                "piece_candidates": piece_pass,
                "piece_candidates_passing": f"{n_pp}/{len(piece_pass)}",
            }
        )
        fitted.append(
            {**ru.to_json(), "false_alarm_pass_fraction": None if frac is None else round(frac, 5), "gain": gain}
        )
    return {"rows": rows, "fitted_rules": {"version": rules.version, "basis": rules.basis, "rules": fitted}}


def format_pieces(m: dict, features: tuple[str, ...]) -> str:
    lines = [f"{'site':13s} {'piece':13s} {'branch':12s} {'rank':>6s} {'d px':>5s}  " + "  ".join(features)]
    for pc in m["pieces"]:
        if not pc["candidates"]:
            lines.append(f"{pc['site']:13s} {pc['piece']:13s} {'(none within radius)':12s}")
            continue
        for c in pc["candidates"]:
            cells = []
            for f in features:
                p = c["features"].get(f)
                if not p:
                    cells.append("-")
                else:
                    cells.append(f"{p['value']:g}({p['frac_ge']:.3f}/{p['frac_le']:.3f})")
            lines.append(
                f"{pc['site']:13s} {pc['piece']:13s} {c['branch']:12s} {c['rank']:6d} {c['distance_px']:5.1f}  "
                + "  ".join(cells)
            )
    return "\n".join(lines)


def format_rules(m: dict) -> str:
    lines = []
    for r in m.get("rules", {}).get("rows", []):
        po = r["pooled"]
        lines.append(
            f"{r['test']} [{','.join(r['branches'])}]: false alarms pass "
            f"{po['n_pass']}/{po['n_false']} = {po['fraction']}  gain {r['gain_if_adopted']}  "
            f"pieces pass {r['piece_candidates_passing']}"
        )
        for sid, s in r["per_strip"].items():
            lines.append(f"    {sid}: {s['n_pass']}/{s['n_false']} = {s['fraction']}")
        for x in r["piece_candidates"]:
            lines.append(
                f"    {x['site']}/{x['piece']} ({x['branch']}, rank {x['rank']}): {'pass' if x['pass'] else 'fail'}"
            )
    return "\n".join(lines)

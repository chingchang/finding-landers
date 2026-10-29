"""The tuning judge: offline rule application equals the detector's, the bar is applied as written."""

import json

from landers import tune
from landers.detect import Candidate, DetectorConfig, finish_tile
from landers.shape import ShapeRules

THRESHOLDS = {
    "match_radius_m": 5.0,
    "match_radius_m_by_kind": {"mark": 20.0},
    "piece_kinds": {"hardware": ["lander", "backshell"], "fabric": ["parachute"], "mark": ["crash_scar"]},
    "top_n": 3,
    "pass": {"min_recall_at_n": 0.8, "max_false_alarms_per_km2": 2.0},
}


def cand(row, col, score, branch="bright", **feats):
    return {
        "row": row,
        "col": col,
        "score": score,
        "branch": branch,
        "grade": "needs second look",
        "area_px": 9,
        "extra": feats,
    }


def key_run():
    """Two strips. Strip A: the lander at (100, 100) sits at rank 5 just behind four false alarms; it is the
    only candidate there with crisp edges. Strip B: a backshell at rank 1 and nine false alarms, three crisp."""
    a = [cand(100, 100, 1.9, edge_sharpness=0.5, saturated_px=0)]
    a += [cand(300 + 20 * i, 300, 2.0 + 0.1 * i, edge_sharpness=0.1, saturated_px=0) for i in range(4)]
    b = [cand(50, 50, 9.0, edge_sharpness=0.1, saturated_px=3)]
    b += [
        cand(400 + 20 * i, 400, 1.0 + i * 0.5, edge_sharpness=0.5 if i < 3 else 0.1, saturated_px=0) for i in range(9)
    ]
    return {
        "run": "fake",
        "detector": {"version": "v0.2", "shape_rules": None},
        "strips": {
            "A": {"valid_area_km2": 10.0, "scale_m": 0.25, "candidates": a},
            "B": {"valid_area_km2": 10.0, "scale_m": 0.25, "candidates": b},
        },
    }


ANSWERS = {
    "sites": [
        {"name": "one", "pieces": [{"piece": "lander", "strip": "A", "line": 101, "sample": 101}]},
        {"name": "two", "pieces": [{"piece": "backshell", "strip": "B", "line": 51, "sample": 51}]},
    ]
}


def injection_run():
    """One tile, 1 km2, two real plantings and one sham; five detections, three of them false alarms, so at
    2 per km2 the threshold falls on the third false alarm (0.8) and the lander (0.5) is below it unless lifted."""
    dets = [
        {
            "tile": "T:0:0",
            "row": 100.0,
            "col": 100.0,
            "score": 0.5,
            "branch": "bright",
            "area_px": 9,
            "features": {"edge_sharpness": 0.5},
        },
        {
            "tile": "T:0:0",
            "row": 300.0,
            "col": 300.0,
            "score": 0.8,
            "branch": "bright",
            "area_px": 9,
            "features": {"edge_sharpness": 0.1},
        },
        {
            "tile": "T:0:0",
            "row": 500.0,
            "col": 500.0,
            "score": 1.0,
            "branch": "bright",
            "area_px": 9,
            "features": {"edge_sharpness": 0.1},
        },
        {
            "tile": "T:0:0",
            "row": 700.0,
            "col": 700.0,
            "score": 2.0,
            "branch": "bright",
            "area_px": 9,
            "features": {"edge_sharpness": 0.1},
        },
        {
            "tile": "T:0:0",
            "row": 900.0,
            "col": 900.0,
            "score": 3.0,
            "branch": "bright",
            "area_px": 9,
            "features": {"edge_sharpness": 0.1},
        },
    ]
    cuts = [{"size_m": 3.0, "scale_m": 0.25}, {"size_m": 12.0, "scale_m": 0.25}]
    placements = [
        {
            "tile": "T:0:0",
            "row": 100.0,
            "col": 100.0,
            "cut_index": 0,
            "site": "one",
            "piece": "lander",
            "kind": "hardware",
            "sham": False,
            "match_radius_px": 20.0,
        },
        {
            "tile": "T:0:0",
            "row": 500.0,
            "col": 500.0,
            "cut_index": 1,
            "site": "one",
            "piece": "parachute",
            "kind": "fabric",
            "sham": False,
            "match_radius_px": 20.0,
        },
        {
            "tile": "T:0:0",
            "row": 900.0,
            "col": 900.0,
            "cut_index": 0,
            "site": "one",
            "piece": "lander",
            "kind": "hardware",
            "sham": True,
            "match_radius_px": 20.0,
        },
    ]
    return {
        "detector": {"shape_rules": None},
        "area_km2": 1.0,
        "fa_per_km2_target": 2.0,
        "cuts": cuts,
        "placements": placements,
        "detections": dets,
    }


def rules_json(name, feature, op, threshold, branches=("bright", "shadow")):
    return {
        "version": name,
        "rules": [
            {
                "name": name,
                "branches": list(branches),
                "conditions": [{"feature": feature, "op": op, "threshold": threshold}],
            }
        ],
    }


def test_fit_measures_pass_fraction_and_gain_on_the_key_false_alarms():
    rules = ShapeRules.from_json(rules_json("crisp", "edge_sharpness", ">=", 0.4))
    fitted, rows = tune.fit(key_run(), ANSWERS, THRESHOLDS, rules)
    # 13 false alarms (4 on A, 9 on B), 3 crisp ones on B
    assert rows[0]["pooled"] == {"n_false": 13, "n_pass": 3, "fraction": round(3 / 13, 5)}
    assert fitted.rules[0].false_alarm_pass_fraction == round(3 / 13, 5)
    assert abs(fitted.rules[0].gain - 0.637) < 0.001


def test_offline_application_matches_the_detector_finish():
    rules = ShapeRules.from_json(
        {
            "version": "x",
            "rules": [
                {
                    "name": "crisp",
                    "branches": ["bright"],
                    "gain": 0.7,
                    "conditions": [{"feature": "edge_sharpness", "op": ">=", "threshold": 0.4}],
                }
            ],
        }
    )
    cands = [
        Candidate(1.0, 2.0, 0.5, "bright", "needs second look", 9, {"edge_sharpness": 0.5}),
        Candidate(3.0, 4.0, 1.0, "bright", "needs second look", 9, {"edge_sharpness": 0.1}),
    ]
    in_process = finish_tile(cands, DetectorConfig(), None, rules)
    dets = [
        {"tile": "t", "row": c.row, "col": c.col, "score": c.score, "branch": c.branch, "features": dict(c.extra)}
        for c in cands
    ]
    offline = tune.apply_to_detections(dets, rules)
    assert [round(c.score, 4) for c in in_process] == [d["score"] for d in offline]
    assert offline[0]["features"]["shape_pass"] == ["crisp"] and "shape_pass" not in offline[1]["features"]


def test_a_rule_that_lifts_the_lander_on_both_boards_still_fails_the_pass_fraction_bar():
    # crisp edges lift the lander to rank 1 on the key and above the injection threshold, but 3 of 13 false
    # alarms (0.23) pass the test, above the bar's 0.05: the verdict is REVERT on that check alone
    r = tune.compare(
        "crisp",
        key_run(),
        ANSWERS,
        THRESHOLDS,
        injection_run(),
        None,
        ShapeRules.from_json(rules_json("crisp", "edge_sharpness", ">=", 0.4)),
    )
    assert r["key"]["ranks"]["one/lander"] == {"kind": "hardware", "reference": 5, "candidate": 1, "branch": "bright"}
    assert (
        r["injection"]["pieces"]["one/lander"]["reference"] == 0
        and r["injection"]["pieces"]["one/lander"]["candidate"] == 1
    )
    assert not r["keep"]
    failed = [c["check"] for c in r["checks"] if not c["pass"]]
    assert failed == ["new rule crisp passes at most 0.05 of false alarms"]
    assert "crisp: key recall@3 2/2 (hardware 2/2) against 1/2 (hardware 1/2)" in tune.summary_line(r)
    assert "REVERT" in tune.format_compare(r)


def test_a_harmless_rule_is_kept_and_a_rule_that_lifts_false_alarms_is_reverted():
    # saturation: no false alarm has it, but neither does the lander; on strip B nothing moves. Harmless: kept.
    sat = ShapeRules.from_json(rules_json("sat", "saturated_px", ">=", 1))
    r = tune.compare("sat", key_run(), ANSWERS, THRESHOLDS, injection_run(), None, sat)
    assert r["keep"], [c for c in r["checks"] if not c["pass"]]
    # a rule that lifts the four false alarms of strip A above the lander, while the lander stays unmatched
    dull = ShapeRules.from_json(rules_json("dull", "edge_sharpness", "<=", 0.2))
    r = tune.compare("dull", key_run(), ANSWERS, THRESHOLDS, injection_run(), sat, dull)
    assert not r["keep"]
    assert r["new_rules"] == ["dull"]
    assert any(c["check"] == "injection recall does not drop" and not c["pass"] for c in r["checks"]) or any(
        "passes at most" in c["check"] and not c["pass"] for c in r["checks"]
    )


def test_reference_rules_are_not_new_and_a_changed_threshold_is():
    ref = ShapeRules.from_json(rules_json("sat", "saturated_px", ">=", 1))
    same = ShapeRules.from_json(rules_json("sat", "saturated_px", ">=", 1))
    changed = ShapeRules.from_json(rules_json("sat", "saturated_px", ">=", 5))
    assert tune.new_rules(same, ref) == []
    assert tune.new_rules(changed, ref) == ["sat"]
    assert tune.new_rules(same, None) == ["sat"]


def test_a_detector_change_is_judged_from_the_candidate_runs_with_rules_re_measured():
    """A detector change gives new runs; the candidate board comes from them and the reference's own rules
    are re-measured on the new key run and held to the pass-fraction bar."""
    sat = ShapeRules.from_json(rules_json("sat", "saturated_px", ">=", 1))
    new_key = key_run()
    new_key["strips"]["A"]["candidates"][0]["score"] = 5.0  # the new detector lifts the lander on strip A
    new_inj = injection_run()
    new_inj["detections"][0]["score"] = 2.5  # the planted lander now clears the threshold
    r = tune.compare(
        "det", key_run(), ANSWERS, THRESHOLDS, injection_run(), sat, None, cand_key_cands=new_key, cand_inj_run=new_inj
    )
    assert r["detector_change"] and r["new_rules"] == []
    assert r["key"]["ranks"]["one/lander"]["reference"] == 5 and r["key"]["ranks"]["one/lander"]["candidate"] == 1
    assert r["injection"]["pieces"]["one/lander"] == {"kind": "hardware", "n": 1, "reference": 0, "candidate": 1}
    assert r["keep"], [c for c in r["checks"] if not c["pass"]]
    assert any(c["check"].startswith("re-measured rule sat") for c in r["checks"])
    # the same change under a rule most false alarms pass: held to the bar although the rule is not new
    dull = ShapeRules.from_json(rules_json("dull", "edge_sharpness", "<=", 0.2))
    r2 = tune.compare(
        "det2",
        key_run(),
        ANSWERS,
        THRESHOLDS,
        injection_run(),
        dull,
        dull,
        cand_key_cands=new_key,
        cand_inj_run=new_inj,
    )
    assert any(c["check"].startswith("re-measured rule dull") and not c["pass"] for c in r2["checks"])


def test_judging_from_a_ruled_run_is_refused():
    run = injection_run()
    run["detector"]["shape_rules"] = "landers/shape_v1.json"
    try:
        tune.injection_board(run, THRESHOLDS, None)
    except ValueError as e:
        assert "unruled" in str(e)
    else:
        raise AssertionError("a ruled run was accepted")


def test_script_writes_the_result(tmp_path):
    from scripts import tune as script

    key = tmp_path / "key.json"
    key.write_text(json.dumps(key_run()))
    inj = tmp_path / "inj.json"
    inj.write_text(json.dumps(injection_run()))
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps(ANSWERS))
    thr = tmp_path / "thr.json"
    thr.write_text(json.dumps(THRESHOLDS))
    rules = tmp_path / "crisp.json"
    rules.write_text(json.dumps(rules_json("crisp", "edge_sharpness", ">=", 0.4)))
    rc = script.main(
        [
            "--name",
            "crisp",
            "--rules",
            str(rules),
            "--no-reference-rules",
            "--key-candidates",
            str(key),
            "--injection",
            str(inj),
            "--answers",
            str(answers),
            "--thresholds",
            str(thr),
            "--out",
            str(tmp_path / "tune"),
        ]
    )
    assert rc == 0
    r = json.loads((tmp_path / "tune" / "crisp" / "tune_crisp.json").read_text())
    assert r["keep"] is False and r["inputs"]["candidate_rules"] == str(rules)
    fitted = json.loads((tmp_path / "tune" / "crisp" / "crisp_fitted_rules.json").read_text())
    assert fitted["rules"][0]["false_alarm_pass_fraction"] == round(3 / 13, 5)

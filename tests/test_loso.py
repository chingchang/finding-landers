"""The leave-one-site-out check: gains are fitted without the held-back site, lift is judged by ablation."""

import json

from landers import loso
from landers.shape import ShapeRules
from tests.test_tune import ANSWERS, THRESHOLDS, injection_run, key_run, rules_json

SITES = {
    "sites": [
        {"name": "one", "group": "tuning", "strips": ["A"]},
        {"name": "two", "group": "tuning", "strips": ["B"]},
        {"name": "sealed", "group": "heldout", "strips": ["Z"]},
    ]
}


def test_tuning_sites_only():
    assert loso.tuning_site_strips(SITES) == {"one": ["A"], "two": ["B"]}


def test_gains_come_from_the_other_site_and_the_lift_is_judged_held_out():
    # crisp edges: fitted on B (3 of 9 false alarms) when A is held back, gain 0.477, enough to lift the
    # lander from rank 5 to 1 on A and the lander planting above the injection threshold; fitted on A
    # (0 of 4, floored) when B is held back, where nothing moves. The lift holds; the pass fraction on the
    # B fold (0.333) is over the bar, so the rule fails as written.
    rules = ShapeRules.from_json(rules_json("crisp", "edge_sharpness", ">=", 0.4))
    r = loso.leave_one_site_out(
        "crisp", key_run(), ANSWERS, THRESHOLDS, injection_run(), rules, {"one": ["A"], "two": ["B"]}
    )
    assert [f["site"] for f in r["folds"]] == ["one", "two"]
    f_one, f_two = r["folds"]
    assert f_one["fitted_on"] == ["B"] and f_one["rule_rows"][0]["pooled"] == {
        "n_false": 9,
        "n_pass": 3,
        "fraction": round(3 / 9, 5),
    }
    assert f_two["fitted_on"] == ["A"] and f_two["rule_rows"][0]["pooled"]["n_pass"] == 0
    assert r["held_out_ranks"]["one/lander"] == {"kind": "hardware", "none": 5, "all": 1, "without_crisp": 5}
    assert r["held_out_ranks"]["two/backshell"] == {"kind": "hardware", "none": 1, "all": 1, "without_crisp": 1}
    assert r["pooled_key"]["all"]["found"] == 2 and r["pooled_key"]["without_crisp"]["found"] == 1
    assert r["pooled_injection"]["all"]["found"] == 2 and r["pooled_injection"]["without_crisp"]["found"] == 1
    d = r["rules"]["crisp"]
    assert not d["holds"]
    failed = [c["check"] for c in d["checks"] if not c["pass"]]
    assert failed == ["pass fraction at most 0.05 on every fold", "pass fraction at most 0.05 on every strip"]
    assert d["lift_holds"] and not d["pass_fraction_stable"]
    assert d["pass_fraction_by_strip"] == {"A": 0.0, "B": round(3 / 9, 5)}
    assert d["pass_fraction_by_fold"] == {"one": round(3 / 9, 5), "two": 0.0}
    assert d["held_out_pieces_moved"] == [
        {"site": "one", "piece": "lander", "kind": "hardware", "with": 1, "without": 5}
    ]
    text = loso.format_loso(r)
    assert "rule crisp: FAILS" in text and "one/lander" in text


def test_a_rule_nothing_passes_holds_and_a_harmful_rule_fails():
    sat = ShapeRules.from_json(rules_json("sat", "saturated_px", ">=", 1))
    r = loso.leave_one_site_out("sat", key_run(), ANSWERS, THRESHOLDS, None, sat, {"one": ["A"], "two": ["B"]})
    assert r["rules"]["sat"]["holds"], r["rules"]["sat"]["checks"]
    assert r["pooled_injection"] == {"none": None, "all": None, "without_sat": None}
    # dull edges lift A's four false alarms (fitted on B: 6 of 9 pass, gain 0.176) but not the lander,
    # which stays at rank 5; on B the backshell (dull) keeps rank 1. No held-out piece moves, the pass
    # fraction fails on both folds
    dull = ShapeRules.from_json(rules_json("dull", "edge_sharpness", "<=", 0.2))
    r = loso.leave_one_site_out("dull", key_run(), ANSWERS, THRESHOLDS, None, dull, {"one": ["A"], "two": ["B"]})
    assert not r["rules"]["dull"]["holds"]
    assert r["held_out_ranks"]["one/lander"]["all"] == 5


def test_a_site_with_no_strip_in_the_run_is_skipped():
    rules = ShapeRules.from_json(rules_json("sat", "saturated_px", ">=", 1))
    r = loso.leave_one_site_out(
        "sat", key_run(), ANSWERS, THRESHOLDS, None, rules, {"one": ["A"], "two": ["B"], "x": ["Q"]}
    )
    assert [f["site"] for f in r["folds"]] == ["one", "two"]


def test_script_writes_the_result(tmp_path):
    from scripts import loso as script

    key = tmp_path / "key.json"
    key.write_text(json.dumps(key_run()))
    inj = tmp_path / "inj.json"
    inj.write_text(json.dumps(injection_run()))
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps(ANSWERS))
    thr = tmp_path / "thr.json"
    thr.write_text(json.dumps(THRESHOLDS))
    sites = tmp_path / "sites.json"
    sites.write_text(json.dumps(SITES))
    rules = tmp_path / "crisp.json"
    rules.write_text(json.dumps(rules_json("crisp", "edge_sharpness", ">=", 0.4)))
    rc = script.main(
        [
            "--name",
            "crisp",
            "--rules",
            str(rules),
            "--key-candidates",
            str(key),
            "--injection",
            str(inj),
            "--answers",
            str(answers),
            "--thresholds",
            str(thr),
            "--sites",
            str(sites),
            "--out",
            str(tmp_path / "loso"),
        ]
    )
    assert rc == 0
    r = json.loads((tmp_path / "loso" / "crisp" / "loso_crisp.json").read_text())
    assert r["rules"]["crisp"]["holds"] is False and r["inputs"]["rules"] == str(rules)
    assert "key_scores" not in r["folds"][0]

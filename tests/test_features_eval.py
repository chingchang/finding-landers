import json

from landers.features_eval import format_pieces, format_rules, measure
from landers.shape import ShapeRules

THRESHOLDS = {"match_radius_m": 5.0, "top_n": 20}


def _run():
    def cand(row, col, score, branch, **feats):
        return {"row": row, "col": col, "score": score, "branch": branch, "extra": feats}

    falses = [
        cand(1000 + 50 * i, 1000, 1.0 - i * 0.01, "bright", two_sided=float(i % 5), isolation_px=10.0 * i)
        for i in range(20)
    ]
    hit = cand(101, 201, 0.5, "bright", two_sided=4.0, isolation_px=256.0)
    return {
        "run": "t",
        "detector": {},
        "strips": {"S": {"valid_area_km2": 1.0, "scale_m": 0.25, "candidates": falses + [hit]}},
    }


def _key():
    return {"sites": [{"name": "site", "pieces": [{"piece": "lander", "strip": "S", "line": 102, "sample": 202}]}]}


def test_measure_reports_fraction_of_false_alarms_at_or_above_piece_value():
    m = measure(_run(), _key(), THRESHOLDS)
    (pc,) = m["pieces"]
    (c,) = pc["candidates"]
    assert c["branch"] == "bright" and c["rank"] == 21 and c["distance_px"] < 2
    ts = c["features"]["two_sided"]
    assert ts["n_false"] == 20 and ts["frac_ge"] == 4 / 20  # four false alarms have two_sided == 4
    iso = c["features"]["isolation_px"]
    assert iso["frac_ge"] == 0.0 and iso["frac_le"] == 1.0  # no false alarm is as isolated as the piece
    assert m["false_alarms_by_strip"]["S"] == {"bright": 20}
    assert "lander" in format_pieces(m, ("two_sided", "isolation_px"))


def test_rule_stats_and_fitted_gain(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(
        json.dumps(
            {
                "version": "shape_t",
                "rules": [
                    {
                        "name": "two_sided",
                        "branches": ["bright"],
                        "conditions": [{"feature": "two_sided", "op": "in", "threshold": [4.0, 9.0]}],
                    },
                    {
                        "name": "isolated",
                        "branches": ["bright"],
                        "conditions": [{"feature": "isolation_px", "op": ">=", "threshold": 250.0}],
                    },
                ],
            }
        )
    )
    m = measure(_run(), _key(), THRESHOLDS, ShapeRules.load(p))
    r0, r1 = m["rules"]["rows"]
    assert r0["pooled"] == {"n_false": 20, "n_pass": 4, "fraction": 0.2} and r0["gain_if_adopted"] == 0.699
    assert r0["piece_candidates_passing"] == "1/1"
    assert r1["pooled"]["n_pass"] == 0 and r1["gain_if_adopted"] == 1.602  # floor: half a count over 20
    fitted = m["rules"]["fitted_rules"]["rules"]
    assert fitted[0]["false_alarm_pass_fraction"] == 0.2 and fitted[0]["gain"] == 0.699
    assert fitted[0]["name"] == "two_sided" and fitted[0]["conditions"][0]["threshold"] == [4.0, 9.0]
    assert "pieces pass 1/1" in format_rules(m)

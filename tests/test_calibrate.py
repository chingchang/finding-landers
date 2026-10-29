import itertools
import math

from landers import calibrate
from landers.detect import Candidate


def _run(branch_scores: dict, area: float, tile="t"):
    dets = []
    for b, scores in branch_scores.items():
        for i, s in enumerate(scores):
            dets.append({"tile": tile, "row": 1000 + 50 * i, "col": 1000 + 50 * i, "score": s, "branch": b})
    truths = [{"tile": tile, "row": 5, "col": 5, "kind": "sheet", "size_m": 10}]
    dets.append({"tile": tile, "row": 6, "col": 5, "score": 99.0, "branch": "sheet"})  # a hit, not a false alarm
    return {
        "area_km2": area,
        "n_tiles": 1,
        "match_radius_px": 10.0,
        "sites": ["x"],
        "detections": dets,
        "truths": truths,
    }


def test_fit_rates_and_monotone_mapping():
    run = _run({"bright": [9.0, 8.0, 8.0, 6.0, 5.0], "sheet": [4.0]}, area=2.0)
    cal = calibrate.fit([run], "t")
    b = cal.branches["bright"]
    assert b.n == 5 and b.scores == [9.0, 8.0, 6.0, 5.0]
    # at raw 8.0 three false alarms have score >= 8 over 2 km2: rate 1.5/km2
    assert math.isclose(10 ** b.log_rates[1], 1.5)
    assert b.slope < 0
    xs = [3.0, 5.0, 5.5, 6.0, 8.0, 9.0, 12.0]
    ys = [cal.calibrated("bright", x) for x in xs]
    assert all(y1 < y2 for y1, y2 in itertools.pairwise(ys))
    # the hit (score 99 in sheet) was not counted as a false alarm
    assert cal.branches["sheet"].n == 1
    # a branch never seen as a false alarm is as rare as the floor
    assert cal.calibrated("dark_compact", 5.0) > cal.calibrated("bright", 9.0)


def test_common_scale_reorders_branches():
    # bright false alarms are common at raw 8; sheet false alarms never reach raw 4
    run = _run({"bright": [9.0, 8.5, 8.0, 8.0, 7.5, 7.0], "sheet": [3.0, 2.5]}, area=1.0)
    cal = calibrate.fit([run], "t")
    cands = [
        Candidate(0, 0, 8.0, "bright", "needs second look", 9),
        Candidate(0, 0, 4.4, "sheet", "needs second look", 200),
    ]
    out = calibrate.apply(cands, cal)
    assert out[1].score > out[0].score  # the sheet at 4.4 is rarer than a bright at 8.0
    assert out[0].extra["raw_score"] == 8.0


def test_save_load_roundtrip(tmp_path):
    run = _run({"bright": [9.0, 8.0], "dark": [5.0, 4.0, 3.0]}, area=1.5)
    cal = calibrate.fit([run], "t")
    cal.save(tmp_path / "c.json")
    back = calibrate.Calibration.load(tmp_path / "c.json")
    for b in ("bright", "dark", "unseen"):
        for x in (2.0, 4.4, 8.0, 20.0):
            assert math.isclose(back.calibrated(b, x), cal.calibrated(b, x), abs_tol=2e-3)  # json rounds to 4 places


def test_fit_refuses_calibrated_runs():
    import pytest

    run = _run({"bright": [9.0, 8.0]}, area=1.0)
    run["detector"] = {"calibration": "x.json"}
    with pytest.raises(ValueError):
        calibrate.fit([run], "t")


def test_fit_caps_knots_but_keeps_the_top_exact():
    scores = {"bright": [float(x) / 10 for x in range(4000, 40, -1)]}
    cal = calibrate.fit([_run(scores, area=10.0)], "t")
    b = cal.branches["bright"]
    assert len(b.scores) <= calibrate.MAX_KNOTS
    assert b.scores[:3] == [400.0, 399.9, 399.8] and b.n == len(scores["bright"])


def test_fit_strip_from_candidates_and_dicts_and_top_exclude():
    """v0.4: a strip's own population fits its curve; the top candidate is one per strip area unless the top
    is left out of the knots and scored by the extrapolated tail."""
    cands = [Candidate(0, 0, float(s), "bright", "needs second look", 9) for s in range(4, 40)]
    cands.append(Candidate(0, 0, 80.0, "bright", "needs second look", 9))  # far above the crowd
    cal0 = calibrate.fit_strip(cands, area_km2=10.0)
    top = max(cands, key=lambda c: c.score)
    assert math.isclose(cal0.calibrated("bright", top.score), math.log10(10.0) + calibrate.TIE_BREAK * 80.0)
    assert cal0.branches["bright"].n == len(cands)
    cal5 = calibrate.fit_strip(cands, area_km2=10.0, top_exclude=5)
    assert cal5.branches["bright"].n == len(cands) and cal5.branches["bright"].scores[0] == 35.0
    assert cal5.calibrated("bright", 80.0) > cal0.calibrated("bright", 80.0)
    # the rate below the excluded top is what the whole population says: six candidates at or above 35
    assert math.isclose(10 ** -(cal5.calibrated("bright", 35.0) - calibrate.TIE_BREAK * 35.0), 6 / 10.0)
    dicts = [{"branch": "bright", "score": -1.0, "extra": {"raw_score": c.score}} for c in cands]
    assert calibrate.fit_strip(dicts, 10.0).to_json() == cal0.to_json()


def test_strip_calibrations_roundtrip(tmp_path):
    a = calibrate.fit_strip([Candidate(0, 0, s, "dark", "g", 9) for s in (3.0, 2.0, 1.0)], 2.0)
    b = calibrate.fit_strip([Candidate(0, 0, s, "sheet", "g", 9) for s in (5.0, 4.0)], 3.0)
    sc = calibrate.StripCalibrations("t", {"S1": a, "S2": b}, top_exclude=1, basis="test", min_population=2)
    sc.save(tmp_path / "sc.json")
    back = calibrate.StripCalibrations.load(tmp_path / "sc.json")
    assert back.top_exclude == 1 and back.min_population == 2 and set(back.strips) == {"S1", "S2"}
    assert math.isclose(back.strips["S2"].calibrated("sheet", 4.4), b.calibrated("sheet", 4.4), abs_tol=2e-3)


def test_thin_branches_get_no_curve_and_score_by_the_fallback_table():
    """A branch with fewer candidates than min_population on a strip is left without a curve; with a fallback
    table attached its candidates score as the table says, and without one they score the floor constant."""
    table = calibrate.fit_scores({"bright": [float(s) for s in range(4, 30)], "sheet": [3.0, 4.0, 5.0]}, 20.0, "v0")
    strip = {"bright": [float(s) for s in range(4, 60)], "sheet": [3.5, 4.6]}
    cal = calibrate.fit_scores(strip, 5.0, "per_strip", min_population=10)
    assert set(cal.branches) == {"bright"} and cal.thin == {"sheet": 2} and cal.min_population == 10
    floor_scored = cal.calibrated("sheet", 4.6)
    assert math.isclose(floor_scored, math.log10(10.0) + calibrate.TIE_BREAK * 4.6)
    cal.fallback = table
    assert math.isclose(cal.calibrated("sheet", 4.6), table.calibrated("sheet", 4.6))
    assert math.isclose(cal.calibrated("bright", 50.0), cal.branches["bright"].calibrated(50.0))
    d = cal.to_json()
    assert d["thin"] == {"sheet": 2} and d["fallback"] == "v0" and "sheet" not in d["branches"]
    back = calibrate.Calibration.from_json(d)
    assert back.thin == {"sheet": 2} and back.min_population == 10 and back.fallback is None
    sc = calibrate.StripCalibrations("t", {"S": back}, min_population=10)
    sc.attach_fallback(table)
    assert math.isclose(sc.strips["S"].calibrated("sheet", 4.6), table.calibrated("sheet", 4.6))
    # the same candidates through fit_strip
    cands = [Candidate(0, 0, s, "bright", "g", 9) for s in strip["bright"]]
    cands += [Candidate(0, 0, s, "sheet", "g", 9) for s in strip["sheet"]]
    via = calibrate.fit_strip(cands, 5.0, min_population=10, fallback=table)
    assert via.thin == {"sheet": 2} and math.isclose(via.calibrated("sheet", 4.6), table.calibrated("sheet", 4.6))

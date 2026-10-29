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

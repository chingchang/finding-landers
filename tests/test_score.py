from landers.score import format_report, score

THRESH = {"match_radius_px": 20, "top_n": 3, "pass": {"min_recall_at_n": 0.5, "max_false_alarms_per_km2": 2.0}}

ANSWERS = {
    "sites": [
        {
            "name": "siteA",
            "pieces": [
                {"piece": "lander", "strip": "S1", "line": 1001, "sample": 2001},
                {"piece": "chute", "strip": "S1", "line": 5000, "sample": 6000},
                {"piece": "shield", "strip": None, "line": None, "sample": None},
            ],
        },
        {"name": "siteB", "pieces": [{"piece": "lander", "strip": "S9", "line": 10, "sample": 10}]},
    ]
}

CANDS = {
    "run": "t",
    "detector": {"frozen": False},
    "strips": {
        "S1": {
            "valid_area_km2": 2.0,
            "candidates": [
                {"row": 100, "col": 100, "score": 9.0, "branch": "bright"},  # false alarm, rank 1
                {"row": 1005, "col": 2010, "score": 8.0, "branch": "shadow"},  # lander: 0-based 1000,2000 -> d=11.2
                {"row": 300, "col": 300, "score": 7.0, "branch": "bright"},  # false alarm
                {"row": 4999, "col": 5999, "score": 1.0, "branch": "dark"},  # chute at rank 4 (> top_n)
            ],
        }
    },
}


def test_ranks_false_alarms_and_skips():
    s = score(CANDS, ANSWERS, THRESH)
    by = {(p.site, p.piece): p for p in s.pieces}
    assert by[("siteA", "lander")].rank == 2 and by[("siteA", "lander")].branch == "shadow"
    assert abs(by[("siteA", "lander")].distance_px - (5**2 + 10**2) ** 0.5) < 1e-9
    assert by[("siteA", "chute")].rank == 4
    assert by[("siteB", "lander")].rank is None  # strip not in run
    assert ("siteA", "shield") not in by  # not recorded: excluded, not a miss
    assert s.n_pieces_recorded == 2 and s.n_pieces_found == 1 and s.recall_at_n == 0.5
    strip = s.strips[0]
    assert strip.n_true_hits == 2 and strip.false_alarms == 2 and strip.false_alarms_per_km2 == 1.0
    assert s.passed is True
    assert any("shield" in x for x in s.skipped) and any("S9" in x for x in s.skipped)
    assert "recall@3 = 0.50" in format_report(s)


def test_empty_run_is_not_decidable():
    s = score({"strips": {}}, ANSWERS, THRESH)
    assert s.recall_at_n is None and s.passed is None


def test_match_radius_in_metres_scales_per_strip():
    from landers.score import match_radius_px

    assert match_radius_px({"match_radius_m": 5.0}, 0.25) == 20.0
    assert match_radius_px({"match_radius_m": 5.0}, 0.5) == 10.0
    assert match_radius_px({"match_radius_px": 7}, 0.25) == 7.0
    thr = dict(THRESH)
    del thr["match_radius_px"]
    thr["match_radius_m"] = 5.0
    cands = {"run": "t", "strips": {"S1": dict(CANDS["strips"]["S1"], scale_m=0.5)}}
    s = score(cands, ANSWERS, thr)
    by = {(p.site, p.piece): p for p in s.pieces}
    assert by[("siteA", "lander")].rank is None  # 11.2 px away, radius now 10 px at 50 cm/px


def test_recall_at_false_alarm_rate_threshold():
    from landers.score import format_injection_report, recall_at_false_alarm_rate

    truths = [
        {"tile": "a", "row": 100, "col": 100, "kind": "sheet", "size_m": 10},
        {"tile": "a", "row": 500, "col": 500, "kind": "dark_compact", "size_m": 2.5},
        {"tile": "b", "row": 100, "col": 100, "kind": "blob_shadow", "size_m": 4},
    ]
    dets = [
        {"tile": "a", "row": 102, "col": 101, "score": 9, "branch": "sheet"},
        {"tile": "a", "row": 900, "col": 900, "score": 8, "branch": "bright"},  # false alarm 1
        {"tile": "b", "row": 101, "col": 99, "score": 7, "branch": "shadow"},
        {"tile": "a", "row": 300, "col": 300, "score": 6, "branch": "bright"},  # false alarm 2 -> threshold
        {"tile": "a", "row": 501, "col": 500, "score": 5, "branch": "dark_compact"},  # below threshold
    ]
    r = recall_at_false_alarm_rate(dets, truths, area_km2=1.0, radius_px=5.0, fa_per_km2=1.0)
    assert r["false_alarms_allowed"] == 1 and r["score_threshold"] == 6 and r["false_alarms_kept"] == 1
    assert r["recall_overall"] == round(2 / 3, 3)
    rows = {(x["kind"], x["size_bin"]): x for x in r["rows"]}
    assert rows[("sheet", "8-12 m")]["branches"] == {"sheet": 1}
    assert rows[("dark_compact", "2-3 m")]["found"] == 0
    assert "recall overall" in format_injection_report(r)

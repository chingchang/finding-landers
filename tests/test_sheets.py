import numpy as np

from landers import sheets


def test_select_radius_and_order():
    entry = {
        "candidates": [
            {"row": 100, "col": 100, "score": 1.0, "branch": "bright"},
            {"row": 110, "col": 100, "score": 5.0, "branch": "sheet"},
            {"row": 9000, "col": 100, "score": 9.0, "branch": "shadow"},  # outside 1 km at 25 cm/px
        ]
    }
    picks = sheets.select(entry, 0.25, 100, 100, radius_m=1000, top_n=10)
    assert [p.branch for p in picks] == ["sheet", "bright"]
    assert picks[0].rank == 1 and abs(picks[0].distance_m - 2.5) < 1e-9


def test_anchor_falls_back_to_site_position():
    site = {
        "lat": 1.0,
        "lon_e": 2.0,
        "pieces_refined": [
            {"piece": "lander", "lat": 1.5, "lon_e": 2.5, "precision_m": 60},
            {"piece": "backshell", "lat": None, "lon_e": None},
        ],
    }
    assert sheets.anchor_for(site, "lander")[:3] == (1.5, 2.5, 60.0)
    lat, lon, prec, how = sheets.anchor_for(site, "backshell")
    assert (lat, lon, prec) == (1.0, 2.0, 1000.0) and "published" in how


def test_stretch_handles_empty():
    a = np.zeros((8, 8), np.uint16)
    assert sheets._stretch(a, np.zeros((8, 8), bool)).max() == 0

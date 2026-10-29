import dataclasses
import math

import numpy as np
import pytest

from landers import detect, geo
from landers import transplant as tp
from landers.strip import Window
from tests.test_detect import fake_label


class FakeStrip:
    """Enough of ``Strip`` for cutting: a label and windowed reads of one array."""

    def __init__(self, data: np.ndarray, lbl):
        self.data = data
        self.label = dataclasses.replace(lbl, lines=data.shape[0], samples=data.shape[1])

    def read(self, r0, r1, c0, c1):
        r0, c0 = max(r0, 0), max(c0, 0)
        r1, c1 = min(r1, self.data.shape[0]), min(c1, self.data.shape[1])
        d = self.data[r0:r1, c0:c1]
        return Window(r0, c0, d, (d != 0) & (d < 1022))


def ground(rng, shape, level=500.0, noise=20.0):
    return np.clip(level + noise * rng.standard_normal(shape), 1, 1021)


def put_object(img, lbl, r, c, radius=6, bright=250, height_m=1.5, dark=150):
    """A bright disc with a dark streak the way shadows fall in ``lbl``; returns nothing."""
    drow, dcol = geo.shadow_direction(lbl)
    length = geo.shadow_length_px(lbl, height_m)
    yy, xx = np.mgrid[: img.shape[0], : img.shape[1]]
    img[(yy - r) ** 2 + (xx - c) ** 2 <= radius**2] += bright
    for t in np.linspace(0, 1, 60):
        pr, pc = r + drow * (radius + 1 + t * length), c + dcol * (radius + 1 + t * length)
        img[int(round(pr)) - 1 : int(round(pr)) + 2, int(round(pc)) - 1 : int(round(pc)) + 2] -= dark


def test_rotation_turns_source_shadow_into_target_shadow():
    for src_az, tgt_az in ((170.0, 20.0), (268.0, 30.0), (150.0, 150.0), (10.0, 350.0)):
        src = fake_label(sub_solar_azimuth_deg=src_az)
        tgt = fake_label(sub_solar_azimuth_deg=tgt_az)
        a = np.zeros((61, 61))
        drow, dcol = geo.shadow_direction(src)
        for t in range(5, 25):
            a[int(round(30 + drow * t)), int(round(30 + dcol * t))] = 1.0
        cut = tp.Cut("s", "p", "hardware", "X", 0, 0, 3, 0.25, 50, src_az, 20, False, a, a, a > 0, 500.0, 0, 0)
        g, _, _ = tp.rotated_arrays(cut, tp.rotation_deg(src_az, tgt_az))
        rr, cc = np.nonzero(g > 0.5)
        v = np.array([(rr - 30).mean(), (cc - 30).mean()])
        v /= np.linalg.norm(v)
        trow, tcol = geo.shadow_direction(tgt)
        assert v @ np.array([trow, tcol]) > 0.98, (src_az, tgt_az, v, (trow, tcol))


def test_cut_and_plant_is_found_by_the_detector_under_the_target_sun():
    rng = np.random.default_rng(3)
    src_lbl = fake_label(sub_solar_azimuth_deg=170.0, incidence_deg=50.0)
    tgt_lbl = fake_label(sub_solar_azimuth_deg=20.0, incidence_deg=57.0)
    src_img = ground(rng, (400, 400), level=800.0)
    put_object(src_img, src_lbl, 200, 200)
    src = FakeStrip(np.clip(src_img, 1, 1021).astype(np.uint16), src_lbl)
    cfg = tp.TransplantConfig()
    cut = tp.cut_piece(src, "siteA", "lander", "hardware", 200, 200, 3.0, cfg)
    assert cut is not None and cut.radius_px == tp.cut_radius_px(3.0, src.label, cfg)
    assert abs(cut.background_dn - 800.0) < 15
    assert cut.gain.shape == cut.weight.shape and cut.weight.max() == 1.0 and cut.weight.min() == 0.0
    assert cut.gain[cut.half, cut.half] > 1.2  # the bright object

    tgt = ground(rng, (1024, 1024), level=400.0).astype(np.uint16)
    win = Window(0, 0, tgt, np.ones_like(tgt, dtype=bool))
    planted, placed = tp.place_in_tile(win, tgt_lbl, [cut], [0], rng, cfg, "t")
    assert len(placed) == 1
    p = placed[0]
    assert abs(p.rotation_deg - tp.rotation_deg(170.0, 20.0)) < 1e-9
    assert abs(p.tan_ratio - math.tan(math.radians(57.0)) / math.tan(math.radians(50.0))) < 1e-6
    r, c = int(p.row), int(p.col)
    # contrast is preserved as a ratio: the object is about (800+250)/800 times its new surroundings
    centre = float(planted.data[r - 2 : r + 3, c - 2 : c + 3].mean())
    assert 1.2 < centre / 400.0 < 1.45, centre
    # the dark streak now lies along the target's shadow direction
    diff = planted.data.astype(float) - tgt.astype(float)
    rr, cc = np.nonzero(diff < -60)
    v = np.array([(rr - r).mean(), (cc - c).mean()])
    v /= np.linalg.norm(v)
    assert v @ np.array(geo.shadow_direction(tgt_lbl)) > 0.9, v
    # and the detector finds it as a bright object with a shadow
    cands = detect.detect_tile(planted, tgt_lbl, detect.DetectorConfig())
    near = [k for k in cands if math.hypot(k.row - p.row, k.col - p.col) <= 4]
    assert near and any(k.branch == "shadow" for k in near), [(k.branch, k.row, k.col) for k in cands]


def test_sham_cut_changes_little_and_saturation_survives():
    rng = np.random.default_rng(4)
    lbl = fake_label()
    img = ground(rng, (300, 300), level=600.0)
    img[140:150, 140:150] = 1023  # a saturated patch
    src = FakeStrip(np.clip(img, 1, 1023).astype(np.uint16), lbl)
    cfg = tp.TransplantConfig()
    cut = tp.cut_piece(src, "s", "parachute", "fabric", 145, 145, 4.0, cfg)
    assert cut.n_saturated == 100 and cut.saturated.sum() == 100
    tgt = ground(rng, (256, 256), level=300.0)
    data = tgt.copy()
    assert tp.plant(data, np.ones_like(data, dtype=bool), cut, 128, 128, 0.0)
    assert (data[123:133, 123:133] >= 1022).all()  # still saturated on darker ground
    sham = tp.cut_piece(src, "s", "parachute", "fabric", 80, 220, 4.0, cfg, sham=True)
    assert sham is not None and sham.sham
    data2 = tgt.copy()
    assert tp.plant(data2, np.ones_like(data2, dtype=bool), sham, 128, 128, 0.0)
    rel = (data2 - tgt) / tgt
    assert abs(rel[118:138, 118:138].mean()) < 0.03  # plain ground: gain about one
    # off the valid ground nothing is planted
    valid = np.ones_like(data, dtype=bool)
    valid[120:124, :] = False
    assert not tp.plant(tgt.copy(), valid, cut, 128, 128, 0.0)


def test_sham_position_avoids_pieces_and_edges():
    rng = np.random.default_rng(5)
    lbl = fake_label(scale_m=0.25)
    src = FakeStrip(ground(rng, (1400, 1400)).astype(np.uint16), lbl)
    cfg = tp.TransplantConfig(sham_offset_m=100.0, sham_clear_m=50.0)
    pieces = [(700.0, 700.0), (700.0, 1100.0)]  # the second piece sits 100 m east, on the first bearing
    pos = tp.sham_position(src, 700.0, 700.0, 30, pieces, cfg)
    assert pos is not None
    assert abs(math.hypot(pos[0] - 700, pos[1] - 700) - 400) < 1.0
    assert all(math.hypot(pos[0] - r, pos[1] - c) >= 200 + 30 for r, c in pieces)
    assert tp.sham_position(src, 40.0, 40.0, 30, [], cfg) is not None  # some bearing points inward
    assert tp.sham_position(FakeStrip(src.data[:300, :300], lbl), 150.0, 150.0, 30, [], cfg) is None


def test_source_and_target_rules():
    sites = {
        "sites": [
            {"name": "a", "group": "tuning", "strips": ["T1", "T2"]},
            {"name": "h", "group": "heldout", "strips": ["H1"]},
            {"name": "s", "group": "spare", "strips": ["S1"]},
        ]
    }
    assert tp.tuning_sources(sites) == {"T1": "a", "T2": "a"}
    manifest = "control_a T1 u\nmpl_summer M1 u\nmpl_summer H1 u\nmpl_other M9 u\nmpl_summer M2 u\n"
    assert tp.search_targets(sites, manifest) == ["M1", "M2"]
    thr = {"piece_kinds": {"hardware": ["lander"], "fabric": ["parachute"], "mark": ["crash_scar"]}}
    answers = {
        "sites": [
            {
                "name": "a",
                "pieces": [
                    {"piece": "lander", "strip": "T1", "line": 101, "sample": 201, "size_m": 3.0},
                    {"piece": "parachute", "strip": None, "line": None, "sample": None},
                ],
            }
        ]
    }
    got = tp.key_pieces(answers, thr, tp.tuning_sources(sites))
    want = {
        "site": "a",
        "piece": "lander",
        "kind": "hardware",
        "strip": "T1",
        "row": 100.0,
        "col": 200.0,
        "size_m": 3.0,
    }
    assert got == [want]
    answers["sites"][0]["pieces"][0]["strip"] = "H1"
    with pytest.raises(ValueError):
        tp.key_pieces(answers, thr, tp.tuning_sources(sites))
    src = fake_label(incidence_deg=50.0, scale_m=0.25)
    targets = {
        "M1": fake_label(incidence_deg=57.0, scale_m=0.25),
        "M2": fake_label(incidence_deg=56.0, scale_m=0.25),
        "M3": fake_label(incidence_deg=55.0, scale_m=0.5),
        "M4": fake_label(incidence_deg=70.0, scale_m=0.25),
    }
    assert tp.nearest_targets(src, targets, 2) == ["M2", "M1"]
    assert tp.nearest_targets(dataclasses.replace(src, scale_m=0.5), targets, 2) == ["M3"]
    assert tp.nearest_targets(dataclasses.replace(src, scale_m=1.0), targets, 2) == []


def test_recall_groups_and_per_truth_radius():
    from landers.score import recall_at_false_alarm_rate

    truths = [
        {"tile": "a", "row": 100, "col": 100, "kind": "mark", "site": "s", "piece": "scar", "radius_px": 80},
        {"tile": "a", "row": 500, "col": 500, "kind": "hardware", "site": "s", "piece": "lander", "radius_px": 20},
    ]
    dets = [
        {"tile": "a", "row": 150, "col": 100, "score": 9, "branch": "dark"},  # 50 px: inside the mark's 80
        {"tile": "a", "row": 550, "col": 500, "score": 8, "branch": "bright"},  # 50 px: outside the lander's 20
    ]
    r = recall_at_false_alarm_rate(dets, truths, 1.0, 20.0, 2.0, group=lambda t: (t["kind"], t["piece"]))
    rows = {(x["kind"], x["size_bin"]): x for x in r["rows"]}
    assert rows[("mark", "scar")]["found"] == 1 and rows[("hardware", "lander")]["found"] == 0
    assert r["false_alarms_kept"] == 1
    sham = tp.Placement("a", "T", 540, 500, 0, "s", "x", "hardware", True, 0, 1, 10)
    assert tp.sham_hits(dets, [sham], None, lambda p: 20.0) == {"n": 1, "hit": 1, "rate": 1.0}

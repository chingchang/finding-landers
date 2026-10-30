"""Item 12c: registration across map scales, the node cache, the crop export and its read-back. No data needed."""

import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import ndimage

from landers import persist as lp
from landers.search import export as ex
from landers.search import persistence as sp
from landers.search import register as rg
from landers.strip import Window, valid_mask


class FakeStrip:
    def __init__(self, data: np.ndarray, scale_m: float, observation_id: str = "X"):
        self.data = data
        self.label = SimpleNamespace(scale_m=scale_m, lines=data.shape[0], samples=data.shape[1], observation_id=observation_id)
        self.jp2_path = None

    @property
    def shape(self):
        return self.data.shape

    def read(self, r0, r1, c0, c1):
        r0, c0 = max(r0, 0), max(c0, 0)
        d = self.data[r0:r1, c0:c1]
        return Window(r0, c0, d, valid_mask(d))

    def read_centered(self, row, col, size):
        r0, c0 = int(round(row)) - size // 2, int(round(col)) - size // 2
        return self.read(r0, r0 + size, c0, c0 + size)

    def read_reduced(self, r0, r1, c0, c1, step):
        r0, c0 = max(r0, 0), max(c0, 0)
        d = self.data[r0:r1:step, c0:c1:step]
        return Window(r0, c0, d, valid_mask(d), step)

    @property
    def overview(self):
        d = self.data[::16, ::16]
        return Window(0, 0, d, valid_mask(d))

    overview_step = 16


def ground(n: int, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    g = ndimage.gaussian_filter(rng.standard_normal((n, n)), 2.0)
    return np.clip(500 + g / g.std() * 80, 1, 1021).astype(np.uint16)


def halved(g: np.ndarray, shift: int) -> np.ndarray:
    """A 0.5 m strip of the same ground: pixel i is the mean of ground pixels 2i + shift and 2i + shift + 1."""
    x = g[shift:, shift:].astype(np.float32)
    n = x.shape[0] // 2
    return (x[: 2 * n, : 2 * n].reshape(n, 2, n, 2).mean(axis=(1, 3))).astype(np.uint16)


def naive_map(scale_a, scale_b):
    return lambda a, b, r, c: (r * scale_a / scale_b, c * scale_a / scale_b)


def test_node_offset_across_scales_both_ways(monkeypatch):
    g = ground(1600)
    s = 40
    fine, coarse = FakeStrip(g, 0.25), FakeStrip(halved(g, s), 0.5)
    monkeypatch.setattr(lp, "predict_in_b", naive_map(0.25, 0.5))
    n = rg.register_node(fine, coarse, 800.0, 800.0, 256, 64, (0.0, 0.0), rg.grid_zooms(fine, coarse))
    assert n.ok, n
    want = -(s + 0.5) / 2  # ground coordinate x sits at (x - s - 0.5) / 2 in the 0.5 m strip
    assert abs(n.drow - want) < 0.5 and abs(n.dcol - want) < 0.5, n
    monkeypatch.setattr(lp, "predict_in_b", naive_map(0.5, 0.25))
    n = rg.register_node(coarse, fine, 380.0, 380.0, 256, 64, (0.0, 0.0), rg.grid_zooms(coarse, fine))
    assert n.ok, n
    assert abs(n.drow - (s + 0.5)) < 1.0 and abs(n.dcol - (s + 0.5)) < 1.0, n


def test_node_equal_scales_matches_the_frozen_rule(monkeypatch):
    g = ground(1400)
    a, b = FakeStrip(g[:-30, :-30], 0.25), FakeStrip(g[30:, 30:], 0.25)
    monkeypatch.setattr(lp, "predict_in_b", lambda sa, sb, r, c: (r, c))
    n = rg.register_node(a, b, 600.0, 600.0, 256, 64, (0.0, 0.0), (1, 1))
    assert n.ok and abs(n.drow + 30) < 0.5 and abs(n.dcol + 30) < 0.5, n
    far = rg.register_node(a, FakeStrip(ground(1370, seed=2), 0.25), 600.0, 600.0, 256, 64, (0.0, 0.0), (1, 1))
    assert not far.ok and far.note == "weak or ambiguous match"


def test_whole_factor_scales_only():
    with pytest.raises(ValueError):
        rg.grid_zooms(FakeStrip(ground(64), 0.25), FakeStrip(ground(64), 0.3))


def test_coarse_offset_finds_a_shift_and_refuses_noise(monkeypatch):
    rng = np.random.default_rng(5)
    g = ndimage.gaussian_filter(rng.standard_normal((6000, 6000)), 16.0)
    g = np.clip(500 + g / g.std() * 80, 1, 1021).astype(np.uint16)
    monkeypatch.setattr(lp, "predict_in_b", lambda sa, sb, r, c: (r, c))
    a, b = FakeStrip(g[:-96, :-96], 0.25), FakeStrip(g[96:, 96:], 0.25)
    dr, dc, rec = rg.coarse_offset(a, b, n_spots=9)
    assert rec["found"] and abs(dr + 96) <= 4 and abs(dc + 96) <= 4, (dr, dc, rec)
    other = np.clip(500 + 60 * rng.standard_normal((6000, 6000)), 1, 1021).astype(np.uint16)
    dr, dc, rec = rg.coarse_offset(a, FakeStrip(other, 0.25), n_spots=5)
    assert not rec["found"] and (dr, dc) == (0.0, 0.0)


def test_no_coarse_offset_reads_no_nodes(monkeypatch):
    monkeypatch.setattr(rg, "coarse_offset", lambda a, b: (0.0, 0.0, {"found": False, "tried": []}))
    nodes, rec = rg.offset_field(FakeStrip(ground(64), 0.25), FakeStrip(ground(64), 0.25))
    assert nodes == [] and rec["coarse"]["found"] is False


def test_node_cache_round_trip(tmp_path):
    nodes = [lp.Node(1.0, 2.0, 3.0, 4.0, 5.5, 6.5, 0.9, 2.0, True), lp.Node(7.0, 8.0, 9.0, 1.0, 0.0, 0.0, 0.0, 0.0, False, "weak")]
    dirs = {"A->B": {"from": "A", "to": "B", "registration": lp.nodes_summary(nodes), "nodes": lp.nodes_to_json(nodes)}}
    path = rg.write_nodes(tmp_path, ["A", "B"], 12.5, "test", dirs)
    back = json.loads(path.read_text())
    assert rg.nodes_from_json(back["directions"]["A->B"]["nodes"]) == nodes
    assert rg.is_registered([0, 4]) and not rg.is_registered([3, 3])


def test_chance_uses_the_directions_radius():
    per = {"B": {"valid_area_km2": 1.0, "scale_m": 0.5, "family_counts": {"bright": 1000, "dark": 0}}}
    surv = {"A": [{"branch": "bright"}]}
    pr = {"radius_px": 8.0, "directions": {"A->B": {"from": "A", "to": "B", "radius_px": 4.0, "survivors": [{"rank": 1, "seen": False}]}}}
    expected = sp.chance_matches(pr, surv, per)[0]["expected_by_chance"]
    assert expected == round(1 - np.exp(-1000 / 1e6 * np.pi * 2.0**2), 2)


SITES = {"sites": [{"name": "t", "group": "tuning", "strips": ["T1"]}, {"name": "b", "group": "heldout", "strips": ["B1"]}]}


def test_blind_strips_are_never_exportable():
    manifest = "mpl_summer S1 url\nmpl_summer B1 url\nother O1 url\n"
    assert ex.exportable_strips(SITES, manifest, "mpl_summer") == {"S1": "search", "T1": "tuning"}
    ex.refuse_blind(SITES, "S1")
    with pytest.raises(ValueError):
        ex.refuse_blind(SITES, "B1")


def test_rank_top_is_the_survivors_order():
    c = [{"row": i, "col": 0, "score": s, "branch": "bright", "grade": "needs second look", "extra": {"x": 1}}
         for i, s in enumerate([1.0, 3.0, 2.0, 3.0])]
    top = ex.rank_top(c, 3)
    entry = {"valid_area_km2": 1.5, "candidates": c}
    assert [r["row"] for r in top] == [r["row"] for r in sp.survivors(entry, 2.0)] == [1, 3, 2]
    assert [r["rank"] for r in top] == [1, 2, 3] and "extra" not in top[0]


def test_export_reads_back_with_edges_saturation_and_no_data(tmp_path):
    g = ground(9000).copy()
    g[100:110, 100:110] = 1023
    g[:50, :] = 0
    strip = FakeStrip(g, 0.25, "S1")
    rows = [{"rank": k + 1, "row": r, "col": c, "score": 1.0} for k, (r, c) in
            enumerate([(105.2, 105.0), (10.0, 4000.0), (8990.0, 8990.0), (4500.0, 4500.0), (4500.0, 4600.0)])]
    index = ex.export_strip(strip, rows, 64, tmp_path / "strips" / "S1", {"candidates_total": 5})
    assert index["n_crops"] == 5 and index["block_reads"] == 3
    (tmp_path / "labels").mkdir()
    es = ex.ExportedStrip(tmp_path, "S1")
    assert np.array_equal(es.crop(4), g[4500 - 32 : 4500 + 32, 4500 - 32 : 4500 + 32])
    assert es.crop(1)[32 - 5 + 5, 32] == 1023  # a saturated value stays as it was
    assert (es.crop(3)[-20:, :] == 0).all() and es.crop(3)[0, 0] == g[8990 - 32, 8990 - 32]  # off the image is no data
    assert np.array_equal(es.overview.data, g[::16, ::16])
    assert es.overview_step == 16 and es.index["chunks"][0]["n"] == 5


def test_window_round_trip(tmp_path):
    g = ground(128)
    ex.write_window(tmp_path / "w.npz", g, 7, 9)
    w = ex.read_window(tmp_path / "w.npz")
    assert (w.row0, w.col0) == (7, 9) and np.array_equal(w.data, g)

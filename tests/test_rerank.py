"""The re-ranker's pieces on synthetic numbers; no encoder and no strip."""

import numpy as np

from landers.rerank import crops as rc
from landers.rerank import model as rm
from landers.transplant import rotation_deg


def test_cut_centres_and_pads_with_no_data():
    data = np.arange(1, 401, dtype=np.uint16).reshape(20, 20)
    out = rc.cut(data, 100, 200, 110.0, 210.0, size=4)
    assert np.array_equal(out, data[8:12, 8:12])
    edge = rc.cut(data, 0, 0, 0.0, 0.0, size=4)
    assert edge[0, 0] == 0 and edge[2, 2] == data[0, 0]


def test_canonical_puts_the_shadow_on_the_same_side_for_any_sun():
    def scene(az):
        # a dark spot on the shadow side, placed by the same rotation the transplant uses
        x = np.full((161, 161), 400, np.uint16)
        x[80, 110] = 50
        turned = np.round(rc.ndimage.rotate(x.astype(float), -rotation_deg(az, 0.0), reshape=False, order=1, mode="nearest")).astype(np.uint16)
        return turned

    a, b = rc.canonical(scene(40.0), 40.0), rc.canonical(scene(250.0), 250.0)
    assert np.unravel_index(np.argmin(a), a.shape) == np.unravel_index(np.argmin(b), b.shape)


def test_canonical_fills_no_data_with_the_median():
    x = np.full((40, 40), 300, np.uint16)
    x[:10] = 0
    assert rc.canonical(x, rotation_deg(0.0, 0.0)).min() == 300


def test_window_is_fixed_on_the_ground():
    x = np.full((320, 320), 100.0, np.float32)
    assert rc.window(x, 16.0, 0.25).shape == (64, 64)
    assert rc.window(x, 16.0, 0.5).shape == (32, 32)


def test_window_does_not_stretch_noise_into_texture():
    rng = np.random.default_rng(0)
    quiet = 500 + rng.normal(0, 1.0, (64, 64))
    assert np.ptp(rc.window(quiet, 16.0, 0.25)) < 0.1  # MAD floor: 2 percent of the median


def test_window_draws_a_saturated_pixel_bright():
    rng = np.random.default_rng(0)
    x = (300 + rng.normal(0, 5.0, (64, 64))).astype(np.float32)
    x[32, 32] = 1023
    w = rc.window(x, 16.0, 0.25)
    assert w[32, 32] == 1.0


def test_novelty_flags_the_stranger_and_keeps_small_populations_at_zero():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 0.05, (60, 8)) + np.eye(8)[0]
    a[0] = np.eye(8)[3]
    n = rm.novelty(a)
    assert np.argmax(n) == 0 and n[0] > 3
    assert (rm.novelty(a[:5]) == 0).all()
    assert rm.novelty(a[1:], query=a[:1])[0] > 3


def test_logistic_matches_a_known_gradient_zero():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(300, 3))
    y = (x[:, 0] + 0.3 * rng.normal(size=300) > 0).astype(float)
    w = np.ones(300)
    b, a = rm.logistic(x, y, w, c=0.1)
    m = x @ b + a
    p = 1 / (1 + np.exp(-m))
    grad = x.T @ (p - y) + b / 0.1
    assert np.abs(grad).max() < 1e-2 and abs((p - y).sum()) < 1e-2
    assert b[0] > 2 * abs(b[1])


def test_source_weights_split_as_the_protocol_says():
    src = np.array(["native"] * 2 + ["copy"] * 8 + ["list_fa"] * 3 + ["sham"] * 8 + ["tile_fa"] * 80 + [""] * 4)
    w = rm.source_weights(src)
    assert abs(w[src == "native"].sum() - 0.5) < 1e-9 and abs(w[src == "copy"].sum() - 0.5) < 1e-9
    for s in ("list_fa", "sham", "tile_fa"):
        assert abs(w[src == s].sum() - 1 / 3) < 1e-9
    assert (w[src == ""] == 0).all()
    only = rm.source_weights(np.array(["native", "list_fa"]))
    assert only.tolist() == [1.0, 1.0]


def test_training_mask_removes_the_held_site_everywhere_and_the_held_target():
    source = np.array(["native", "list_fa", "copy", "sham", "tile_fa", "tile_fa", "copy", ""])
    site = np.array(["a", "a", "a", "a", "", "a", "b", ""])
    target = np.array(["", "", "t1", "t2", "t1", "t2", "t2", "t1"])
    keep = rm.training_mask(source, site, target, "a", None)
    assert keep.tolist() == [False, False, False, False, True, False, True, False]
    keep = rm.training_mask(source, site, target, "a", "t2")
    assert keep.tolist() == [False, False, False, False, True, False, False, False]
    keep = rm.training_mask(source, site, target, "b", None, transplanted=False)
    assert keep.tolist() == [True, True, False, False, False, False, False, False]


def test_label_tile_copy_sham_and_false_alarm():
    dets = [{"row": 100, "col": 100, "score": 1.0}, {"row": 103, "col": 100, "score": 2.0}, {"row": 500, "col": 500, "score": 3.0}, {"row": 900, "col": 900, "score": 0.0}]
    pls = [{"row": 101, "col": 100, "site": "a", "sham": False}, {"row": 500, "col": 501, "site": "b", "sham": True}, {"row": 50, "col": 50, "site": "c", "sham": False}]
    source, site, best = rm.label_tile(dets, pls, [20.0, 20.0, 20.0])
    assert source == ["", "copy", "tile_fa", "tile_fa"]
    assert site == ["a", "a", "b", ""]
    assert best == [1, 2, None]


def test_fit_separates_a_planted_direction_and_every_variant_runs():
    rng = np.random.default_rng(0)
    n = 300
    y = np.zeros(n)
    y[:60] = 1
    emb = rng.normal(0, 1, (n, 80)).astype(np.float32)
    emb[:60, 7] += 4
    sc, nov = rng.normal(size=n), rng.normal(size=n)
    for name in rm.VARIANTS:
        if name == "no_transplanted":
            continue
        m = rm.fit(emb, sc, nov, y, np.ones(n), name)
        d = m.decision(emb, sc, nov)
        if rm.VARIANTS[name]["embedding"]:
            assert rm.auc(d[:60], d[60:]) > 0.9


def test_auc_and_wilson():
    assert rm.auc(np.array([2.0, 3.0]), np.array([1.0, 2.0])) == 0.875
    assert rm.auc(np.array([]), np.array([1.0])) is None
    lo, hi = rm.wilson(3, 6)
    assert 0.18 < lo < 0.2 and 0.8 < hi < 0.82
    assert rm.wilson(0, 0) is None


def test_paste_verdict():
    high = [{"native": 0.0, "copies_median": 2.0}] * 4
    assert rm.paste_verdict(high)["learning_the_paste"] is True
    mixed = [{"native": 0.0, "copies_median": 2.0}] * 2 + [{"native": 2.0, "copies_median": 0.0}] * 2
    assert rm.paste_verdict(mixed)["learning_the_paste"] is False
    assert rm.paste_verdict([{"native": 1.0, "copies_median": None}])["learning_the_paste"] is None

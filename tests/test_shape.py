import numpy as np

from landers import shape
from landers.score import _auc, feature_separation


def test_disc_is_circular_and_filled():
    lab = np.zeros((40, 40), int)
    yy, xx = np.mgrid[:40, :40]
    lab[(yy - 20) ** 2 + (xx - 20) ** 2 <= 8**2] = 1
    z = lab.astype(float) * 5.0
    g = shape.gradient_magnitude(z)
    sl = (slice(12, 29), slice(12, 29))
    f = shape.component_features(lab, 1, z, g, sl)
    assert f["circularity"] > 0.6 and f["fill"] > 0.6 and f["elongation"] < 0.1 and f["edge_sharpness"] > 0


def test_bar_is_elongated():
    lab = np.zeros((40, 40), int)
    lab[18:22, 5:35] = 1
    z = lab.astype(float) * 5.0
    f = shape.component_features(lab, 1, z, shape.gradient_magnitude(z), (slice(18, 22), slice(5, 35)))
    assert f["elongation"] > 0.5 and f["fill"] == 1.0


def test_tile_ranks_and_auc():
    assert shape.tile_ranks([3.0, 9.0, 5.0]) == [2, 0, 1]
    assert _auc([5, 6], [1, 2]) == 1.0 and _auc([1, 2], [5, 6]) == 0.0 and _auc([3], [3]) == 0.5


def test_feature_separation_groups_by_kind_and_branch():
    truths = [{"tile": "t", "row": 10, "col": 10, "kind": "blob_shadow", "size_m": 2}]
    dets = [
        {"tile": "t", "row": 11, "col": 10, "score": 1, "branch": "bright", "features": {"circularity": 0.9}},
        {"tile": "t", "row": 500, "col": 500, "score": 1, "branch": "bright", "features": {"circularity": 0.3}},
        {"tile": "t", "row": 600, "col": 600, "score": 1, "branch": "bright", "features": {"circularity": 0.4}},
    ]
    r = feature_separation(dets, truths, 5.0)
    assert r["rows"][0]["kind"] == "blob_shadow" and r["rows"][0]["auc"]["circularity"] == 1.0

import numpy as np
import pytest

from landers import config, persist
from tests.conftest import site_strips


def test_register_arrays_recovers_known_shift():
    rng = np.random.default_rng(3)
    big = rng.standard_normal((900, 900)).astype(np.float32)
    big = np.clip(500 + 40 * big, 1, 1021).astype(np.uint16)
    # blur a little so there is structure to match
    from scipy import ndimage

    big = ndimage.gaussian_filter(big.astype(np.float32), 1.5).astype(np.uint16)
    template = big[300:500, 310:510]  # 200 px window whose centre sits at (400, 410) in big
    search = big[200:600, 200:600]  # 400 px window centred at (400, 400): template is +0 rows, +10 cols off centre
    drow, dcol, corr, ratio = persist.register_arrays(
        template, np.ones_like(template, bool), search, np.ones_like(search, bool)
    )
    assert abs(drow - 0) < 0.5 and abs(dcol - 10) < 0.5, (drow, dcol)
    assert corr > 0.9 and ratio > 1.5


def test_interpolate_and_family():
    nodes = [
        persist.Node(0, 0, 0, 0, 10, -5, 0.9, 2.0, True),
        persist.Node(1000, 0, 0, 0, 12, -5, 0.9, 2.0, True),
        persist.Node(0, 1000, 0, 0, 100, 100, 0.9, 2.0, False),
    ]
    dr, dc, near = persist.interpolate(nodes, 500, 0)
    assert 10 < dr < 12 and abs(dc + 5) < 1e-9 and near == 500
    assert persist.FAMILY["sheet"] == "bright" and persist.FAMILY["dark_compact"] == "dark"


@pytest.mark.slow
def test_registration_on_a_real_pair():
    ids = site_strips("schiaparelli")
    if len(ids) < 2 or any(config.find_strip(i) is None for i in ids[:2]):
        pytest.skip("Schiaparelli pair not on disk")
    from landers.strip import Strip

    a, b = Strip.open(ids[0]), Strip.open(ids[1])
    dr, dc, info = persist.coarse_offset(a, b)
    assert info["spots"] >= 1, info
    r, c = a.shape[0] // 2, a.shape[1] // 2
    node = persist.register_at(a, b, float(r), float(c), prior=(dr, dc))
    assert node.ok, node
    assert abs(node.drow - dr) < 64 and abs(node.dcol - dc) < 64  # fine stage agrees with the coarse one

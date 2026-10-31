"""The two-sided test of plan item 16: which side the light is on, and the fit. No data on disk needed."""

import math

import numpy as np
import pytest
from scipy import ndimage

from landers import relief, shape
from landers.detect import DetectorConfig, detect_tile
from landers.strip import Window
from tests.test_detect import fake_label


def scene(lit_on_sun_side: bool, length: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """Shadow direction is +col. A dark patch, with a lit strip beside it on one side."""
    z = np.zeros((100, 100))
    z[46:55, 40 : 40 + length] = -6.0
    if lit_on_sun_side:
        z[46:55, 36:39] = 5.0
    else:
        z[46:55, 40 + length + 1 : 40 + length + 4] = 5.0
    return z, z < -3.5


def feats(z, mask, reach=20.0, scale=0.25, inc=45.0):
    lab, _ = ndimage.label(mask)
    sl = ndimage.find_objects(lab)[0]
    r, c = ndimage.center_of_mass(mask)
    return shape.relief_features(lab, 1, sl, z, r, c, 0.0, 1.0, reach, scale, inc)


def test_an_object_has_its_lit_face_on_the_sun_side():
    assert feats(*scene(True))["relief_dipole"] == pytest.approx(5.0, abs=0.01)


def test_a_depression_has_its_lit_wall_on_the_anti_sun_side():
    assert feats(*scene(False))["relief_dipole"] == pytest.approx(-5.0, abs=0.01)


def test_a_patch_along_the_axis_does_not_measure_itself():
    """The reason for the feature: at the equivalent radius from the centroid, the old bands are still inside the patch."""
    z, mask = scene(True, length=30)
    radius = math.sqrt(mask.sum() / math.pi)
    r, c = ndimage.center_of_mass(mask)
    old = shape.shadow_features(z, r, c, radius, 0.0, 1.0, 20.0, 0.25, 45.0)
    assert old["anti_sun_min_z"] < -2.0 and old["sun_min_z"] < -2.0
    new = feats(z, mask)
    assert new["relief_anti_min_z"] > -2.0 and new["relief_sun_min_z"] > -2.0


def test_length_and_width_read_in_metres():
    f = feats(*scene(True), scale=0.25, inc=45.0)
    assert f["relief_height_m"] == pytest.approx(12 * 0.25, abs=0.01)
    assert f["relief_width_m"] == pytest.approx(9 * 0.25, abs=0.01)


def arrays(**kw):
    n = len(next(iter(kw.values())))
    base = {
        "relief_dipole": np.ones(n),
        "relief_sun_min_z": np.zeros(n),
        "relief_anti_min_z": np.zeros(n),
        "relief_height_m": np.ones(n),
        "relief_width_m": np.ones(n),
    }
    return {**base, **{k: np.array(v, float) for k, v in kw.items()}}


def test_each_fixed_condition_can_fail():
    f = arrays(
        relief_sun_min_z=[0, -2.5, 0, 0, 0],
        relief_height_m=[1, 1, 0.2, 4, 1],
        relief_width_m=[1, 1, 1, 1, 11],
    )
    assert relief.fixed_conditions(f).tolist() == [True, False, False, False, False]


def test_a_missing_feature_never_passes():
    f = arrays(relief_dipole=[np.nan], relief_sun_min_z=[np.nan], relief_height_m=[np.nan], relief_width_m=[np.nan])
    assert not relief.fixed_conditions(f)[0]
    assert np.isnan(relief.test_value(f)[0])


def test_the_placebo_reverses_the_sign_and_the_side():
    f = arrays(relief_dipole=[3.0, -3.0], relief_sun_min_z=[0, -5], relief_anti_min_z=[-5, 0])
    assert relief.test_value(f, flipped=True)[1] == 3.0
    assert np.isnan(relief.test_value(f, flipped=True)[0])
    assert relief.test_value(f)[0] == 3.0
    assert np.isnan(relief.test_value(f)[1])


def test_the_fit_comes_to_the_fraction_and_the_gain_is_measured():
    values = np.concatenate([np.arange(1.0, 101.0), np.full(9900, np.nan)])
    r = relief.fit_rule(values, p=0.001)
    assert (r.threshold, r.passed, r.n) == (91.0, 10, 10000)
    assert r.gain == pytest.approx(3.0)
    g = relief.gains(values, r)
    assert (g > 0).sum() == 10 and g[-1] == 0.0


def test_too_few_passing_keeps_t_just_above_nothing():
    values = np.concatenate([[2.0, -1.0, 0.0], np.full(9997, np.nan)])
    r = relief.fit_rule(values, p=0.001)
    assert (r.threshold, r.passed) == (2.0, 1)
    assert r.gain == pytest.approx(4.0)


def test_no_positive_value_is_no_rule():
    assert relief.fit_rule(np.array([-1.0, np.nan, 0.0])) is None
    assert relief.gains(np.array([-1.0, np.nan]), None).tolist() == [0.0, 0.0]


def test_the_flag_moves_no_candidate():
    rng = np.random.default_rng(1)
    data = rng.normal(400, 12, (512, 512)).round().astype(np.uint16)
    data[250:262, 250:256] = 200
    data[250:262, 244:248] = 700
    win = Window(0, 0, data, np.ones(data.shape, bool))
    lbl = fake_label(lines=512, samples=512, scale_m=0.25, sub_solar_azimuth_deg=180.0, incidence_deg=60.0)
    off = detect_tile(win, lbl, DetectorConfig())
    on = detect_tile(win, lbl, DetectorConfig(relief_features=True))
    assert [(c.row, c.col, c.score, c.branch) for c in off] == [(c.row, c.col, c.score, c.branch) for c in on]
    dark = [c for c in on if c.branch in relief.BRANCHES]
    assert dark and all("relief_dipole" in c.extra for c in dark)
    assert not any("relief_dipole" in c.extra for c in off)

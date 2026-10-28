import numpy as np

from landers import geo
from landers.label import StripLabel


def test_roundtrip(all_labels):
    for p in all_labels:
        lbl = StripLabel.read(p)
        rows = np.array([10.0, lbl.lines / 2, lbl.lines - 10.0])
        cols = np.array([10.0, lbl.samples / 2, lbl.samples - 10.0])
        lat, lon = geo.rowcol_to_latlon(lbl, rows, cols)
        r2, c2 = geo.latlon_to_rowcol(lbl, lat, lon)
        assert np.allclose(rows, r2, atol=1e-3) and np.allclose(cols, c2, atol=1e-3)


def test_rect_contains_label_footprint_and_shares_its_centre(all_labels):
    bad = []
    for p in all_labels:
        lbl = StripLabel.read(p)
        mn, mx, w, e = geo.rect_bounds(lbl)
        eps = 1e-4
        contained = (
            mn - eps <= lbl.min_lat and lbl.max_lat <= mx + eps and w - eps <= lbl.west_lon and lbl.east_lon <= e + eps
        )
        dlat = (mn + mx) / 2 - (lbl.min_lat + lbl.max_lat) / 2
        dlon = (w + e) / 2 - (lbl.west_lon + lbl.east_lon) / 2
        if not contained or abs(dlat) > 0.002 or abs(dlon) > 0.02:
            bad.append((lbl.observation_id, lbl.projection, contained, dlat, dlon))
    assert not bad, bad


def test_equirectangular_matches_label_to_a_metre(all_labels):
    for p in all_labels:
        lbl = StripLabel.read(p)
        if lbl.projection != "EQUIRECTANGULAR":
            continue
        mn, mx, w, e = geo.rect_bounds(lbl)
        for ours, theirs in ((mn, lbl.min_lat), (mx, lbl.max_lat), (w, lbl.west_lon), (e, lbl.east_lon)):
            assert abs(ours - theirs) < 3e-5, (lbl.observation_id, ours, theirs)


def test_shadow_geometry(all_labels):
    # shadow length = height * tan(incidence) / scale; direction is a unit vector
    for p in all_labels:
        lbl = StripLabel.read(p)
        expect = 2.0 * np.tan(np.radians(lbl.incidence_deg)) / lbl.scale_m
        assert abs(geo.shadow_length_px(lbl, 2.0) - expect) < 1e-9
        d = geo.shadow_direction(lbl)
        assert abs(np.hypot(*d) - 1) < 1e-9

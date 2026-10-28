"""Latitude/longitude <-> image pixel for the two HiRISE map projections.

Pixel coordinates here are 0-based numpy ``(row, col)`` of the pixel centre: row 0 is PDS line 1.
Formulas follow the PDS DSMAP.CAT sphere conventions; ``tests/test_geo.py`` checks them against each
label's own footprint bounds, which is the only truth available without ground control.
"""

from __future__ import annotations

import math

import numpy as np

from landers.label import StripLabel


def sphere_radius_m(lbl: StripLabel) -> float:
    """Radius of the projection sphere, implied by MAP_RESOLUTION (pix/deg) and MAP_SCALE (m/pix).

    Equals A_AXIS_RADIUS for the equirectangular strips and the polar radius (3376.2 km) for the polar
    stereographic ones; using A_AXIS_RADIUS for the latter puts the footprint 0.1 degrees off.
    """
    return lbl.map_resolution * lbl.scale_m * 180.0 / math.pi


def _xy_from_latlon(lbl: StripLabel, lat, lon):
    lat = np.radians(np.asarray(lat, dtype=float))
    lon = np.radians(np.asarray(lon, dtype=float))
    lon0 = math.radians(lbl.center_lon)
    R = sphere_radius_m(lbl)
    if lbl.projection == "EQUIRECTANGULAR":
        lat0 = math.radians(lbl.center_lat)
        x = R * math.cos(lat0) * (lon - lon0)
        y = R * lat
    elif lbl.projection == "POLAR STEREOGRAPHIC":
        if lbl.center_lat > 0:
            rho = 2 * R * np.tan(math.pi / 4 - lat / 2)
            x = rho * np.sin(lon - lon0)
            y = -rho * np.cos(lon - lon0)
        else:
            rho = 2 * R * np.tan(math.pi / 4 + lat / 2)
            x = rho * np.sin(lon - lon0)
            y = rho * np.cos(lon - lon0)
    else:
        raise ValueError(f"unsupported projection {lbl.projection!r}")
    return x, y


def _latlon_from_xy(lbl: StripLabel, x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    lon0 = math.radians(lbl.center_lon)
    R = sphere_radius_m(lbl)
    if lbl.projection == "EQUIRECTANGULAR":
        lat0 = math.radians(lbl.center_lat)
        lat = y / R
        lon = lon0 + x / (R * math.cos(lat0))
    elif lbl.projection == "POLAR STEREOGRAPHIC":
        rho = np.hypot(x, y)
        if lbl.center_lat > 0:
            lat = math.pi / 2 - 2 * np.arctan(rho / (2 * R))
            lon = lon0 + np.arctan2(x, -y)
        else:
            lat = -math.pi / 2 + 2 * np.arctan(rho / (2 * R))
            lon = lon0 + np.arctan2(x, y)
    else:
        raise ValueError(f"unsupported projection {lbl.projection!r}")
    return np.degrees(lat), np.degrees(lon) % 360.0


def latlon_to_rowcol(lbl: StripLabel, lat, lon):
    """Planetocentric latitude and east longitude (degrees) -> 0-based (row, col) pixel centre."""
    x, y = _xy_from_latlon(lbl, lat, lon)
    # PDS: line = LINE_PROJECTION_OFFSET - y/scale + 1 (1-based pixel centre); row = line - 1.
    row = lbl.line_offset - y / lbl.scale_m
    col = lbl.sample_offset + x / lbl.scale_m
    return row, col


def rowcol_to_latlon(lbl: StripLabel, row, col):
    row = np.asarray(row, dtype=float)
    col = np.asarray(col, dtype=float)
    y = (lbl.line_offset - row) * lbl.scale_m
    x = (col - lbl.sample_offset) * lbl.scale_m
    return _latlon_from_xy(lbl, x, y)


def rect_bounds(lbl: StripLabel):
    """(min_lat, max_lat, west_lon, east_lon) of the full image rectangle, from its four corners.

    The data footprint is a slanted parallelogram inside this rectangle, so for polar strips (rotated
    in the image frame) these bounds are wider than the label's; see ``mask_bounds`` for the strict check.
    """
    rows = np.array([0, 0, lbl.lines - 1, lbl.lines - 1], dtype=float)
    cols = np.array([0, lbl.samples - 1, 0, lbl.samples - 1], dtype=float)
    lat, lon = rowcol_to_latlon(lbl, rows, cols)
    return float(lat.min()), float(lat.max()), float(lon.min()), float(lon.max())


def mask_bounds(lbl: StripLabel, valid: np.ndarray, step: int):
    """Bounds of the valid-data footprint from a reduced-resolution mask (``step`` image px per mask px)."""
    rows, cols = np.nonzero(valid)
    lat, lon = rowcol_to_latlon(lbl, rows * step + step / 2 - 0.5, cols * step + step / 2 - 0.5)
    return float(lat.min()), float(lat.max()), float(lon.min()), float(lon.max())


def shadow_direction(lbl: StripLabel):
    """Unit vector (drow, dcol) pointing from an object to where its shadow falls.

    SUB_SOLAR_AZIMUTH is the direction *to* the sun, clockwise from image-right (PDS convention,
    measured in the image frame). Shadows fall the opposite way.
    """
    a = math.radians(lbl.sub_solar_azimuth_deg + 180.0)
    # azimuth clockwise from +col (right); image rows increase downward.
    return math.sin(a), math.cos(a)


def shadow_length_px(lbl: StripLabel, height_m: float) -> float:
    return height_m * math.tan(math.radians(lbl.incidence_deg)) / lbl.scale_m

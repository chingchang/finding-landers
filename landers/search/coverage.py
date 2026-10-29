"""Coverage and overlap from per-strip cell sets: how much ground was imaged on how many dates, which pairs
of strips share ground and how much, and a figure of it.

Every strip is a different date, so "number of strips covering a cell" is "number of dates". Two strips
from the same day would break that reading; the inventory carries the dates so a reader can check.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from landers.search.grid import PolarGrid, unpack

CREDIT = "NASA/JPL/University of Arizona"

# One hue, light to dark, for a magnitude (dates per cell); the surface and inks match the contact sheets' kin.
SURFACE = (252, 252, 251)
INK = (11, 11, 11)
INK_2 = (82, 81, 78)
MUTED = (137, 135, 129)
RAMP = [(183, 211, 246), (134, 182, 239), (85, 152, 231), (42, 120, 214), (28, 92, 171), (13, 54, 107)]
BINS = [(1, 1), (2, 2), (3, 3), (4, 5), (6, 8), (9, None)]  # dates per cell for each ramp step


def coverage(cells: dict[str, np.ndarray], grid: PolarGrid) -> dict:
    """Union of all cell sets with the number of strips (dates) covering each cell."""
    if not cells:
        raise ValueError("no strips")
    allk = np.concatenate(list(cells.values()))
    keys, n = np.unique(allk, return_counts=True)
    ix, iy = unpack(keys)
    hist = np.bincount(n)
    by_dates = {int(k): round(float(hist[k]) * grid.cell_km2, 3) for k in range(1, hist.size) if hist[k]}
    at_least = {}
    for k in range(1, hist.size):
        at_least[int(k)] = round(float(hist[k:].sum()) * grid.cell_km2, 3)
    per_strip = {}
    for sid, ks in cells.items():
        idx = np.searchsorted(keys, ks)
        n_here = n[idx]
        per_strip[sid] = {
            "km2": round(float(ks.size) * grid.cell_km2, 3),
            "km2_on_two_or_more_dates": round(float((n_here >= 2).sum()) * grid.cell_km2, 3),
            "fraction_on_two_or_more_dates": round(float((n_here >= 2).mean()), 3) if ks.size else 0.0,
        }
    return {
        "grid": grid.to_json(),
        "strips": len(cells),
        "union_km2": round(float(keys.size) * grid.cell_km2, 3),
        "km2_by_dates": by_dates,
        "km2_with_at_least_n_dates": at_least,
        "max_dates": int(n.max()),
        "bbox_cells": {"ix0": int(ix.min()), "ix1": int(ix.max()), "iy0": int(iy.min()), "iy1": int(iy.max())},
        "per_strip": per_strip,
        "cells": np.column_stack([ix, iy, n]).astype(np.int64),
    }


def overlaps(cells: dict[str, np.ndarray], grid: PolarGrid) -> list[dict]:
    """Every pair of strips sharing at least one cell, with the shared area and each side's share of it,
    largest first."""
    out = []
    for a, b in combinations(sorted(cells), 2):
        shared = np.intersect1d(cells[a], cells[b], assume_unique=True).size
        if shared == 0:
            continue
        out.append(
            {
                "a": a,
                "b": b,
                "km2": round(shared * grid.cell_km2, 3),
                "fraction_of_a": round(shared / cells[a].size, 3),
                "fraction_of_b": round(shared / cells[b].size, 3),
            }
        )
    out.sort(key=lambda p: (-p["km2"], p["a"], p["b"]))
    return out


def coverage_json(cov: dict) -> dict:
    d = dict(cov)
    d["cells"] = cov["cells"].tolist()
    d["cells_note"] = "[ix, iy, dates] for every covered cell"
    return d


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow before 10.1
        return ImageFont.load_default()


def _bin_index(n: int) -> int:
    for i, (lo, hi) in enumerate(BINS):
        if n >= lo and (hi is None or n <= hi):
            return i
    return len(BINS) - 1


def render(cov: dict, path, px_per_cell: int | None = None, title: str = "Ground imaged, by number of dates"):
    """A map of the coverage: one filled square per covered grid cell, darker with more dates, with a legend,
    a scale bar and the credit line. Axes are the projection's x (right) and y (up) in kilometres."""
    cells = cov["cells"]
    bb = cov["bbox_cells"]
    nx, ny = bb["ix1"] - bb["ix0"] + 1, bb["iy1"] - bb["iy0"] + 1
    if px_per_cell is None:
        px_per_cell = max(1, min(4, 900 // max(nx, ny)))
    cell_m = cov["grid"]["cell_m"]
    raster = np.zeros((ny, nx), dtype=np.int32)
    raster[bb["iy1"] - cells[:, 1], cells[:, 0] - bb["ix0"]] = cells[:, 2]  # y up: top row is iy1
    rgb = np.empty((ny, nx, 3), dtype=np.uint8)
    rgb[:] = SURFACE
    for i in range(len(BINS)):
        lo, hi = BINS[i]
        m = (raster >= lo) & ((raster <= hi) if hi is not None else True)
        rgb[m] = RAMP[i]
    img = Image.fromarray(rgb).resize((nx * px_per_cell, ny * px_per_cell), Image.NEAREST)

    margin, legend_w, header, footer = 24, 190, 44, 56
    W, H = img.width + 2 * margin + legend_w, img.height + header + footer
    out = Image.new("RGB", (W, H), SURFACE)
    out.paste(img, (margin, header))
    d = ImageDraw.Draw(out)
    f_title, f_lbl, f_small = _font(18), _font(13), _font(11)
    d.text((margin, 12), title, fill=INK, font=f_title)
    # legend
    lx, ly = margin + img.width + 24, header
    d.text((lx, ly), "dates per cell", fill=INK_2, font=f_lbl)
    for i, (lo, hi) in enumerate(BINS):
        y = ly + 24 + i * 22
        d.rectangle([lx, y, lx + 16, y + 16], fill=RAMP[i])
        label = f"{lo}" if hi == lo else (f"{lo} to {hi}" if hi else f"{lo} or more")
        d.text((lx + 24, y + 1), label, fill=INK, font=f_lbl)
    y = ly + 24 + len(BINS) * 22 + 10
    d.text((lx, y), f"cell {cell_m:g} m", fill=MUTED, font=f_small)
    d.text((lx, y + 16), f"union {cov['union_km2']:.1f} km2", fill=MUTED, font=f_small)
    d.text((lx, y + 32), f"{cov['strips']} strips", fill=MUTED, font=f_small)
    # scale bar: 5 km if it fits, else 1 km
    for km in (10, 5, 2, 1):
        bar = int(km * 1000 / cell_m * px_per_cell)
        if bar <= img.width * 0.4:
            break
    bx, by = margin, header + img.height + 14
    d.line([bx, by, bx + bar, by], fill=INK, width=2)
    d.line([bx, by - 4, bx, by + 4], fill=INK, width=2)
    d.line([bx + bar, by - 4, bx + bar, by + 4], fill=INK, width=2)
    d.text((bx, by + 6), f"{km} km; x right, y up in the strips' projection", fill=INK_2, font=f_small)
    d.text((bx, by + 22), f"Credit: {CREDIT}", fill=MUTED, font=f_small)
    out.save(path)
    return path

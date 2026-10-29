"""A complete set of results files from synthetic ground and the fake backend.

No strip, no network, no model call, and nothing about Mars: two squares of noisy ground with bright and
dark discs drawn in, a detector-shaped candidates file for each, a persistence file that compares the two by
identity (the second square is the first with one object missing), the SAM, probe, vote and review files
the model scripts would write, their ledger, and a small coverage file. The strip names are neutral unless
the caller gives others (the blind-page test gives realistic-looking ids to prove they are removed).

The files follow the shapes of ``scripts/detect.py``, ``scripts/persist.py``, ``scripts/models_*.py`` and
``landers.models.ledger``; a change to one of those shapes should break ``tests/test_board.py`` here first.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from landers.models import run, spark
from landers.persist import FAMILY, GRADE_CANDIDATE, GRADE_LOOK

OBJECTS = [  # (row, col, radius px, bright?) in both squares; the last is in the first square only
    (300, 300, 5, True),
    (120, 450, 3, True),
    (450, 150, 4, False),
    (200, 200, 6, False),
    (500, 480, 3, True),
]
BRANCH_OF = {(True, "compact"): "bright", (False, "compact"): "dark_compact"}


def ground(seed: int, objects, size: int = 600) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    data = np.clip(500 + 30 * rng.standard_normal((size, size)), 1, 1021).astype(np.float32)
    yy, xx = np.mgrid[0:size, 0:size]
    for r, c, rad, bright in objects:
        data[(yy - r) ** 2 + (xx - c) ** 2 <= rad**2] = 900 if bright else 150
    valid = np.ones(data.shape, bool)
    valid[:, :20] = False
    return data, valid


def candidates_for(objects, seed: int, n_noise: int = 6) -> list[dict]:
    """Detector-shaped candidates: one per object plus a few noise detections, grades as the detector
    gives them (needs second look), scores on the calibrated scale."""
    rng = np.random.default_rng(seed)
    out = []
    for k, (r, c, rad, bright) in enumerate(objects):
        area = int(round(np.pi * rad * rad))
        out.append(
            {
                "row": float(r) + 0.5,
                "col": float(c) - 0.5,
                "score": round(3.0 - 0.4 * k, 3),
                "branch": "bright" if bright else "dark_compact",
                "grade": GRADE_LOOK,
                "area_px": area,
                "extra": {"circularity": round(0.9 - 0.05 * k, 3), "fill": 0.7, "raw_score": round(8.0 - k, 2)},
            }
        )
    for k in range(n_noise):
        out.append(
            {
                "row": round(float(rng.uniform(40, 560)), 1),
                "col": round(float(rng.uniform(40, 560)), 1),
                "score": round(float(rng.uniform(-2.5, 0.5)), 3),
                "branch": ["bright", "dark", "sheet", "shadow"][k % 4],
                "grade": GRADE_LOOK,
                "area_px": int(rng.integers(4, 40)),
                "extra": {"circularity": round(float(rng.uniform(0.2, 0.9)), 3)},
            }
        )
    return out


def annotate_identity(cands_a: list[dict], cands_b: list[dict], radius_px: float = 8.0) -> dict:
    """``extra.persist`` for A's candidates against B's list with no registration (same pixel grid)."""
    counts = {"seen": 0, "not_seen": 0, "unregistered": 0}
    for c in cands_a:
        fam = FAMILY.get(c["branch"], "bright")
        best = None
        for b in cands_b:
            if FAMILY.get(b["branch"], "bright") != fam:
                continue
            d = float(np.hypot(b["row"] - c["row"], b["col"] - c["col"]))
            if d <= radius_px and (best is None or d < best[0]):
                best = (d, b)
        if best is None:
            c["extra"]["persist"] = {"seen": False, "row_b": c["row"], "col_b": c["col"]}
            c["grade"] = GRADE_LOOK
            counts["not_seen"] += 1
        else:
            c["extra"]["persist"] = {
                "seen": True,
                "distance_px": round(best[0], 1),
                "branch_b": best[1]["branch"],
                "score_b": best[1]["score"],
                "row_b": c["row"],
                "col_b": c["col"],
            }
            c["grade"] = GRADE_CANDIDATE
            counts["seen"] += 1
    return counts


def by_branch(cands: list[dict]) -> dict:
    out: dict = {}
    for c in cands:
        s = out.setdefault(c["branch"], {"n": 0, "seen": 0})
        s["n"] += 1
        if c["extra"].get("persist", {}).get("seen"):
            s["seen"] += 1
    return out


def build(out_dir: Path, strip_ids: tuple[str, str] = ("demo_first", "demo_second"), top: int = 4) -> dict[str, Path]:
    """Write every file and return their paths. ``top`` is how many candidates the model passes cover."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    a, b = strip_ids
    objs_a, objs_b = OBJECTS, OBJECTS[:-1]
    data_a, valid_a = ground(1, objs_a)
    data_b, valid_b = ground(2, objs_b)
    cands = {a: candidates_for(objs_a, 11), b: candidates_for(objs_b, 12)}
    run_name = "demo"
    candidates = {
        "run": run_name,
        "detector": {"version": "demo", "frozen": False, "calibration": None},
        "git_commit": "demo",
        "strips": {
            sid: {"valid_area_km2": 0.0225, "scale_m": 0.25, "tiles": 1, "candidates": cands[sid]} for sid in (a, b)
        },
    }
    cand_path = out_dir / f"candidates_{run_name}.json"
    cand_path.write_text(json.dumps(candidates, indent=1))

    # persistence, both directions, by identity
    import copy

    directions = {}
    for src, dst in ((a, b), (b, a)):
        annotated = copy.deepcopy(cands[src])
        counts = annotate_identity(annotated, cands[dst])
        directions[f"{src}->{dst}"] = {
            "from": src,
            "to": dst,
            "registration": {
                "nodes": 1,
                "ok": 1,
                "median_drow": 0.0,
                "median_dcol": 0.0,
                "spread_px": 0.0,
                "note": "demo: identity",
            },
            "nodes": [],
            "match_radius_px": 8.0,
            "counts": counts,
            "by_branch": by_branch(annotated),
            "candidates": annotated,
        }
    persist_path = out_dir / "persist_demo_pair.json"
    persist_path.write_text(
        json.dumps(
            {"run": run_name, "git_commit": "demo", "pair": [a, b], "directions": directions, "radius_px": 8.0},
            indent=1,
        )
    )

    # the model passes on the fake backend, for the first strip only (as item 9b would run them)
    models = out_dir / "models"
    client = run.open_client("fake", models)
    read = run.array_reader(data_a, valid_a)
    ref = run.array_reader(data_b, valid_b)
    # the model scripts take the candidates file; grades there are the detector's
    top_cands = run.top_candidates(cands[a], top)
    sam_recs = run.sam_pass(client, read, top_cands, 0.25)
    run.write_json(models / f"sam_{a}.json", {"run": run_name, "backend": "fake", "records": sam_recs})
    probe = run.vote_pass(client, read, top_cands[:2], n_votes=2, probe=True)
    run.write_json(models / f"probe_{a}.json", {"run": run_name, "backend": "fake", "seed": 0, "records": probe})
    votes = run.vote_pass(client, read, top_cands, reference=ref, reference_at=(500.0, 500.0), n_votes=3, seed=0)
    run.write_json(models / f"votes_{a}.json", {"run": run_name, "backend": "fake", "seed": 0, "records": votes})
    manifest = {
        "strip": a,
        "ids": {run.candidate_id(i): {"row": c["row"], "col": c["col"]} for i, c in enumerate(top_cands)},
    }
    run.write_json(models / f"manifest_{a}.json", manifest)
    checks = run.check_runner(client, read, top_cands, 0.25)
    store = run.build_store(top_cands, {"top_n": 20}, "strip_a", sam_recs, votes, checks)
    store.request_check("c000", "second_date_check")  # one ordered check in the log, as a reviewer might
    res = spark.review(client, store, "strip_a")
    result = res.to_json()
    result["strip"] = a
    result["ids"] = manifest["ids"]
    result["checks"] = store.check_log
    run.write_json(models / f"review_{a}.json", result)

    # a coverage file, the shape item 11a is expected to write (any shape renders)
    search = out_dir / "search"
    search.mkdir(exist_ok=True)
    cov_path = search / "coverage.json"
    cov_path.write_text(
        json.dumps(
            {
                "note": "demo coverage",
                "cell_km": 1.0,
                "strips": {a: {"valid_area_km2": 0.0225, "dates": 1}, b: {"valid_area_km2": 0.0225, "dates": 1}},
                "cells": {"n": 1, "by_dates": {"2": 1}},
            },
            indent=1,
        )
    )
    return {"candidates": cand_path, "persist": persist_path, "models": models, "coverage": cov_path}

"""v2 end to end on a strip, plan item 16a: frozen-v1's detector, the combined ranking, the half-fitted rate beside each
score, and the model stage of item 14 behind one switch (``landers/v2.json``, off).

The combined ranking is each candidate's better rank of frozen-v1 and the re-ranker. It was chosen after seeing item 13's
result and only the blind run can judge it. Rows the proposer ranks below ``rerank.top`` stay out of the list, and a piece
among them counts as a miss.

Nothing here reads a key, an index or another run's list: ``ReadWatch`` refuses it while a strip runs, and the only things
taken from a strip are its pixels and its label. The model stage also opens ``controls/thresholds.json`` for the reviewer
and ``controls/sites.json`` for the prompt leak guard, which only ever refuses a prompt. A vote or a review can lower a
grade and never raises one.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from landers import config
from landers import halfcal as hc
from landers.detect import DetectorConfig, detect_strip, detect_strip_parallel
from landers.rerank import crops as rc
from landers.rerank import model as rm
from landers.search import export as ex
from landers.strip import Strip, valid_mask

CONFIG_PATH = config.REPO_ROOT / "landers" / "v2.json"
FROZEN_TAG = "frozen-v2"
FROZEN_PATHS = ("landers", "scripts/v2.py", "controls/thresholds.json", "uv.lock")
REFUSED_NAMES = {
    "tuning.json", "tuning.private.json", "heldout.json", "sites.json", "manifest.txt", "index.json", "pieces.json", "tiles.json",
}  # fmt: skip
REFUSED_DIRS = (
    "out/export", "out/search", "out/rerank/emb", "out/rerank/t10", "out/rerank/fit", "out/rerank/controls", "out/halfcal",
    "out/deep14/inputs", "out/shape_v3", "out/heldout_v1", "docs/proposals",
)  # fmt: skip


def load_json(path) -> dict:
    return json.loads(Path(path).read_text())


def load_config(path: Path = CONFIG_PATH) -> dict:
    return load_json(path)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(path)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def repo_path(p) -> Path:
    p = Path(p)
    return p if p.is_absolute() else config.REPO_ROOT / p


# ---------------------------------------------------------------- what a run may open


_watches: list[ReadWatch] = []
_hooked = False


def _audit(event: str, args: tuple) -> None:
    if event == "open" and _watches and isinstance(args[0], str | bytes | os.PathLike):
        _watches[-1].saw(os.fsdecode(args[0]))


class ReadWatch:
    """While active, opening a key, an index or another run's list raises PermissionError. ``allowed``: the exact files a
    caller was handed. Python's own opens only, so a detector's worker process is outside it; a run that must show the
    whole detector read nothing passes ``jobs=1``."""

    def __init__(self, allowed: tuple = ()):
        self.allowed = {os.path.abspath(str(p)) for p in allowed}
        self.opened: set[str] = set()

    def refused(self, path: str) -> bool:
        p = os.path.abspath(path)
        if p in self.allowed:
            return False
        if os.path.basename(p) in REFUSED_NAMES:
            return True
        return any(p == str(config.REPO_ROOT / d) or p.startswith(str(config.REPO_ROOT / d) + os.sep) for d in REFUSED_DIRS)

    def saw(self, path: str) -> None:
        if self.refused(path):
            raise PermissionError(f"{path}: a v2 run does not read this")
        p = os.path.abspath(path)
        for root, tag in ((config.REPO_ROOT, "repo"), (config.data_root(), "data")):
            if p.startswith(str(root) + os.sep) and "/.venv/" not in p and "__pycache__" not in p and not p.endswith(".py"):
                self.opened.add(f"{tag}:{os.path.relpath(p, root)}")

    def allow(self, *paths) -> None:
        self.allowed |= {os.path.abspath(str(p)) for p in paths}

    def __enter__(self) -> ReadWatch:
        global _hooked
        if not _hooked:
            sys.addaudithook(_audit)
            _hooked = True
        _watches.append(self)
        return self

    def __exit__(self, *exc) -> None:
        _watches.remove(self)


# ---------------------------------------------------------------- frozen files


def save_model(path: Path, m: rm.Fitted, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part.npz")
    np.savez_compressed(
        tmp, mean=m.mean, components=m.components, scale_mean=m.scale_mean, scale_sd=m.scale_sd, coef=m.coef,
        intercept=np.array(m.intercept), meta=np.array(json.dumps({**meta, "use": m.use})),
    )  # fmt: skip
    tmp.replace(path)


def load_model(path: Path) -> rm.Fitted:
    with np.load(path) as z:
        meta = json.loads(str(z["meta"]))
        return rm.Fitted(z["mean"], z["components"], z["scale_mean"], z["scale_sd"], z["coef"], float(z["intercept"]), meta["use"])


def save_reference(path: Path, data: np.ndarray) -> None:
    """The crop every vote image shows as its reference: raw samples, nothing about where it is from."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part.npz")
    np.savez_compressed(tmp, data=data.astype(np.uint16))
    tmp.replace(path)


class Reference:
    """The frozen reference crop, read the way item 14 read it from its strip: a square about the same centre."""

    def __init__(self, path: Path):
        with np.load(path) as z:
            self.data = z["data"]

    def read(self, row: float = 0.0, col: float = 0.0, size: int = 320):
        return centred(self.data, size)

    def for_vote(self, size: int = 320) -> tuple[np.ndarray, np.ndarray, float, float]:
        data, valid = self.read(size=size)
        return data, valid, data.shape[0] / 2.0, data.shape[1] / 2.0


def centred(raw: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray]:
    """A ``size`` px window on a crop's centre; past the crop is no data."""
    n = raw.shape[0]
    if size > n:
        pad = (size - n) // 2
        w = np.pad(raw, (pad, size - n - pad))
    else:
        i = (n - size) // 2
        w = raw[i : i + size, i : i + size]
    return w.astype(np.float32), valid_mask(w)


def detector_configs(cfg: dict, frozen: bool) -> tuple[DetectorConfig, DetectorConfig]:
    """What the files record (paths inside the repo) and what runs (absolute paths). The rule file is named in the config,
    never the newest on disk."""
    d = cfg["detector"]
    record = DetectorConfig(frozen=frozen, calibration=d["calibration"], shape_rules=d["shape_rules"])
    return record, DetectorConfig(frozen=frozen, calibration=str(repo_path(d["calibration"])), shape_rules=str(repo_path(d["shape_rules"])))


def frozen_check(run_git=None) -> str | None:
    """Why a real run may not start, or None. landers/, this command and the numbers must be as tagged."""
    import subprocess

    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True, cwd=config.REPO_ROOT)

    run_git = run_git or git
    if run_git("rev-parse", "--verify", "--quiet", f"refs/tags/{FROZEN_TAG}").returncode != 0:
        return f"no tag {FROZEN_TAG}: a person freezes v2 before any run on a strip outside the tuning proof"
    changed = run_git("diff", "--name-only", FROZEN_TAG, "--", *FROZEN_PATHS).stdout.strip()
    return f"differs from {FROZEN_TAG}: {changed.split()}" if changed else None


# ---------------------------------------------------------------- the ranking


def rank_of(x: np.ndarray) -> np.ndarray:
    r = np.zeros(len(x), int)
    r[np.argsort(-x, kind="stable")] = np.arange(1, len(x) + 1)
    return r


def fused(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The better of two ranks decides, the other breaks ties. Higher is better."""
    return -(np.minimum(a, b) + np.maximum(a, b) / (2.0 * len(a) + 1))


def top_rows(candidates: list[dict], top: int) -> tuple[list[dict], np.ndarray]:
    """The top of a strip by frozen-v1's score, in the export's form, and each row's raw score."""
    ranked = sorted(candidates, key=lambda c: -float(c["score"]))[:top]
    return ex.rank_top(ranked, top), np.array([c["extra"]["raw_score"] for c in ranked], np.float64)


def cut_stack(strip, rows: list[dict], size: int) -> np.ndarray:
    stack = np.zeros((len(rows), size, size), np.uint16)
    for win, idx in ex.read_blocks(strip, rows, size):
        for i in idx:
            stack[i] = ex.cut_square(win, rows[i]["row"], rows[i]["col"], size)
    return stack


def embed_stack(embedder, stack: np.ndarray, label, chunk: int) -> np.ndarray:
    """The crops in the export's chunks, so the encoder's batches fall where item 13's fell."""
    out = []
    for i in range(0, len(stack), chunk):
        out.append(embedder([rc.views(r, label.sub_solar_azimuth_deg, label.scale_m) for r in stack[i : i + chunk]]))
    return np.concatenate(out).astype(np.float32)


def combined(rows: list[dict], model: rm.Fitted, emb: np.ndarray) -> list[dict]:
    """The rows in combined order. ``score`` is the combined score; both source ranks and scores stay beside it."""
    frozen_scores = np.array([x["score"] for x in rows], np.float64)
    learned = model.decision(emb, frozen_scores, rm.novelty(emb))
    frozen_rank, rerank_rank = rank_of(frozen_scores), rank_of(learned)
    values = fused(frozen_rank, rerank_rank)
    out = [
        {**x, "score": float(v), "export_rank": int(x["rank"]), "frozen_rank": int(fr), "rerank_rank": int(rr),
         "frozen_score": float(fs), "rerank_score": round(float(ls), 6)}
        for x, v, fr, rr, fs, ls in zip(rows, values, frozen_rank, rerank_rank, frozen_scores, learned, strict=True)
    ]  # fmt: skip
    return sorted(out, key=lambda c: -c["score"])


def rate_column(population: list[dict], rows: list[dict], raw_top: np.ndarray, valid: np.ndarray, step: int, scale_m: float) -> list[dict]:
    """Item 15a's column: each branch's curve from the whole strip, one half at a time; beside the score only."""
    row = np.array([c["row"] for c in population], np.float64)
    col = np.array([c["col"] for c in population], np.float64)
    raw = np.array([c["extra"]["raw_score"] for c in population], np.float64)
    branch = np.array([c["branch"] for c in population])
    cals = hc.cross_fit(branch, raw, hc.colour(row, col, scale_m), hc.colour_areas(valid, step, scale_m))
    colours = hc.colour([c["row"] for c in rows], [c["col"] for c in rows], scale_m)
    q_raw = np.array([raw_top[c["export_rank"] - 1] for c in rows], np.float64)
    rate, below = hc.rates_by_other(cals, np.array([c["branch"] for c in rows]), q_raw, colours)
    out = hc.with_rate_column(rows, rate, below)
    if not hc.only_the_column_differs(rows, out):
        raise RuntimeError("the column changed something else in the list")
    return out


# ---------------------------------------------------------------- one strip, as far as the list


def strip_list(
    sid: str, work: Path, cfg: dict, cfg_run: DetectorConfig, model: rm.Fitted, embedder: Callable[[], Callable], jobs: int = 3,
    detections: dict | None = None, opener: Callable = Strip.open, detect: Callable | None = None, log: Callable = print,
) -> dict:  # fmt: skip
    """The strip's list, with each step's file written as it lands; a rerun picks up from the last one written."""
    d = work / sid
    done = d / "list.json"
    if done.exists():
        return load_json(done)
    r = cfg["rerank"]
    t0 = time.time()
    strip = opener(sid)
    path_detect = d / "detect.json"
    if detections and sid in detections:
        entry = load_json(detections[sid])["strips"][sid]
    elif path_detect.exists():
        entry = load_json(path_detect)
    else:
        if detect:
            entry = detect(strip, cfg_run)
        elif jobs > 1:
            entry = detect_strip_parallel(strip, cfg_run, jobs)
        else:
            entry = detect_strip(strip, cfg_run)
        write_json(path_detect, entry)
        log(f"{sid}: {len(entry['candidates'])} candidates from {entry['tiles']} tiles, {time.time() - t0:.0f}s")
    population = entry["candidates"]
    rows, raw_top = top_rows(population, r["top"])
    if rows:
        path_emb = d / "emb.npz"
        if path_emb.exists():
            with np.load(path_emb) as z:
                emb = z["emb"]
        else:
            emb = embed_stack(embedder(), cut_stack(strip, rows, r["crop_px"]), strip.label, r["chunk"])
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / "emb.part.npz"
            np.savez(tmp, emb=emb)
            tmp.replace(path_emb)
            log(f"{sid}: {len(rows)} crops embedded, {time.time() - t0:.0f}s")
        out = rate_column(population, combined(rows, model, emb), raw_top, strip.overview.valid, strip.overview_step, strip.label.scale_m)
    else:
        out = []
    listed = {
        "scale_m": entry["scale_m"], "valid_area_km2": entry["valid_area_km2"], "tiles": entry["tiles"],
        "candidates_total": len(population), "candidates": out,
    }  # fmt: skip
    write_json(done, listed)
    log(f"{sid}: list of {len(out)} of {len(population)}, {time.time() - t0:.0f}s")
    return listed


# ---------------------------------------------------------------- the model stage


def bounded_checks(runner, limit: int):
    """more_votes only, ``limit`` times; anything else comes back to the reviewer as a refusal."""
    used = {"n": 0}

    def check(cid: str, kind: str) -> dict:
        if kind != "more_votes":
            raise ValueError(f"{kind} is not available in this run; more_votes is")
        if used["n"] >= limit:
            raise ValueError(f"this review has used its {limit} checks")
        used["n"] += 1
        return runner(cid, kind)

    return check


def model_stage(client, lists: dict[str, dict], stacks: dict[str, np.ndarray], reference: Reference, thresholds: dict, stage: dict, out: Path, max_usd: float, probe: int = 0, log: Callable = print) -> dict:
    """Item 14's stage on these strips, on one ledger: the optional recognition probe, one vote per candidate under
    docs/proposals/vote-single-v1.md rank by rank across the strips, each vote reserved before anything is sent, then one
    Spark review per strip of the top left after the votes. Every record is written as it lands and a rerun sends nothing
    twice. ``stacks``: each strip's crops of the voted rows, cut from the strip."""
    from landers.models import run, spark
    from landers.models.ledger import CapError, PauseError

    class Stop(Exception):
        pass

    top, seed = stage["top"], stage["seed"]
    led = client.ledger

    def path_of(kind, sid):
        return out / f"{kind}_{sid}.json"

    def doc(sid):
        p = path_of("votes", sid)
        d = load_json(p) if p.exists() else {"records": []}
        return d | {"strip": sid, "backend": client.backend.name, "seed": seed}

    cands = {sid: e["candidates"][:top] for sid, e in lists.items()}
    bank = {sid: {(c["row"], c["col"]): stacks[sid][i] for i, c in enumerate(cands[sid])} for sid in stacks}
    reader = {sid: (lambda row, col, size, sid=sid: centred(bank[sid][(row, col)], size)) for sid in bank}
    voted = {sid: doc(sid) for sid in lists}
    done = {sid: {r["id"] for r in voted[sid]["records"]} for sid in lists}
    left = sum(run.candidate_id(i) not in done[sid] for sid in lists for i in range(len(cands[sid])))
    ref = reference.for_vote()

    def guard():
        if led.total_cost_usd() >= max_usd:
            raise Stop(f"this run reached its limit of {max_usd} USD")

    stopped = None
    try:
        led.reserve("wonder", left)
        for sid in lists:
            p = path_of("probe", sid)
            if probe and not p.exists():
                recs = run.vote_pass(client, reader[sid], cands[sid][:probe], reference.read, (0.0, 0.0), 3, seed=seed, probe=True, saturated_bright=True)
                if any("not_run" in r for r in recs):
                    raise CapError(next(r["not_run"] for r in recs if "not_run" in r))
                write_json(p, {"strip": sid, "backend": client.backend.name, "seed": seed, "records": recs})
        with led.spending_reserved():
            for i in range(top):
                for sid in lists:
                    cid = run.candidate_id(i)
                    if i >= len(cands[sid]) or cid in done[sid]:
                        continue
                    guard()
                    voted[sid]["records"].append(run.single_vote(client, reader[sid], cands[sid][i], i, ref, seed=seed))
                    write_json(path_of("votes", sid), voted[sid])
                    done[sid].add(cid)
        for sid in lists:
            write_json(path_of("manifest", sid), {"strip": sid, "ids": {run.candidate_id(i): {"row": c["row"], "col": c["col"]} for i, c in enumerate(cands[sid])}})
        for sid in lists:
            p = path_of("review", sid)
            if p.exists() or not cands[sid]:
                continue
            guard()
            recs = {r["id"]: r for r in voted[sid]["records"]}
            kept = [i for i, c in enumerate(cands[sid]) if recs[run.candidate_id(i)]["grade_after"] == c["grade"]][: stage["review_top"]]
            view = [cands[sid][i] for i in kept]
            view_votes = [recs[run.candidate_id(i)] | {"id": run.candidate_id(j)} for j, i in enumerate(kept)]
            checks = bounded_checks(run.check_runner(client, reader[sid], view, lists[sid]["scale_m"], saturated_bright=True), stage["checks"])
            store = run.build_store(view, thresholds, "strip_a", vote_records=view_votes, checks=checks)
            result = spark.review(client, store, "strip_a", stage["review_turns"], one_turn=True)
            write_json(p, {"strip": sid, "backend": client.backend.name, "ranks": kept, **result.to_json(), "checks": store.check_log})
    except (Stop, CapError, PauseError) as e:
        stopped = str(e)
        log(f"model stage stopped: {e}")
    return {"backend": client.backend.name, "stopped": stopped, "calls": led.units_total(), "this_run_usd": led.total_cost_usd(), "other_runs_usd": led.prior_usd}


def lowered_rows(rows: list[dict], vote_records: list[dict], review: dict | None) -> list[dict]:
    """The list after the models. A lowered row carries its new grade and goes below everything kept, staying on the list,
    as item 14's boards do; the rest are the same rows in the same order. Anything that would raise a grade stops here."""
    from landers.models.wonder import GRADES

    def not_raised(before: str, after: str) -> None:
        if before in GRADES and (after not in GRADES or GRADES.index(after) < GRADES.index(before)):
            raise ValueError(f"a model raised a grade: {before} to {after}")

    new: dict[int, dict] = {}
    for r in vote_records:
        not_raised(r["grade_before"], r["grade_after"])
        if r["grade_after"] != r["grade_before"]:
            new[int(r["id"][1:])] = {"grade": r["grade_after"], "lowered_by": "votes"}
    for cid, g in (review or {}).get("grades", {}).items():
        not_raised(g["before"], g["after"])
        if g["after"] != g["before"]:
            i = review["ranks"][int(cid[1:])]
            new[i] = {"grade": g["after"], "lowered_by": "review"}
    if not new:
        return rows
    floor = min(r["score"] for r in rows)
    span = max(r["score"] for r in rows) - floor + 1.0
    out = [
        {**r, **new[i], "grade_before_models": r["grade"], "combined_score": r["score"], "score": r["score"] - span} if i in new else r
        for i, r in enumerate(rows)
    ]
    return sorted(out, key=lambda c: -c["score"])


# ---------------------------------------------------------------- the whole command


def run_strips(
    ids: list[str], out: Path, *, cfg: dict | None = None, model_path: Path | None = None, reference_path: Path | None = None, stage_on: bool | None = None,
    backend: str | None = None, frozen: bool = False, jobs: int = 3, work: Path | None = None, detections: dict | None = None, probe: int = 0, max_usd: float = 10.0,
    embedder: Callable[[], Callable] | None = None, opener: Callable = Strip.open, detect: Callable | None = None, item: str = "17", log: Callable = print,
) -> dict:  # fmt: skip
    """v2 over ``ids``, one strip at a time. Writes ``out/candidates_v2.json`` last; a killed run reruns from what it wrote.
    Under ``ReadWatch`` throughout, so a key or an index cannot be opened by anything here."""
    from landers.search.run import git_state

    cfg = cfg or load_config()
    out, work = Path(out), Path(work) if work else Path(out) / "strips"
    stage = cfg["model_stage"]
    on = stage["on"] if stage_on is None else stage_on
    if on and not backend:
        raise ValueError("the model stage is on: name a backend")
    model_path = Path(model_path) if model_path else repo_path(cfg["rerank"]["model"])
    reference_path = Path(reference_path) if reference_path else repo_path(stage["reference"])
    record, cfg_run = detector_configs(cfg, frozen)
    state = {"config": cfg, "model_sha256": sha256_of(model_path), "detector": record.to_json(), "stage_on": on, "backend": backend if on else None}
    state_path = out / "run.json"
    if state_path.exists():
        was = load_json(state_path)
        if {k: was.get(k) for k in state} != json.loads(json.dumps(state)):
            raise SystemExit(f"{state_path}: this run's config, model or stage differs; not resuming")
    write_json(state_path, state)

    if embedder is None:

        def dino():
            from landers.rerank.embed import Dino

            return Dino(str(config.REPO_ROOT / "out" / "rerank" / "hf"), batch=cfg["rerank"]["batch"])

        embedder = _once(dino)

    allowed = tuple(Path(p) for p in (detections or {}).values())
    with ReadWatch(allowed) as watch:
        model = load_model(model_path)
        lists = {
            sid: strip_list(sid, work, cfg, cfg_run, model, embedder, jobs=jobs, detections=detections, opener=opener, detect=detect, log=log)
            for sid in ids
        }
        models = {"on": False}
        final = {sid: e["candidates"] for sid, e in lists.items()}
        if on:
            from landers.models import run as model_run

            watch.allow(config.REPO_ROOT / "controls" / "sites.json")  # the prompt leak guard's list of what must never be sent
            client = model_run.open_client(backend, out, item=item)
            stacks = {sid: cut_stack(opener(sid), e["candidates"][: stage["top"]], cfg["rerank"]["crop_px"]) for sid, e in lists.items()}
            thresholds = load_json(config.REPO_ROOT / "controls" / "thresholds.json")
            models = {"on": True, **model_stage(client, lists, stacks, Reference(reference_path), thresholds, stage, out, max_usd, probe, log)}
            for sid in lists:
                votes = out / f"votes_{sid}.json"
                review = out / f"review_{sid}.json"
                final[sid] = lowered_rows(
                    lists[sid]["candidates"], load_json(votes)["records"] if votes.exists() else [], load_json(review) if review.exists() else None
                )
        result = {
            "run": out.name, "version": cfg["version"], "list": cfg["list_label"], "detector": record.to_json(), "git": git_state(), "model_sha256": state["model_sha256"],
            "half_rate_column": hc_column_note(), "model_stage": models,
            "strips": {sid: {**{k: v for k, v in e.items() if k != "candidates"}, "candidates": final[sid]} for sid, e in lists.items()},
        }  # fmt: skip
        write_json(out / "candidates_v2.json", result)
    write_json(out / "files_read.json", {"what": "every file this process opened under the repo or the data directory, code left out", "files": sorted(watch.opened)})
    log(f"written {out / 'candidates_v2.json'}")
    return result


def _once(make: Callable) -> Callable:
    """One encoder per process, however many strips ask for it."""
    held: list = []

    def get():
        if not held:
            held.append(make())
        return held[0]

    return get


def hc_column_note() -> str:
    return (
        f"{hc.RATE_FIELD}: candidates per km2 of this strip, in this candidate's branch, at or above its raw score, measured on the half of "
        f"the strip it does not sit on; no rule gain. {hc.BELOW_FIELD}: above the top of that curve, where the data say only that the rate is below this. "
        "Beside the score only: no order and no grade comes from it."
    )

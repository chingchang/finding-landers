"""v2 end to end on a strip nobody has seen: a synthetic one, a stub detector and a stub encoder. No data, no network."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from landers import config, v2
from landers.models.wonder import GRADES
from landers.rerank import model as rm
from landers.strip import Window, valid_mask

SCALE = 0.25
SIZE = 16000  # 4 km across, so both colours of the 1 km checkerboard hold ground


class SyntheticStrip:
    """Windows are generated, not stored, so a 4 km strip costs nothing."""

    def __init__(self):
        self.label = SimpleNamespace(scale_m=SCALE, lines=SIZE, samples=SIZE, observation_id="none", sub_solar_azimuth_deg=40.0)
        self.overview_step = 16
        d = np.full((SIZE // 16, SIZE // 16), 300, np.uint16)
        self.overview = Window(0, 0, d, valid_mask(d))

    @property
    def shape(self):
        return SIZE, SIZE

    def read(self, r0, r1, c0, c1):
        r0, c0 = max(r0, 0), max(c0, 0)
        r1, c1 = min(r1, SIZE), min(c1, SIZE)
        rows, cols = np.mgrid[r0:r1, c0:c1]
        d = (300 + (rows * 7 + cols * 13) % 97).astype(np.uint16)
        return Window(r0, c0, d, valid_mask(d))


def population(n=60):
    rng = np.random.default_rng(1)
    out = []
    for i in range(n):
        out.append({
            "row": float(rng.integers(400, SIZE - 400)), "col": float(rng.integers(400, SIZE - 400)), "score": round(float(rng.normal()), 4),
            "branch": ["bright", "dark"][i % 2], "grade": GRADES[1], "area_px": 9, "extra": {"raw_score": float(rng.normal(5.0, 1.0))},
        })  # fmt: skip
    return out


def detect_stub(calls=None):
    def detect(strip, cfg):
        if calls is not None:
            calls.append(1)
        return {"valid_area_km2": 16.0, "scale_m": SCALE, "tiles": 4, "candidates": population()}

    return detect


def stub_encoder(views):
    """Eight numbers per crop, from its pixels."""
    return np.array([[f(w) for w in v for f in (np.mean, np.std, np.min, np.max)] for v in views], np.float32)


@pytest.fixture
def frozen(tmp_path):
    rng = np.random.default_rng(2)
    emb = rng.normal(size=(40, 8)).astype(np.float32)
    y = (emb[:, 0] > 0).astype(float)
    m = rm.fit(emb, rng.normal(size=40), rng.normal(size=40), y, np.ones(40))
    model = tmp_path / "model.npz"
    v2.save_model(model, m, {"variant": "primary"})
    reference = tmp_path / "reference.npz"
    v2.save_reference(reference, SyntheticStrip().read(0, 384, 0, 384).data)
    cfg = v2.load_config()
    cfg = {**cfg, "rerank": {**cfg["rerank"], "top": 30, "chunk": 8, "crop_px": 320}, "model_stage": {**cfg["model_stage"], "top": 5, "on": False}}
    return SimpleNamespace(m=m, model=model, reference=reference, cfg=cfg)


def run(frozen, out, **kw):
    kw.setdefault("detect", detect_stub())
    return v2.run_strips(
        ["never_seen"], out, cfg=frozen.cfg, model_path=frozen.model, reference_path=frozen.reference, embedder=lambda: stub_encoder,
        opener=lambda sid: SyntheticStrip(), log=lambda *_: None, **kw,
    )  # fmt: skip


def test_better_rank_decides_and_the_other_breaks_ties():
    assert v2.rank_of(np.array([0.1, 0.9, 0.5])).tolist() == [3, 1, 2]
    a, b = np.array([1, 2, 3, 4]), np.array([4, 3, 1, 2])
    order = np.argsort(-v2.fused(a, b), kind="stable").tolist()
    assert order == [2, 0, 1, 3]  # both best ranks of 1 first, the lower second rank (3, then 4) ahead; then the two of 2


def test_model_file_gives_the_same_decisions(frozen):
    x = np.random.default_rng(3).normal(size=(5, 8)).astype(np.float32)
    s, n = np.arange(5.0), np.ones(5)
    assert np.array_equal(v2.load_model(frozen.model).decision(x, s, n), frozen.m.decision(x, s, n))


@pytest.mark.parametrize(
    "path",
    ["controls/tuning.json", "controls/heldout.json", "controls/sites.json", "out/export/strips/x/index.json", "out/search/candidates/a.json", "out/deep14/inputs/candidates_combined.json", "out/halfcal/column/a.json"],
)
def test_the_watch_refuses_keys_indexes_and_other_lists(path):
    with v2.ReadWatch() as w, pytest.raises(PermissionError):
        w.saw(str(config.REPO_ROOT / path))


def test_the_watch_stops_a_real_open_and_ends_with_its_block(tmp_path):
    key = tmp_path / "heldout.json"
    key.write_text("{}")
    with v2.ReadWatch(), pytest.raises(PermissionError):
        open(key)
    assert open(key).read() == "{}"
    with v2.ReadWatch((key,)) as w:
        assert open(key).read() == "{}"
    assert not w.refused(str(key))


def test_a_detector_that_opens_the_key_is_stopped(frozen, tmp_path):
    def peeking(strip, cfg):
        open(config.REPO_ROOT / "controls" / "tuning.json")

    with pytest.raises(PermissionError):
        run(frozen, tmp_path / "out", detect=peeking)


def test_unseen_strip_end_to_end_stage_off(frozen, tmp_path):
    out = tmp_path / "out"
    r = run(frozen, out)
    e = r["strips"]["never_seen"]
    rows = e["candidates"]
    assert r["model_stage"] == {"on": False}
    assert "chosen after seeing item 13" in r["list"]
    assert e["candidates_total"] == 60 and len(rows) == 30
    assert sorted(c["frozen_rank"] for c in rows) == list(range(1, 31)) == sorted(c["rerank_rank"] for c in rows)
    assert [c["score"] for c in rows] == sorted((c["score"] for c in rows), reverse=True)
    best = np.array([min(c["frozen_rank"], c["rerank_rank"]) for c in rows])
    assert (np.diff(best) >= 0).all()
    assert all((c["half_rate_per_km2"] is None) != (c["half_rate_below_per_km2"] is None) for c in rows)
    assert json.loads((out / "candidates_v2.json").read_text())["strips"]["never_seen"]["candidates"] == rows
    names = json.loads((out / "files_read.json").read_text())["files"]
    assert not any(Path(n).name in v2.REFUSED_NAMES for n in names)


def test_the_top_of_the_list_is_the_frozen_top_and_a_rerun_detects_nothing(frozen, tmp_path):
    calls = []
    first = run(frozen, tmp_path / "out", detect=detect_stub(calls))
    assert calls == [1]
    want = sorted(population(), key=lambda c: -c["score"])[:30]
    rows = sorted(first["strips"]["never_seen"]["candidates"], key=lambda c: c["export_rank"])
    assert [(c["row"], c["col"], c["frozen_score"]) for c in rows] == [(c["row"], c["col"], c["score"]) for c in want]
    again = run(frozen, tmp_path / "out", detect=detect_stub(calls))
    assert calls == [1] and again["strips"] == first["strips"]


def test_a_changed_model_is_not_resumed(frozen, tmp_path):
    run(frozen, tmp_path / "out")
    v2.save_model(frozen.model, frozen.m, {"variant": "other"})
    with pytest.raises(SystemExit):
        run(frozen, tmp_path / "out")


def test_a_strip_with_no_candidates_gives_an_empty_list(frozen, tmp_path):
    def nothing(strip, cfg):
        return {"valid_area_km2": 16.0, "scale_m": SCALE, "tiles": 4, "candidates": []}

    assert run(frozen, tmp_path / "out", detect=nothing)["strips"]["never_seen"]["candidates"] == []


def test_the_rate_column_changes_only_the_column(frozen, tmp_path):
    rows = run(frozen, tmp_path / "a")["strips"]["never_seen"]["candidates"]
    assert all(set(c) >= {"row", "col", "grade", "frozen_rank", "rerank_rank", "half_rate_per_km2", "half_rate_below_per_km2"} for c in rows)
    pop = population()
    raw_top = np.array([c["extra"]["raw_score"] for c in sorted(pop, key=lambda c: -c["score"])[:30]])
    bare = [{k: v for k, v in c.items() if not k.startswith("half_rate")} for c in rows]
    strip = SyntheticStrip()
    assert v2.rate_column(pop, bare, raw_top, strip.overview.valid, 16, SCALE) == rows


def test_the_stage_on_the_fake_backend_changes_nothing_in_the_list(frozen, tmp_path):
    work = tmp_path / "strips"
    off = run(frozen, tmp_path / "off", work=work)
    on = run(frozen, tmp_path / "on", work=work, stage_on=True, backend="fake")
    assert on["strips"] == off["strips"]
    assert on["model_stage"]["on"] and on["model_stage"]["stopped"] is None
    votes = json.loads((tmp_path / "on" / "votes_never_seen.json").read_text())["records"]
    assert len(votes) == 5 and all(r["rule"] == "vote-single-v1" and r["crop_draw"] == "saturated-bright" for r in votes)
    assert (tmp_path / "on" / "review_never_seen.json").exists()
    assert (tmp_path / "on" / "ledger.json").exists()
    # a rerun sends nothing twice
    calls = on["model_stage"]["calls"]
    assert run(frozen, tmp_path / "on", work=work, stage_on=True, backend="fake")["model_stage"]["calls"] == calls


def test_the_stage_refuses_to_run_without_a_backend(frozen, tmp_path):
    with pytest.raises(ValueError):
        run(frozen, tmp_path / "out", stage_on=True)


def test_the_switch_in_the_config_turns_the_stage_on(frozen, tmp_path):
    frozen.cfg["model_stage"]["on"] = True
    assert run(frozen, tmp_path / "out", backend="fake")["model_stage"]["on"]


def rows_for_grades(n=4):
    return [{"row": float(i), "col": 0.0, "score": -float(i + 1), "grade": GRADES[1]} for i in range(n)]


def record(i, before, after):
    return {"id": f"c{i:03d}", "grade_before": before, "grade_after": after}


def test_a_lowered_row_goes_below_everything_kept_and_stays_on_the_list():
    rows = rows_for_grades()
    out = v2.lowered_rows(rows, [record(0, GRADES[1], GRADES[2])], None)
    assert [r["row"] for r in out] == [1.0, 2.0, 3.0, 0.0]
    assert out[-1]["grade"] == GRADES[2] and out[-1]["grade_before_models"] == GRADES[1] and out[-1]["lowered_by"] == "votes"
    assert out[0] == rows[1]


def test_a_review_lowers_the_row_it_names_through_its_ranks():
    rows = rows_for_grades()
    review = {"ranks": [1, 3], "grades": {"c000": {"before": GRADES[1], "after": GRADES[1]}, "c001": {"before": GRADES[1], "after": GRADES[2]}}}
    out = v2.lowered_rows(rows, [], review)
    assert out[-1]["row"] == 3.0 and out[-1]["lowered_by"] == "review"


def test_nothing_lowered_returns_the_same_rows():
    rows = rows_for_grades()
    assert v2.lowered_rows(rows, [record(0, GRADES[1], GRADES[1])], None) is rows


def test_a_model_can_never_raise_a_grade():
    with pytest.raises(ValueError):
        v2.lowered_rows(rows_for_grades(), [record(0, GRADES[1], GRADES[0])], None)
    with pytest.raises(ValueError):
        v2.lowered_rows(rows_for_grades(), [], {"ranks": [0], "grades": {"c000": {"before": GRADES[2], "after": GRADES[1]}}})


def git_stub(tag=True, changed=""):
    def git(*args):
        if args[0] == "rev-parse":
            return SimpleNamespace(returncode=0 if tag else 1, stdout="")
        return SimpleNamespace(returncode=0, stdout=changed)

    return git


def test_a_real_run_needs_the_tag_and_the_frozen_files_as_tagged():
    assert "no tag" in v2.frozen_check(git_stub(tag=False))
    assert "differs" in v2.frozen_check(git_stub(changed="landers/v2.json\n"))
    assert v2.frozen_check(git_stub()) is None


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, config.REPO_ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_command_refuses_before_the_freeze(monkeypatch, tmp_path):
    cmd = load_script("v2")
    monkeypatch.setattr(cmd.v2, "frozen_check", lambda: "no tag")
    monkeypatch.setattr(cmd.v2, "run_strips", lambda *a, **k: pytest.fail("ran"))
    assert cmd.main(["any", "--out", str(tmp_path)]) == 3


def test_the_command_runs_marked_frozen_once_the_tag_is_there(monkeypatch, tmp_path):
    cmd = load_script("v2")
    seen = {}
    monkeypatch.setattr(cmd.v2, "frozen_check", lambda: None)
    monkeypatch.setattr(cmd.v2, "run_strips", lambda ids, out, **k: seen.update(ids=ids, **k))
    assert cmd.main(["a", "b", "--out", str(tmp_path), "--detections", "a=f.json"]) == 0
    assert seen["ids"] == ["a", "b"] and seen["frozen"] is True and seen["detections"] == {"a": "f.json"}


def test_the_run_path_never_names_the_key_code():
    for path in ("landers/v2.py", "scripts/v2.py"):
        text = (config.REPO_ROOT / path).read_text()
        assert "rerank as rr" not in text and "import score" not in text


def test_the_config_names_its_files_and_they_exist():
    cfg = v2.load_config()
    for p in (cfg["detector"]["calibration"], cfg["detector"]["shape_rules"], cfg["rerank"]["model"], cfg["model_stage"]["reference"]):
        assert (config.REPO_ROOT / p).exists(), p
    assert cfg["detector"]["shape_rules"] == "landers/shape_v3.json"
    record_cfg, run_cfg = v2.detector_configs(cfg, True)
    assert record_cfg.frozen and record_cfg.shape_rules == "landers/shape_v3.json" and Path(run_cfg.shape_rules).is_absolute()

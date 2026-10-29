"""scripts/detect.py writes after every strip and can resume an interrupted run of the same config."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "detect.py"


def _load():
    spec = importlib.util.spec_from_file_location("detect_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_write_result_is_atomic_and_resume_keeps_finished_strips(tmp_path):
    m = _load()
    cfg = m.DetectorConfig(calibration=None).to_json()  # tuples here, lists once read back
    path = tmp_path / "candidates_r.json"
    first = {"run": "r", "detector": cfg, "started": "t0", "git_commit": "abc", "strips": {"S1": {"tiles": 3}}}
    m.write_result(path, first)
    assert json.loads(path.read_text())["strips"] == {"S1": {"tiles": 3}}
    assert not list(tmp_path.glob("*.part"))

    fresh = {"run": "r", "detector": cfg, "started": "t1", "git_commit": "def", "strips": {}}
    resumed = m.resume_from(path, fresh)
    assert resumed["strips"] == {"S1": {"tiles": 3}}
    assert resumed["resumed_from"] == {"started": "t0", "git_commit": "abc"}

    other = {"run": "r", "detector": {**cfg, "z_bright": 5.0}, "started": "t2", "git_commit": "x", "strips": {}}
    with pytest.raises(SystemExit):
        m.resume_from(path, other)  # a different detector must not be stitched onto the old strips

    missing = tmp_path / "candidates_none.json"
    untouched = {"run": "r", "detector": cfg, "started": "t3", "git_commit": "y", "strips": {}}
    assert m.resume_from(missing, untouched)["strips"] == {}

"""Item 16b's driver: which strips it takes, what it refuses, and how it reads the run's log. No data, no network."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def driver():
    spec = importlib.util.spec_from_file_location("v2_search_prep", ROOT / "experiments" / "v2_search_prep.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_strips_come_from_the_single_strip_commands_in_order():
    text = """# a comment
uv run --group rerank scripts/v2.py B --out out/v2/search --detections B=b.json
uv run --group rerank scripts/v2.py A --out out/v2/search --detections A=a.json
# the whole list
uv run --group rerank scripts/v2.py B A --out out/v2/search --detections B=b.json A=a.json
"""
    assert driver().search_strips(text) == ["B", "A"]


def test_a_strip_named_twice_stops_the_pass():
    line = "uv run scripts/v2.py A --out x\n"
    with pytest.raises(ValueError):
        driver().search_strips(line + line)


def test_a_strip_on_the_control_list_is_refused_whatever_its_group():
    sites = {"sites": [{"strips": ["K"], "group": "tuning"}, {"strips": ["H"], "group": "heldout"}]}
    d = driver()
    d.refuse_controls(["A", "B"], sites)
    for strip in ("K", "H"):
        with pytest.raises(SystemExit):
            d.refuse_controls(["A", strip], sites)


def test_timings_read_the_log_lines_the_run_writes():
    d = driver()
    assert d.seconds_of("S: 2000 crops embedded, 61s") == ("S", "embedded", 61.0)
    assert d.seconds_of("S: list of 2000 of 70000, 75s") == ("S", "listed", 75.0)
    assert d.seconds_of("written out/v2/search_prep/candidates_v2.json") is None

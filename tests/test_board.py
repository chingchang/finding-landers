"""The case board on the fake backend's outputs: every value traced, the vocabulary fixed, nothing raised,
and the blind page clean."""

import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from landers.board import demo, load, render
from landers.board.load import ALL_GRADES, JoinError, Source, VocabularyError

ROOT = Path(__file__).resolve().parent.parent
BANNED = ("found", "discovered", "confirmed", "proven")


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("demo")
    return d, demo.build(d)


@pytest.fixture(scope="module")
def case(files):
    d, p = files
    return load.load_case(p["candidates"], p["models"], None, p["coverage"], None, None, top=6)


class Reader(HTMLParser):
    """Text outside traced spans, the spans themselves, and model quotes."""

    def __init__(self):
        super().__init__()
        self.in_span = 0
        self.in_q = 0
        self.in_style = False
        self.spans: list[dict] = []
        self.loose: list[str] = []
        self.own_words: list[str] = []
        self._cur = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "style":
            self.in_style = True
        if tag == "span" and "data-src" in a:
            self.in_span += 1
            self._cur = {
                "src": a["data-src"],
                "path": json.loads(a["data-path"]),
                "op": a.get("data-op", ""),
                "text": "",
            }
            self.spans.append(self._cur)
        if tag == "q":
            self.in_q += 1

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False
        if tag == "span" and self.in_span:
            self.in_span -= 1
            self._cur = None
        if tag == "q" and self.in_q:
            self.in_q -= 1

    def handle_data(self, data):
        if self.in_style:
            return
        if self.in_span:
            self._cur["text"] += data
        else:
            self.loose.append(data)
            if not self.in_q:
                self.own_words.append(data)


def read(page: str) -> Reader:
    r = Reader()
    r.feed(page)
    return r


def test_demo_writes_the_shapes_the_scripts_write(files):
    d, p = files
    cands = json.loads(p["candidates"].read_text())
    assert set(cands["strips"]) == {"demo_first", "demo_second"}
    assert {"row", "col", "score", "branch", "grade", "area_px", "extra"} <= set(
        cands["strips"]["demo_first"]["candidates"][0]
    )
    for kind in ("sam", "votes", "probe", "review", "manifest"):
        assert (p["models"] / f"{kind}_demo_first.json").exists()
    assert (p["models"] / "ledger.json").exists()
    pers = json.loads(p["persist"].read_text())
    assert set(pers["directions"]) == {"demo_first->demo_second", "demo_second->demo_first"}


def test_case_joins_the_files_and_keeps_grades_monotone(case):
    assert [s.strip for s in case.strips] == ["demo_first", "demo_second"]
    a = case.strips[0]
    assert a.list_stage == "persistence" and a.model_files == {
        "sam": "sam:demo_first",
        "votes": "votes:demo_first",
        "probe": "probe:demo_first",
        "review": "review:demo_first",
    }
    assert len(a.candidates) == 6
    c0 = a.candidates[0]
    assert (
        c0.cid == "c000"
        and c0.rank == 1
        and [s.name for s in c0.chain] == ["detector", "persistence", "votes", "review"]
    )
    assert c0.persist["seen"].value is True and c0.chain[1].after.value == "candidate"
    # the vote and review stages were run from the candidates file, whose grade is the detector's, so the
    # chain is inconsistent there and the board says so rather than hiding it
    assert any("votes: started from needs second look" in f for f in c0.flags)
    assert c0.final == "needs second look", "the lowest grade along the chain, never a raise"
    assert c0.sam["found"].value is True and c0.tests["sam_size"]["outcome"].value in ("pass", "fail", "unsure")
    assert len(c0.votes) == 3 and c0.verdict["action"].value == "keep"
    assert c0.probe["n"].value == 2 and c0.checks and c0.checks[0].value["kind"] == "second_date_check"
    last = a.candidates[-1]
    assert last.sam is None and last.votes is None and last.verdict is None, "beyond the model passes"
    assert sum(r.value for r in a.list_grade_counts.values()) == a.n_candidates.value
    assert sum(r.value for r in a.shown_grade_counts.values()) == len(a.candidates)
    b = case.strips[1]
    assert b.model_files == {} and b.review is None and b.list_stage == "persistence"
    assert a.review["verdicts"].value == 4 and a.review["lowered"].value == 0 and a.review["checks"].value == 1
    assert case.ledger is not None and case.coverage is not None


def test_every_value_on_the_page_is_traced_to_its_file(case, files):
    d, p = files
    page, trace = render.render(case)
    r = read(page)
    loose = re.sub(r"\bc\d{3}\b", "", "\n".join(r.loose))  # candidate ids are names, not numbers
    assert not re.search(r"\d", loose), f"untraced digits on the page: {re.findall(r'[^\n]*\d[^\n]*', loose)[:5]}"
    assert r.spans and len(r.spans) == len(trace["values"])
    sources = {s.key: s for s in case.sources}
    checked = 0
    for sp in r.spans:
        src = sources[sp["src"]]
        path = tuple(sp["path"])
        if sp["op"] == "":
            assert sp["text"] == render.fmt(src.walk(path)), (sp, src.walk(path))
            checked += 1
        elif sp["op"] == "count":
            assert int(sp["text"]) == len(src.walk(path))
        elif sp["op"].startswith("count where"):
            assert int(sp["text"]) <= len(src.walk(path))
        elif sp["op"] == "rank by score":
            assert 1 <= int(sp["text"]) <= len(src.walk(path))
        elif sp["op"].startswith("sha256"):
            assert sp["text"] == src.sha256
        elif sp["op"].startswith("path of"):
            assert sp["text"] == str(src.path)
        elif sp["op"] == "key":
            assert sp["text"] in src.walk(path), "a key shown as a label exists in the file"
        else:
            raise AssertionError(f"unknown op {sp['op']}")
    assert checked > 100
    # the trace sidecar names every file with its hash
    assert set(trace["sources"]) == set(sources) and all("sha256" in v for v in trace["sources"].values())


def test_the_boards_own_words_are_the_fixed_vocabulary(case):
    page, _ = render.render(case)
    r = read(page)
    own = " ".join(r.own_words).lower()
    for w in BANNED:
        assert not re.search(rf"\b{w}\b", own), w
    for g in ALL_GRADES:
        assert g in own
    # model text is quoted and labelled as such, never rewritten
    assert 'class="model"' in page and "fake backend: no opinion" in page


def test_vocabulary_outside_the_fixed_set_stops_the_build(files, tmp_path):
    d, p = files
    bad = tmp_path / "candidates_bad.json"
    data = json.loads(p["candidates"].read_text())
    data["strips"]["demo_first"]["candidates"][0]["grade"] = "confirmed"
    bad.write_text(json.dumps(data))
    with pytest.raises(VocabularyError, match="grade 'confirmed'"):
        load.load_case(bad, None, [], None, None, None)
    data["strips"]["demo_first"]["candidates"][0]["grade"] = "needs second look"
    data["strips"]["demo_first"]["candidates"][0]["tests"] = {"height": {"outcome": "maybe", "value": 1, "limit": 2}}
    bad.write_text(json.dumps(data))
    with pytest.raises(VocabularyError, match="outcome 'maybe'"):
        load.load_case(bad, None, [], None, None, None)


def test_a_file_that_raises_a_grade_is_flagged_not_believed(files, tmp_path):
    d, p = files
    models = tmp_path / "models"
    models.mkdir()
    for f in p["models"].glob("*.json"):
        (models / f.name).write_text(f.read_text())
    rv = json.loads((models / "review_demo_first.json").read_text())
    rv["grades"]["c001"] = {"before": "needs second look", "after": "candidate", "reviewed": True}
    (models / "review_demo_first.json").write_text(json.dumps(rv))
    case = load.load_case(p["candidates"], models, [], None, None, None, top=3)
    c1 = case.strips[0].candidates[1]
    assert any("grade raised" in f for f in c1.flags) and c1.final == "needs second look"
    page, _ = render.render(case)
    assert "grade raised from needs second look to candidate" in page


def test_persistence_file_for_other_candidates_is_refused(files, tmp_path):
    d, p = files
    pers = json.loads(p["persist"].read_text())
    pers["directions"]["demo_first->demo_second"]["candidates"][0]["row"] += 1.0
    bad = tmp_path / "persist_x.json"
    bad.write_text(json.dumps(pers))
    with pytest.raises(JoinError):
        load.load_case(p["candidates"], None, [bad], None, None, None)


def test_manifest_mismatch_unjoins_the_model_files(files, tmp_path):
    d, p = files
    models = tmp_path / "models"
    models.mkdir()
    for f in p["models"].glob("*.json"):
        (models / f.name).write_text(f.read_text())
    m = json.loads((models / "manifest_demo_first.json").read_text())
    m["ids"]["c000"]["row"] += 5
    (models / "manifest_demo_first.json").write_text(json.dumps(m))
    case = load.load_case(p["candidates"], models, [], None, None, None, top=3)
    st = case.strips[0]
    assert st.manifest_note and "c000" in st.manifest_note and st.model_files == {}
    assert st.candidates[0].sam is None


def test_blind_page_carries_no_id_or_position(tmp_path):
    ids = ("ESP_" + "012345_1234", "PSP_" + "001234_1234")  # realistic ids, built so the file check does not see them
    p = demo.build(tmp_path / "d", ids)
    case = load.load_case(p["candidates"], p["models"], None, p["coverage"], None, None, top=5)
    page, trace = render.render(case, blind=True)
    assert "strip_a" in page and "strip_b" in page
    for sid in ids:
        assert sid not in page and sid not in json.dumps(trace)
    assert "persist:demo_pair" not in page and "persist:a" in page
    assert "row" not in [h for h in re.findall(r"<th>([^<]*)</th>", page)]
    assert "Score against the tuning key" not in page
    # the open page shows them
    open_page, _ = render.render(case, blind=False)
    assert ids[0] in open_page


def test_score_section_renders_from_a_score_file(files, tmp_path):
    d, p = files
    sc = {
        "recall_at_n": 0.5,
        "top_n": 20,
        "n_pieces_recorded": 2,
        "n_pieces_found": 1,
        "median_false_alarms_per_km2": 1.5,
        "passed": False,
        "matching": "one_to_one",
        "pieces": [
            {
                "site": "demo",
                "piece": "lander",
                "kind": "hardware",
                "strip": "demo_first",
                "rank": 1,
                "distance_px": 0.7,
                "branch": "bright",
            }
        ],
        "strips": [
            {
                "strip": "demo_first",
                "n_candidates": 11,
                "n_true_hits": 1,
                "false_alarms": 10,
                "valid_area_km2": 0.0225,
                "false_alarms_per_km2": 444.4,
            }
        ],
        "skipped": ["demo/parachute: position not recorded"],
    }
    sp = tmp_path / "score_demo.json"
    sp.write_text(json.dumps(sc))
    case = load.load_case(p["candidates"], None, [], None, sp, None, top=2)
    page, _ = render.render(case)
    r = read(page)
    loose = re.sub(r"\bc\d{3}\b", "", "\n".join(r.loose))
    assert "Score against the tuning key" in page and not re.search(r"\d", loose)
    assert any(s["src"] == "score" and s["path"] == ["pieces", 0, "rank"] and s["text"] == "1" for s in r.spans)


def test_generic_rendering_traces_any_shape(tmp_path):
    f = tmp_path / "cov.json"
    f.write_text(
        json.dumps({"a": 1, "b": {"c": [1, 2, {"d": 3.5, "e": [4]}]}, "f": [{"g": 5, "h": {"i": 6}}, {"g": 7}]})
    )
    src = Source.read("coverage", f)
    pg = render.Page([src])
    pg.generic(src, ())
    page = "".join(pg.parts)
    r = read(page)
    assert not re.search(r"\d", "".join(r.loose))
    assert {json.dumps(s["path"]) for s in r.spans} >= {
        '["a"]',
        '["b", "c", 1]',
        '["b", "c", 2, "d"]',
        '["f", 0, "h", "i"]',
        '["f", 1, "g"]',
    }


def test_script_builds_the_demo_and_the_page(tmp_path):
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "board.py"), "--demo", str(tmp_path / "demo")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert r.returncode == 0, r.stderr
    out = tmp_path / "demo" / "board" / "index.html"
    assert out.exists() and (tmp_path / "demo" / "board" / "index_trace.json").exists()
    assert "written:" in r.stdout
    r2 = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "board.py"),
            str(tmp_path / "demo" / "candidates_demo.json"),
            "--models",
            str(tmp_path / "demo" / "models"),
            "--coverage",
            str(tmp_path / "demo" / "search" / "coverage.json"),  # not the default: a real one may exist in out/
            "--blind",
            "--out",
            str(tmp_path / "b.html"),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert r2.returncode == 0, r2.stderr
    assert "demo_first" not in (tmp_path / "b.html").read_text()

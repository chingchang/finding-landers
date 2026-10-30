"""The few-shot vote (plan item 9d) on the fake backend: pools, leave one site out, the example view, the
prompt text, and that the plain prompt is unchanged."""

import numpy as np
import pytest

from landers.models import crops, fewshot, leak, run, wonder
from landers.models.backend import FakeBackend, ModelClient, request_hash
from landers.models.ledger import Ledger

THRESHOLDS = {
    "top_n": 20,
    "match_radius_m": 5.0,
    "piece_kinds": {"hardware": ["lander", "backshell"], "fabric": ["parachute"], "mark": ["crash_scar"]},
    "match_radius_m_by_kind": {"mark": 20.0},
}

KEY = {
    "sites": [
        {
            "name": "alpha",
            "strips": ["A1", "A2"],
            "pieces": [
                {"piece": "lander", "strip": "A1", "line": 101, "sample": 201},
                {"piece": "crash_scar", "strip": "A1", "line": 301, "sample": 301},
                {"piece": "parachute", "strip": None, "line": None, "sample": None},
            ],
        },
        {"name": "beta", "strips": ["B1"], "pieces": [{"piece": "backshell", "strip": "B1", "line": 51, "sample": 51}]},
        {"name": "gamma", "strips": ["C1"], "pieces": [{"piece": "parachute", "strip": "C1", "line": 11, "sample": 11}]},
    ]
}


def inputs():
    return {
        "strips": {
            "A1": {"scale_m": 0.25, "candidates": [{"row": 100, "col": 200, "score": 9}, {"row": 900, "col": 900, "score": 8}]},
            "B1": {"scale_m": 0.5, "candidates": [{"row": 50.5, "col": 50, "score": 9}, {"row": 400, "col": 10, "score": 1}]},
            "C1": {"scale_m": 0.25, "candidates": [{"row": 700, "col": 700, "score": 3}]},
        }
    }


def test_pools_take_hardware_and_fabric_pieces_and_top_false_alarms():
    hw = fewshot.hardware_pool(KEY, THRESHOLDS)
    assert sorted(e.what for e in hw) == ["backshell", "lander", "parachute"], "no mark, no unrecorded piece"
    assert all(e.label == "hardware" for e in hw)
    lander = next(e for e in hw if e.what == "lander")
    assert (lander.row, lander.col) == (100.0, 200.0), "key lines and samples are 1-based"
    nat = fewshot.natural_pool(KEY, THRESHOLDS, inputs())
    assert sorted((e.strip, e.row) for e in nat) == [("A1", 900), ("B1", 400), ("C1", 700)], "hits are not examples"
    assert fewshot.natural_pool(KEY, THRESHOLDS, inputs(), top=1) == [n for n in nat if n.strip == "C1"]


def test_leave_one_site_out_drops_every_strip_of_the_site():
    pool = fewshot.hardware_pool(KEY, THRESHOLDS) + fewshot.natural_pool(KEY, THRESHOLDS, inputs())
    out = fewshot.leave_site_out(pool, "alpha")
    assert out and all(e.site != "alpha" and e.strip != "A1" for e in out)
    assert fewshot.site_of_strip(KEY)["A2"] == "alpha"


def test_draw_is_seeded_balanced_and_refuses_small_pools():
    hw = fewshot.hardware_pool(KEY, THRESHOLDS)
    nat = fewshot.natural_pool(KEY, THRESHOLDS, inputs())
    a = fewshot.draw(np.random.default_rng([0, 1, 2]), hw, nat, 2)
    b = fewshot.draw(np.random.default_rng([0, 1, 2]), hw, nat, 2)
    assert a == b and sorted(e.label for e in a) == ["hardware", "hardware", "natural", "natural"]
    with pytest.raises(ValueError):
        fewshot.draw(np.random.default_rng(0), hw[:1], nat, 2)


def test_example_view_resamples_turns_with_the_sun_and_flips_with_the_candidate():
    # a bright bar pointing to +col from the centre in the source; the source sun at 0, the target at 90 deg
    data = np.full((400, 400), 500.0, np.float32)
    data[198:203, 200:212] = 900.0
    read = run.array_reader(data, np.ones(data.shape, bool))
    plain = crops.Augmentation()
    same = fewshot.example_u8(read, 200, 200, fewshot.View(0.25, 0.0, 0.25, 0.0), plain)
    assert same.shape == (256, 256) and same[128, 160] > 200 and same[160, 128] < 100
    turned = fewshot.example_u8(read, 200, 200, fewshot.View(0.25, 0.0, 0.25, 90.0), plain)
    # a direction (sin a, cos a) at azimuth 0 becomes azimuth 90: +col turns into +row
    assert turned[160, 128] > 200 and turned[128, 160] < 100
    half = fewshot.example_u8(read, 200, 200, fewshot.View(0.5, 0.0, 0.25, 0.0), plain)
    # a 12 px bar is 48 zoomed px long at the same scale, 96 when the source is at twice the metres per pixel
    assert half[128, 200] > 200 and same[128, 200] < 100
    flipped = fewshot.example_u8(read, 200, 200, fewshot.View(0.25, 0.0, 0.25, 0.0), crops.Augmentation(flip_h=True))
    assert flipped[128, 96] > 200 and flipped[128, 160] < 100


def source(data):
    read = run.array_reader(data, np.ones(data.shape, bool))
    hw = fewshot.hardware_pool(KEY, THRESHOLDS)
    nat = fewshot.natural_pool(KEY, THRESHOLDS, inputs())
    readers = {s: read for s in ("A1", "B1", "C1")}
    views = {s: fewshot.View(0.25, 10.0, 0.25, 40.0) for s in readers}
    return fewshot.ExampleSource(fewshot.leave_site_out(hw, "alpha"), fewshot.leave_site_out(nat, "alpha"), readers, views)


def test_fewshot_vote_pass_sends_examples_with_labels_only(tmp_path):
    rng = np.random.default_rng(0)
    data = np.clip(500 + 30 * rng.standard_normal((1000, 1000)), 1, 1021).astype(np.float32)
    read = run.array_reader(data)
    cands = [{"row": 500.0, "col": 500.0, "score": 2.0, "branch": "bright", "grade": "needs second look"}]
    fake = FakeBackend()
    cl = ModelClient(fake, Ledger(tmp_path / "l.json"))
    src = source(data)
    recs = run.vote_pass(cl, read, cands, reference=read, reference_at=(300, 300), n_votes=3, examples=src)
    assert recs[0]["prompt"] == wonder.FEWSHOT_VERSION and len(recs[0]["votes"]) == 3
    assert recs[0]["crops"][0]["examples"].count("hardware") == 2
    assert len(src.drawn) == 3 and all(e.site != "alpha" for ex in src.drawn.values() for e in ex)
    # the request: 3 crop images + 4 examples, labelled by image number, nothing else about them
    aug = crops.Augmentation()
    view = crops.build_crop(*read(500, 500, 384), 192, 192, 256, 4, aug, (*read(300, 300, 384), 192, 192))
    view.examples = src(0, 0, aug)
    req = wonder.vote_request(view)
    assert len(req.images) == 7
    labels = recs[0]["crops"][0]["examples"]
    assert f"image 4 {labels[0]} example" in req.question and "image 7" in req.question and "image 8" not in req.question
    for t in req.texts():
        assert leak.find_leak(t) is None
    for word in ("alpha", "beta", "gamma", "A1", "B1", "C1", "rank", "lander", "backshell", "parachute"):
        assert word not in req.question


def test_plain_prompt_is_unchanged_and_only_keeps_the_augmentations(tmp_path):
    data = np.clip(500 + 30 * np.random.default_rng(1).standard_normal((800, 800)), 1, 1021).astype(np.float32)
    read = run.array_reader(data)
    cands = [
        {"row": 300.0 + 50 * i, "col": 400.0, "score": 5.0 - i, "branch": "bright", "grade": "needs second look"}
        for i in range(3)
    ]
    full_fake, part_fake = FakeBackend(), FakeBackend()
    full = run.vote_pass(ModelClient(full_fake, Ledger(tmp_path / "a.json")), read, cands, seed=0)
    seen = []
    part = run.vote_pass(ModelClient(part_fake, Ledger(tmp_path / "b.json")), read, cands, seed=0, only={2}, on_record=seen.append)
    assert [r["id"] for r in part] == ["c002"] and seen == part
    assert part_fake.calls == full_fake.calls[6:], "rank 2's requests are the same whichever ranks run"
    assert full[0]["prompt"] == wonder.PLAIN_VERSION and "examples" not in full[0]["crops"][0]
    view = crops.build_crop(*read(300, 400, 384), 192, 192, 256)
    assert wonder.vote_request(view).question == wonder.VOTE_QUESTION.format(reference_clause="")
    assert request_hash(wonder.vote_request(view)) == request_hash(wonder.vote_request(view))

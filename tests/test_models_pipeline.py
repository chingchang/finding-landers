"""SAM measurements, blind crops, votes, the review loop and the passes end to end, on the fake backend."""

import json

import numpy as np
import pytest

from landers.detect import DetectorConfig
from landers.models import crops, leak, run, sam, spark, wonder
from landers.models.backend import Box, FakeBackend, ModelClient, SamObject, SamResult
from landers.models.ledger import Ledger


def client(tmp_path, **kw):
    return ModelClient(FakeBackend(**kw), Ledger(tmp_path / "ledger.json"))


def ground(seed=0, size=600, objects=()):
    """Noisy ground with bright discs of given (row, col, radius_px) drawn in."""
    rng = np.random.default_rng(seed)
    data = np.clip(500 + 30 * rng.standard_normal((size, size)), 1, 1021).astype(np.float32)
    yy, xx = np.mgrid[0:size, 0:size]
    for r, c, rad in objects:
        data[(yy - r) ** 2 + (xx - c) ** 2 <= rad**2] = 900
    valid = np.ones(data.shape, bool)
    valid[:, :20] = False  # a no-data edge
    return data, valid


# ----------------------------------------------------------------------------------------------- sam


def test_object_prompt_matches_the_documented_grammar():
    s = sam.build_object_prompt(512, 512, [Box(100, 120, 140, 160)])
    assert s == "<0f>1<|box;x1=100;y1=120;x2=140;y2=160;w=512;h=512|>"
    two = sam.build_object_prompt(64, 64, [Box(1, 1, 5, 5), Box(10, 10, 20, 20)])
    assert two.count("<|box;") == 2 and ",2<|box;x1=10" in two
    with pytest.raises(ValueError, match="at most 16"):
        sam.build_object_prompt(64, 64, [Box(1, 1, 2, 2)] * 17)
    with pytest.raises(ValueError, match="outside"):
        sam.build_object_prompt(64, 64, [Box(1, 1, 64, 2)])
    with pytest.raises(ValueError, match="no boxes"):
        sam.build_object_prompt(64, 64, [])


def test_box_for_blob_pads_and_clips():
    b = sam.box_for_blob(128, 128, area_px=50, size=256)  # radius about 4, padded to 8
    assert b == Box(120, 120, 136, 136)
    tiny = sam.box_for_blob(128, 128, area_px=1, size=256)
    assert tiny.x2 - tiny.x1 == 6, "a minimum half size of 3 px"
    big = sam.box_for_blob(128, 128, area_px=200000, size=256)
    assert big == Box(0, 0, 255, 255)


def test_mask_measurements_of_a_disc_and_the_tests():
    size, rad = 128, 6
    box = Box(50, 50, 78, 78)
    mask = np.zeros((size, size), bool)
    yy, xx = np.mgrid[0:size, 0:size]
    mask[(yy - 64) ** 2 + (xx - 64) ** 2 <= rad**2] = True
    img = np.where(mask, 900.0, 500.0) + np.random.default_rng(0).normal(0, 5, (size, size))
    m = sam.mask_measurements(mask, box, 0.25, img)
    assert m["equiv_diameter_m"] == pytest.approx(2 * rad * 0.25, rel=0.12)
    assert m["elongation"] < 0.1 and m["circularity"] > 0.7 and not m["touches_box_edge"]
    assert m["edge_contrast"] > 10
    cfg, lim = DetectorConfig(), sam.SamLimits()
    t = sam.size_shape_tests(m, "bright", cfg, lim, confidence=0.9)
    assert (
        t["sam_size"]["outcome"] == "pass"
        and t["sam_shape"]["outcome"] == "pass"
        and t["sam_edge"]["outcome"] == "pass"
    )
    assert sam.size_shape_tests(m, "sheet", cfg, lim, 0.9)["sam_size"]["outcome"] == "fail", "3 m is no parachute"
    assert sam.size_shape_tests(m, "sheet", cfg, lim, 0.9)["sam_shape"]["outcome"] == "not run"
    assert sam.size_shape_tests(m, "bright", cfg, lim, 0.1)["sam_size"]["outcome"] == "unsure", "weak confidence"
    assert sam.size_shape_tests({"area_px": 0}, "bright", cfg, lim, 0.9)["sam_size"]["outcome"] == "not run"
    edge = dict(m, touches_box_edge=True)
    assert sam.size_shape_tests(edge, "dark_compact", cfg, lim, 0.9)["sam_shape"]["outcome"] == "unsure"


def test_measure_result_matches_objects_to_boxes_and_clips_to_the_box():
    boxes = [Box(10, 10, 30, 30), Box(60, 60, 90, 90)]
    full = np.ones((100, 100), bool)
    res = SamResult([SamObject(2, boxes[1], 0.8, full)])  # object 1 missing, object 2 covers everything
    out = sam.measure_result(res, boxes, 0.5)
    assert out[0]["found"] is False and out[0]["measurements"]["area_px"] == 0
    assert (
        out[1]["found"] and out[1]["measurements"]["area_px"] == 31 * 31 and out[1]["measurements"]["touches_box_edge"]
    )


# ----------------------------------------------------------------------------------------------- crops


def test_blind_crop_is_rgb_png_without_metadata_and_zoom_repeats_pixels():
    data, valid = ground(objects=[(300, 300, 5)])
    c = crops.build_crop(data, valid, 300, 300, size=64, zoom=4)
    for p in c.images():
        leak.check_png(p)
    import io

    from PIL import Image

    im = Image.open(io.BytesIO(c.native_png))
    assert im.mode == "RGB" and im.size == (64, 64) and not im.text
    z = np.asarray(Image.open(io.BytesIO(c.zoom_png)))[..., 0]
    assert z.shape == (64, 64) and np.array_equal(z[0:4, 0:4], np.full((4, 4), z[0, 0]))
    assert c.native_u8[32, 32] == 255, "the object is the brightest thing in a global stretch"
    assert c.reference_png is None and c.valid_fraction == 1.0


def test_crop_at_the_edge_is_padded_invalid_and_reference_is_stretched_the_same_way():
    data, valid = ground()
    c = crops.build_crop(data, valid, 5, 5, size=64)
    assert c.valid_fraction < 0.5 and c.native_u8[0, 0] == 0
    ref = crops.build_crop(data, valid, 300, 300, size=64, reference=(data, valid, 400, 400))
    assert ref.reference_png is not None and len(ref.images()) == 3


def test_augmentations_are_seeded_and_first_is_plain():
    a = crops.draw_augmentations(np.random.default_rng(7), 3, 256)
    b = crops.draw_augmentations(np.random.default_rng(7), 3, 256)
    assert [x.to_json() for x in a] == [x.to_json() for x in b]
    assert a[0] == crops.Augmentation()
    assert any(x.flip_h or x.flip_v or x.drow or x.dcol for x in a[1:])
    data, valid = ground(objects=[(300, 300, 5)])
    flipped = crops.build_crop(data, valid, 300, 300, 64, aug=crops.Augmentation(flip_h=True, drow=4))
    plain = crops.build_crop(data, valid, 300, 300, 64)
    assert flipped.native_png != plain.native_png


# ----------------------------------------------------------------------------------------------- wonder


def test_votes_lower_one_step_and_never_raise():
    nat = {"verdict": "natural", "confidence": 0.9}
    hw = {"verdict": "hardware", "confidence": 0.95}
    un = {"verdict": "unsure", "confidence": 0.5}
    assert wonder.apply_votes("candidate", [nat, nat, un])[0] == "needs second look"
    assert wonder.apply_votes("needs second look", [nat, nat, nat])[0] == "likely natural"
    assert wonder.apply_votes("likely natural", [nat, nat, nat])[0] == "likely natural"
    assert wonder.apply_votes("candidate", [nat, hw, nat])[0] == "candidate", "a hardware vote blocks the lowering"
    assert wonder.apply_votes("likely natural", [hw, hw, hw])[0] == "likely natural", "votes never raise"
    assert wonder.apply_votes("candidate", [nat, un, un])[0] == "candidate"
    weak = {"verdict": "natural", "confidence": 0.6}
    assert wonder.apply_votes("candidate", [weak, weak, weak])[0] == "candidate"
    assert wonder.apply_votes("not assessed", [nat, nat, nat])[0] == "not assessed"


def test_parse_vote_marks_off_schema():
    v = wonder.parse_vote({"verdict": "yes", "confidence": 2, "reason": "x"})
    assert v["verdict"] == "unsure" and v["off_schema"] and v["confidence"] == 0.0
    assert not wonder.parse_vote({"verdict": "natural", "confidence": 0.8, "reason": "r"})["off_schema"]


def test_cast_votes_and_probe_on_the_fake(tmp_path):
    data, valid = ground(objects=[(300, 300, 5)])
    views = [
        crops.build_crop(data, valid, 300, 300, 64, aug=a)
        for a in crops.draw_augmentations(np.random.default_rng(0), 3, 64)
    ]
    cl = client(tmp_path)
    votes = wonder.cast_votes(cl, views)
    assert len(votes) == 3 and all(v["verdict"] == "unsure" for v in votes)
    assert cl.ledger.entries["wonder"]["units"] == 3 and cl.ledger.entries["wonder"]["cost_usd"] > 0
    pr = wonder.probe(cl, views)
    s = wonder.probe_summary(pr)
    assert s == {"n": 3, "recognised": 0, "max_confidence": 0.0, "claims": []}
    cl2 = client(tmp_path, wonder_answers={"probe": {"recognised": True, "place": "a famous site", "confidence": 0.9}})
    s2 = wonder.probe_summary(wonder.probe(cl2, views))
    assert s2["recognised"] == 3 and s2["claims"] == ["a famous site"]


# ----------------------------------------------------------------------------------------------- spark


def cands():
    return [
        {
            "row": 300.0,
            "col": 300.0,
            "score": 2.5,
            "branch": "bright",
            "grade": "candidate",
            "area_px": 80,
            "extra": {"circularity": 0.81, "persist": {"seen": True}},
        },
        {
            "row": 100.0,
            "col": 450.0,
            "score": 1.25,
            "branch": "dark_compact",
            "grade": "needs second look",
            "area_px": 40,
            "extra": {"elongation": 0.3},
        },
    ]


def test_evidence_record_is_blind():
    c = dict(cands()[0], lat="redacted", lon_e="redacted", strip="ESP" + "_000000_0000")
    rec = spark.evidence_record(c, "c000")
    text = json.dumps(rec)
    for forbidden in ("row", "col", "lat", "lon", "strip", "ESP"):
        assert f'"{forbidden}"' not in text
    assert rec["persistence"]["seen"] is True and rec["shape"] == {"circularity": 0.81}
    assert spark.evidence_record(cands()[1], "c001")["persistence"] == {"seen": None, "note": "one date only"}


def test_record_verdict_validation():
    store = run.build_store(cands(), {"top_n": 20})
    assert "rejected" in store.record_verdict("c000", "raise", ["grade"], "x")
    assert "rejected" in store.record_verdict("c000", "keep", [], "x")
    r = store.record_verdict("c000", "keep", ["grade", "nope.field"], "x")
    assert "not in the record" in r["rejected"]
    r = store.record_verdict("c000", "lower", ["score"], "score 2.4 is low")
    assert "numbers not copied" in r["rejected"] and "2.4" in r["rejected"]
    r = store.record_verdict("c000", "lower", ["score"], "a score of 2.5 but confirmed natural")
    assert "confirmed" in r["rejected"]
    ok = store.record_verdict(
        "c000", "lower", ["score", "shape.circularity"], "score 2.5 with circularity 0.81; lowered"
    )
    assert ok == {"recorded": True, "id": "c000", "action": "lower"}
    assert "rejected" in store.record_verdict("zzz", "keep", ["grade"], "x")
    grades = spark.apply_verdicts(store.records, store.verdicts)
    assert grades["c000"] == {"before": "candidate", "after": "needs second look", "reviewed": True}
    assert grades["c001"] == {"before": "needs second look", "after": "needs second look", "reviewed": False}


def test_numbers_rule_accepts_rounded_values():
    rec = {"a": 0.8125, "b": 3}
    assert spark.numbers_not_in_record("a is 0.81 and b is 3", rec) == []
    assert spark.numbers_not_in_record("a is 0.82", rec) == ["0.82"]
    assert spark.numbers_not_in_record("id c001 is fine", rec) == [], "ids are not numbers"


def test_review_loop_on_the_fake_records_a_verdict_for_every_candidate(tmp_path):
    cl = client(tmp_path)
    store = run.build_store(cands(), {"top_n": 20}, "strip_a")
    res = spark.review(cl, store, "strip_a")
    assert res.stopped == "final answer" and res.turns == 4
    assert set(res.verdicts) == {"c000", "c001"} and all(v["action"] == "keep" for v in res.verdicts.values())
    assert res.final["unrecorded"] == []
    tools = [t["tool"] for t in res.tool_log]
    assert tools[0] == "list_candidates" and "read_thresholds" in tools and tools.count("record_verdict") == 2
    assert cl.ledger.entries["spark"]["units"] == 4
    assert all(g["after"] == g["before"] for g in res.grades.values())


def test_request_check_is_bounded_and_refusals_are_reported(tmp_path):
    def checks(cid, kind):
        from landers.models.ledger import CapError

        if kind == "more_votes":
            raise CapError("wonder: cap")
        return {"available": False, "note": "no second date in this run"}

    store = run.build_store(cands(), {}, checks=checks)
    r = store.request_check("c000", "more_votes")
    assert r == {"refused": "wonder: cap"}
    r = store.request_check("c000", "second_date_check")
    assert r["result"]["available"] is False and "checks" in store.records["c000"]
    assert "error" in store.request_check("c000", "teleport")
    assert "refused" in run.build_store(cands(), {}).request_check("c000", "zoom_pass")


def test_review_turn_cap(tmp_path):
    class Chatty(FakeBackend):
        def spark(self, req):
            from landers.models.backend import SparkTurn

            return SparkTurn(
                None, [{"id": "x", "type": "function", "function": {"name": "read_thresholds", "arguments": "{}"}}]
            )

    cl = ModelClient(Chatty(), Ledger(tmp_path / "l.json"))
    res = spark.review(cl, run.build_store(cands(), {}), "strip_a", max_turns=3)
    assert res.stopped == "turn cap" and res.turns == 3 and res.verdicts == {}


# ----------------------------------------------------------------------------------------------- passes


def test_sam_pass_and_vote_pass_end_to_end(tmp_path):
    data, valid = ground(objects=[(300, 300, 5), (100, 450, 3)])
    read = run.array_reader(data, valid)
    cl = client(tmp_path)
    cs = cands()
    sam_recs = run.sam_pass(cl, read, cs, 0.25)
    assert [r["id"] for r in sam_recs] == ["c000", "c001"]
    assert sam_recs[0]["found"] and sam_recs[0]["tests"]["sam_size"]["outcome"] in ("pass", "fail", "unsure")
    assert "row" not in sam_recs[0] and "col" not in sam_recs[0]
    votes = run.vote_pass(cl, read, cs, reference=read, reference_at=(500, 500), n_votes=3, seed=3)
    assert len(votes[0]["votes"]) == 3 and votes[0]["crops"][0]["has_reference"]
    assert votes[0]["grade_after"] == votes[0]["grade_before"]
    probe = run.vote_pass(cl, read, cs[:1], n_votes=2, probe=True)
    assert probe[0]["summary"]["n"] == 2
    store = run.build_store(cs, {"top_n": 20}, "strip_a", sam_recs, votes, run.check_runner(cl, read, cs, 0.25))
    assert "sam" in store.records["c000"] and len(store.records["c000"]["votes"]) == 3
    assert store.records["c000"]["tests"]["sam_size"]["outcome"] in ("pass", "fail", "unsure")
    zoom = store.request_check("c000", "zoom_pass")
    assert zoom["result"]["found"] in (True, False) and "tests" in zoom["result"]
    more = store.request_check("c001", "more_votes")
    assert len(more["result"]["votes"]) == 3
    assert store.request_check("c000", "second_date_check")["result"]["seen"] is True
    res = spark.review(cl, store, "strip_a")
    assert res.stopped == "final answer"
    led = cl.ledger.entries
    assert led["sam"]["units"] == 3 and led["wonder"]["units"] == 6 + 2 + 3 and led["spark"]["units"] == 4
    run.write_json(tmp_path / "x" / "review.json", res.to_json())
    assert (tmp_path / "x" / "review.json").exists()


def test_sam_pass_records_not_run_past_the_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("LANDERS_CAP_SAM", "1")
    data, valid = ground()
    cl = ModelClient(FakeBackend(), Ledger.load(tmp_path / "l.json"))
    recs = run.sam_pass(cl, run.array_reader(data, valid), cands(), 0.25)
    assert recs[0]["found"] is not None and "not_run" in recs[1]
    assert recs[1]["tests"]["sam_size"]["outcome"] == "not run"

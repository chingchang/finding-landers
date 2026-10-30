"""Plan item 14: the cumulative dollar cap, the pause, the reservation, saturated pixels drawn bright, the single-vote rule
and the review's one verdict turn. All on the fake backend, no network."""

import json

import numpy as np
import pytest

from landers.models import crops, run, spark, wonder
from landers.models.backend import FakeBackend, ModelClient, WonderRequest
from landers.models.ledger import REGISTER, CapError, Ledger, PauseError, register_run, spent_usd, total_cap_from_env


def vote(verdict, confidence):
    return {"verdict": verdict, "confidence": confidence, "reason": "x", "off_schema": False}


# ------------------------------------------------------------------ the ledger


def test_total_cap_refuses_before_the_call_counting_other_runs():
    led = Ledger(caps={"sam": 10, "wonder": 10, "spark": 10}, prior_usd=119.96)
    with pytest.raises(CapError, match="would pass"):
        led.charge("wonder")
    assert led.entries["wonder"]["units"] == 0
    assert led.entries["wonder"]["refused"] == 1


def test_total_cap_counts_this_run_too():
    led = Ledger(caps={"sam": 10, "wonder": 10, "spark": 10}, prior_usd=119.0)
    led.charge("wonder")
    led.record("wonder", True, 0, 48_000)  # 0.96 USD, so the next call's 0.05 passes 120
    with pytest.raises(CapError):
        led.charge("wonder")


def test_total_cap_env_can_lower_and_never_raise(monkeypatch):
    monkeypatch.setenv("LANDERS_CAP_TOTAL_USD", "50")
    assert total_cap_from_env() == 50.0
    monkeypatch.setenv("LANDERS_CAP_TOTAL_USD", "500")
    assert total_cap_from_env() == 120.0


def test_pause_stops_at_the_named_call_over_all_models():
    led = Ledger(caps={"sam": 10, "wonder": 10, "spark": 10}, pause_at_units=2)
    led.charge("wonder")
    led.charge("spark")
    with pytest.raises(PauseError):
        led.charge("wonder")
    assert led.units_total() == 2


def test_reservation_holds_calls_from_everything_outside_its_block():
    led = Ledger(caps={"sam": 0, "wonder": 3, "spark": 0})
    led.reserve("wonder", 2)
    led.charge("wonder")
    with pytest.raises(CapError, match="reserved"):
        led.charge("wonder")
    with led.spending_reserved():
        led.charge("wonder")
        led.charge("wonder")
    assert led.entries["wonder"]["units"] == 3


def test_reserving_past_the_cap_is_refused_before_anything_is_sent():
    with pytest.raises(CapError, match="cannot reserve"):
        Ledger(caps={"sam": 0, "wonder": 3, "spark": 0}).reserve("wonder", 4)


def register_at(tmp_path, rows):
    reg = tmp_path / "docs" / "reports" / "ledgers.json"
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"ledgers": rows}))
    return reg


def write_ledger(path, usd):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"total_cost_usd": usd}))


def test_spent_sums_the_register_and_leaves_out_the_asking_run(tmp_path):
    reg = register_at(tmp_path, [{"item": "a", "path": "a.json"}, {"item": "b", "path": "b.json"}])
    write_ledger(tmp_path / "a.json", 1.5)
    write_ledger(tmp_path / "b.json", 2.25)
    assert spent_usd(reg) == 3.75
    assert spent_usd(reg, exclude=tmp_path / "b.json") == 1.5


def test_a_listed_ledger_that_is_gone_stops_everything_unless_live(tmp_path):
    reg = register_at(tmp_path, [{"item": "a", "path": "gone.json"}])
    with pytest.raises(FileNotFoundError):
        spent_usd(reg)
    reg = register_at(tmp_path / "live", [{"item": "a", "path": "gone.json", "live": True}])
    assert spent_usd(reg) == 0.0


def test_register_run_adds_once(tmp_path):
    reg = register_at(tmp_path, [])
    p = tmp_path / "out" / "x" / "ledger.json"
    p.parent.mkdir(parents=True)
    register_run(p, "14", reg)
    register_run(p, "14", reg)
    assert json.loads(reg.read_text())["ledgers"] == [{"item": "14", "path": "out/x/ledger.json", "live": True}]


def test_every_published_ledger_is_on_the_register():
    root = REGISTER.parent
    listed = {(root.parent.parent / r["path"]).resolve() for r in json.loads(REGISTER.read_text())["ledgers"]}
    published = {p.resolve() for p in root.rglob("ledger.json")}
    assert published <= listed, f"not on the register: {published - listed}"


def test_open_client_starts_from_what_the_other_runs_spent(tmp_path):
    client = run.open_client("fake", tmp_path)
    assert client.ledger.prior_usd == spent_usd()


# ------------------------------------------------------------------ saturated pixels


def saturated_field():
    data = np.full((64, 64), 400.0, np.float32)
    data += np.arange(64, dtype=np.float32)
    data[30:34, 30:34] = 1023
    data[0, 0] = 0
    valid = (data != 0) & (data < 1022)
    return data, valid


def test_saturated_pixels_draw_bright_only_when_asked():
    data, valid = saturated_field()
    old = crops.stretch(data, valid, 1, 99)
    new = crops.stretch(data, valid, 1, 99, saturated_bright=True)
    assert old[31, 31] == 0
    assert new[31, 31] == 255
    assert new[0, 0] == 0  # no data stays black
    np.testing.assert_array_equal(old[valid], new[valid])


def test_outside_the_array_stays_black():
    data, valid = saturated_field()
    arr, ok = crops.square_crop(data, valid, 2, 2, 32)
    u8 = crops.stretch(arr, ok, 1, 99, saturated_bright=True)
    assert u8[0, 0] == 0


def test_default_requests_hash_as_before():
    data, valid = saturated_field()
    plain = crops.build_crop(data, valid, 32, 32, 32, 4)
    assert crops.stretch(*crops.square_crop(data, valid, 32, 32, 32), 0.5, 99.5).tobytes() == plain.native_u8.tobytes()
    bright = crops.build_crop(data, valid, 32, 32, 32, 4, saturated_bright=True)
    assert plain.native_png != bright.native_png


# ------------------------------------------------------------------ the single-vote rule


GRADE = "needs second look"


@pytest.mark.parametrize(
    "verdict,confidence,borderline,after",
    [
        ("natural", 0.85, False, "likely natural"),
        ("natural", 0.90, False, "likely natural"),
        ("natural", 0.84, True, GRADE),
        ("natural", 0.70, True, GRADE),
        ("natural", 0.69, False, GRADE),
        ("hardware", 0.99, False, GRADE),
        ("unsure", 0.99, False, GRADE),
    ],
)
def test_first_vote(verdict, confidence, borderline, after):
    rule = wonder.SingleVoteRule()
    v = vote(verdict, confidence)
    assert rule.borderline(v) is borderline
    assert rule.apply(GRADE, [v])[0] == after


def test_three_votes_fall_to_the_rule_of_record():
    rule = wonder.SingleVoteRule()
    first = vote("natural", 0.72)
    assert rule.apply(GRADE, [first, vote("natural", 0.7), vote("unsure", 0.5)])[0] == "likely natural"
    assert rule.apply(GRADE, [first, vote("natural", 0.65), vote("natural", 0.65)])[0] == GRADE
    assert rule.apply(GRADE, [first, vote("natural", 0.8), vote("hardware", 0.7)])[0] == GRADE


@pytest.mark.parametrize("grade", ["candidate", "needs second look", "likely natural"])
@pytest.mark.parametrize("verdict", ["natural", "hardware", "unsure"])
@pytest.mark.parametrize("confidence", [0.0, 0.7, 0.85, 1.0])
def test_a_vote_never_raises_a_grade(grade, verdict, confidence):
    after, _ = wonder.SingleVoteRule().apply(grade, [vote(verdict, confidence)])
    assert wonder.GRADES.index(after) >= wonder.GRADES.index(grade)


def test_not_assessed_stays_as_it_is():
    assert wonder.SingleVoteRule().apply("not assessed", [vote("natural", 0.9)])[0] == "not assessed"


class ScriptedVotes(FakeBackend):
    """Answers from a list, one per call, and remembers each request."""

    def __init__(self, answers):
        super().__init__()
        self.answers = list(answers)
        self.requests: list[WonderRequest] = []

    def wonder(self, req):
        self.requests.append(req)
        result = super().wonder(req)
        result.data = self.answers.pop(0)
        return result


def field_reader():
    rng = np.random.default_rng(0)
    data = rng.normal(400, 20, (800, 800)).astype(np.float32)
    data[398:402, 398:402] = 1023
    return run.array_reader(data, data < 1022)


CAND = {"row": 400, "col": 400, "branch": "bright", "grade": GRADE, "score": 1.0, "area_px": 16}


def pass_with(answers):
    backend = ScriptedVotes(answers)
    client = ModelClient(backend, Ledger(caps={"sam": 0, "wonder": 10, "spark": 0}))
    return run.single_vote(client, field_reader(), CAND, 3), backend, client


def answer(verdict, confidence):
    return {"verdict": verdict, "confidence": confidence, "reason": "x"}


def test_one_vote_when_the_first_decides():
    rec, backend, client = pass_with([answer("natural", 0.9)])
    assert len(rec["votes"]) == 1
    assert client.ledger.entries["wonder"]["units"] == 1
    assert rec["grade_after"] == "likely natural"
    assert rec["rule"] == "vote-single-v1"
    assert rec["crops"][0]["augmentation"] == crops.Augmentation().to_json()


def test_three_votes_in_the_band():
    rec, backend, client = pass_with([answer("natural", 0.75), answer("natural", 0.8), answer("unsure", 0.4)])
    assert len(rec["votes"]) == 3
    assert client.ledger.entries["wonder"]["units"] == 3
    assert rec["grade_after"] == "likely natural"
    assert len({r.images[0] for r in backend.requests}) == 3


def test_a_ranks_requests_do_not_depend_on_what_ran_before():
    a, *_ = pass_with([answer("natural", 0.75), answer("hardware", 0.9), answer("unsure", 0.4)])
    b, *_ = pass_with([answer("natural", 0.75), answer("unsure", 0.1), answer("unsure", 0.4)])
    assert a["crops"] == b["crops"]


def test_the_saturated_core_reaches_the_model_white():
    rec, backend, _ = pass_with([answer("hardware", 0.9)])
    import io

    from PIL import Image

    png = backend.requests[0].images[0]
    arr = np.asarray(Image.open(io.BytesIO(png)))
    assert arr[128, 128, 0] == 255


# ------------------------------------------------------------------ the review


def small_store():
    cands = [{**CAND, "row": 400 + i} for i in range(3)]
    return run.build_store(cands, {"version": "v"}, "strip_a")


def test_one_turn_review_records_every_verdict():
    store = small_store()
    client = ModelClient(FakeBackend(), Ledger(caps={"sam": 0, "wonder": 0, "spark": 10}))
    r = spark.review(client, store, "strip_a", 6, one_turn=True)
    assert set(r.verdicts) == {"c000", "c001", "c002"}
    assert r.stopped == "final answer"


class StallingSpark(FakeBackend):
    """Fetches forever, and keeps each request's messages."""

    def __init__(self):
        super().__init__()
        self.seen = []

    def spark(self, req):
        self.seen.append(json.loads(json.dumps(req.messages)))
        call = {"id": f"t{len(self.seen)}", "type": "function", "function": {"name": "read_thresholds", "arguments": "{}"}}
        return spark.SparkTurn(None, [call], None)


def test_one_turn_review_names_what_is_missing_with_two_turns_left():
    backend = StallingSpark()
    client = ModelClient(backend, Ledger(caps={"sam": 0, "wonder": 0, "spark": 10}))
    spark.review(client, small_store(), "strip_a", 4, one_turn=True)
    assert spark.ONE_TURN_CLAUSE in backend.seen[0][0]["content"]
    users = [m["content"] for m in backend.seen[2] if m["role"] == "user"]
    assert not any("Two turns remain" in u for u in [m["content"] for m in backend.seen[1] if m["role"] == "user"])
    assert any("c000, c001, c002" in u for u in users)


def test_the_plain_review_prompt_is_unchanged():
    backend = StallingSpark()
    client = ModelClient(backend, Ledger(caps={"sam": 0, "wonder": 0, "spark": 10}))
    spark.review(client, small_store(), "strip_a", 2)
    assert backend.seen[0][0]["content"] == spark.SYSTEM_PROMPT

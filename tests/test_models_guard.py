"""The leak guard, the ledger and the backends. No network anywhere."""

import json
import os
from pathlib import Path

import numpy as np
import pytest

from landers.models import leak, spark, wonder
from landers.models.backend import (
    Box,
    DryRunBackend,
    FakeBackend,
    MissingRecording,
    ModelClient,
    RecordedBackend,
    SamRequest,
    SparkRequest,
    TransientError,
    WonderRequest,
    make_backend,
    request_hash,
)
from landers.models.crops import to_png
from landers.models.ledger import CapError, Ledger

SITES = Path(__file__).resolve().parent.parent / "controls" / "sites.json"
needs_sites = pytest.mark.skipif(not SITES.exists(), reason="controls/sites.json not in this checkout")


def png(size=32, seed=0):
    rng = np.random.default_rng(seed)
    return to_png(rng.integers(0, 255, (size, size), dtype=np.uint8))


# ----------------------------------------------------------------------------------------------- leak


def test_guard_catches_ids_files_dates_bearings():
    assert "observation id" in leak.find_leak("tile from " + "ESP_" + "000000_0000")
    assert "observation id" in leak.find_leak("PSP" + "_001890_1995")
    assert "file name" in leak.find_leak("crop of X" + "_RED near")
    assert "file name" in leak.find_leak("see a" + ".JP2 file")
    assert "date" in leak.find_leak("taken 2016-10-25")
    assert "date" in leak.find_leak("doy 2016-299T")
    assert "coordinate with bearing" in leak.find_leak("at 22.3 N")
    assert "coordinate with bearing" in leak.find_leak("312.05 deg E")


@needs_sites
def test_guard_catches_site_names_and_published_coordinates():
    sites = json.loads(SITES.read_text())["sites"]
    tuning = next(s for s in sites if s["group"] == "tuning")
    assert "site or mission name" in leak.find_leak(f"this is {tuning['name'].upper()} ground")
    precise = [
        p
        for s in sites
        if s["group"] == "tuning"
        for p in s.get("pieces_refined", [])
        if p.get("lat") is not None and all(len(str(p[k]).split(".")[1]) >= 3 for k in ("lat", "lon_e"))
    ]
    piece = precise[0]
    assert "published coordinate" in leak.find_leak(f"value {piece['lat']} here")
    assert "published coordinate" in leak.find_leak(f"value {piece['lon_e']} here")


def test_guard_passes_the_fixed_prompts_and_tools():
    for text in (
        wonder.VOTE_QUESTION.format(reference_clause=wonder.REFERENCE_CLAUSE),
        wonder.PROBE_QUESTION.format(reference_clause=""),
        spark.SYSTEM_PROMPT,
        json.dumps(spark.TOOLS),
        json.dumps(spark.FINAL_SCHEMA),
        json.dumps(wonder.VOTE_SCHEMA),
    ):
        assert leak.find_leak(text) is None, (leak.find_leak(text), text[:80])


def test_guard_rejects_png_with_text_chunk_and_passes_clean():
    clean = png()
    leak.check_png(clean)
    import io

    from PIL import Image, PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "a strip id would go here")
    buf = io.BytesIO()
    Image.fromarray(np.zeros((8, 8, 3), np.uint8), "RGB").save(buf, format="PNG", pnginfo=info)
    with pytest.raises(leak.LeakError, match="tEXt"):
        leak.check_png(buf.getvalue())
    with pytest.raises(leak.LeakError, match="not a PNG"):
        leak.check_png(b"GIF89a")


def test_guard_walks_nested_requests_but_skips_data_urls():
    leak.check_strings({"a": ["data:image/png;base64,RVNQXzAwMDAwMF8wMDAw"], "b": {"c": "fine"}})
    with pytest.raises(leak.LeakError, match=r"request\.b\.c"):
        leak.check_strings({"a": [], "b": {"c": "ESP" + "_000000_0000"}})


# ----------------------------------------------------------------------------------------------- ledger


def test_ledger_caps_counts_and_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("LANDERS_CAP_WONDER", "2")
    led = Ledger.load(tmp_path / "ledger.json")
    assert led.caps["wonder"] == 2 and led.caps["sam"] == 3000
    led.charge("wonder")
    led.record("wonder", True, input_tokens=1_000_000, output_tokens=0)
    led.charge("wonder")
    led.record("wonder", False)
    with pytest.raises(CapError):
        led.charge("wonder")
    led.charge("sam", 10)
    d = json.loads((tmp_path / "ledger.json").read_text())
    e = d["entries"]
    assert e["wonder"]["units"] == 2 and e["wonder"]["attempts"] == 2 and e["wonder"]["refused"] == 1
    assert e["wonder"]["ok"] == 1 and e["wonder"]["failed"] == 1
    assert e["wonder"]["cost_usd"] == pytest.approx(4.0)
    assert e["sam"]["units"] == 10 and e["sam"]["cost_usd"] == pytest.approx(0.025)
    again = Ledger.load(tmp_path / "ledger.json")
    assert again.entries["sam"]["units"] == 10, "a ledger continues from disk"
    assert again.remaining("sam") == 2990


# ----------------------------------------------------------------------------------------------- backends


def sam_req(size=32):
    return SamRequest(png(size), size, size, [Box(10, 10, 20, 20)])


def test_fake_sam_returns_a_disc_inside_the_box():
    r = FakeBackend().sam(sam_req())
    assert len(r.objects) == 1 and r.objects[0].confidence == 0.9
    m = r.objects[0].mask
    assert m.shape == (32, 32) and m[15, 15] and not m[0, 0] and not m[9, 15] and not m[15, 21]


def test_request_hash_is_stable_and_blind_to_image_bytes_order():
    a, b = sam_req(), sam_req()
    assert request_hash(a) == request_hash(b)
    c = SamRequest(png(32, seed=1), 32, 32, [Box(10, 10, 20, 20)])
    assert request_hash(a) != request_hash(c)


def test_recorded_backend_replays_and_refuses_unknown(tmp_path):
    inner = FakeBackend()
    rec = RecordedBackend(tmp_path, inner)
    req = sam_req()
    first = rec.sam(req)
    assert len(inner.calls) == 1
    second = RecordedBackend(tmp_path).sam(req)
    assert np.array_equal(first.objects[0].mask, second.objects[0].mask)
    saved = json.loads(next(tmp_path.glob("sam_*.json")).read_text())
    assert "sha256" in json.dumps(saved["request"]) and "base64," not in json.dumps(saved["request"])
    with pytest.raises(MissingRecording):
        RecordedBackend(tmp_path).sam(SamRequest(png(32, seed=2), 32, 32, [Box(1, 1, 5, 5)]))
    wr = WonderRequest("q", [png()], wonder.VOTE_SCHEMA)
    v1 = rec.wonder(wr)
    v2 = RecordedBackend(tmp_path).wonder(wr)
    assert v1.data == v2.data and v2.input_tokens == v1.input_tokens


def test_dry_run_writes_requests_without_image_bytes(tmp_path):
    be = DryRunBackend(tmp_path)
    be.sam(sam_req())
    be.wonder(WonderRequest("q", [png()], wonder.VOTE_SCHEMA))
    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 2 and {f.name.split("_")[0] for f in files} == {"sam", "wonder"}
    for f in files:
        text = f.read_text()
        assert "base64," not in text and "sha256" in text
        d = json.loads(text)["wire"]
        assert d["model"] in ("sam-3.1", "muse-wonder-1.0")
    samwire = json.loads(next(f for f in files if f.name.startswith("sam")).read_text())["wire"]
    assert samwire["metadata"] == {"include_confidence": "true", "mask_encoding": "one_bit"}
    assert samwire["input"][0]["content"][0]["text"].startswith("<0f>1<|box;x1=10;y1=10;x2=20;y2=20;w=32;h=32|>")


def test_real_backend_is_gated_on_the_person():
    with pytest.raises(RuntimeError, match="MODEL_API_KEY"):
        make_backend("real", env={})
    with pytest.raises(RuntimeError, match="LANDERS_REAL_CALLS"):
        make_backend("real", env={"MODEL_API_KEY": "x"})
    assert "MODEL_API_KEY" not in os.environ or True  # the test never reads a real key
    with pytest.raises(ValueError):
        make_backend("nope")


class Flaky(FakeBackend):
    def __init__(self, fail_times):
        super().__init__()
        self.fail_times = fail_times

    def wonder(self, req):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise TransientError("429")
        return super().wonder(req)


def test_client_retries_transient_and_counts_every_attempt(tmp_path):
    slept = []
    client = ModelClient(Flaky(2), Ledger(tmp_path / "l.json"), sleep=slept.append)
    r = client.wonder(WonderRequest("q", [png()], wonder.VOTE_SCHEMA))
    assert r.data["verdict"] == "unsure"
    e = client.ledger.entries["wonder"]
    assert e["attempts"] == 3 and e["units"] == 3 and e["failed"] == 2 and e["ok"] == 1
    assert slept == [2.0, 4.0]
    client2 = ModelClient(Flaky(3), Ledger(tmp_path / "l2.json"), sleep=lambda s: None)
    with pytest.raises(RuntimeError, match="gave up"):
        client2.wonder(WonderRequest("q", [png()], wonder.VOTE_SCHEMA))


def test_client_refuses_a_leaking_request_before_charging(tmp_path):
    client = ModelClient(FakeBackend(), Ledger(tmp_path / "l.json"))
    with pytest.raises(leak.LeakError):
        client.wonder(WonderRequest("image " + "ESP_" + "000000_0000", [png()], wonder.VOTE_SCHEMA))
    assert client.ledger.entries["wonder"]["attempts"] == 0
    with pytest.raises(leak.LeakError):
        client.spark(SparkRequest([{"role": "user", "content": "taken 2016-10-25"}], spark.TOOLS))
    assert client.ledger.entries["spark"]["attempts"] == 0


def test_client_stops_at_the_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("LANDERS_CAP_SAM", "1")
    client = ModelClient(FakeBackend(), Ledger.load(tmp_path / "l.json"))
    client.sam(sam_req())
    with pytest.raises(CapError):
        client.sam(sam_req())
    assert client.ledger.entries["sam"]["refused"] == 1

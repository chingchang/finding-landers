"""Item 12c(d): the download of the sealed group's strips, against a local server. No network, no data."""

import http.server
import importlib.util
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("fetch_blind", ROOT / "scripts" / "fetch_blind.py")
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)

BODY = bytes(range(256)) * 40


class Handler(http.server.BaseHTTPRequestHandler):
    limit = None  # bytes to send before dropping the connection, once
    honour_range = True
    ranges = []

    def do_GET(self):
        rng = self.headers.get("Range")
        Handler.ranges.append(rng)
        start = int(rng[6:-1]) if rng and Handler.honour_range else 0
        body = BODY[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if Handler.limit is not None:
            body, Handler.limit = body[: Handler.limit], None
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    Handler.limit, Handler.honour_range, Handler.ranges = None, True, []
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}/f"
    s.shutdown()


def test_only_the_heldout_group_is_fetched():
    sites = {"sites": [{"name": "a", "group": "tuning", "strips": ["T"]}, {"name": "b", "group": "heldout", "strips": ["B1", "B2"]}]}
    assert fb.blind_strips(sites) == [("control_b", "B1"), ("control_b", "B2")]


def test_url_bins_the_orbit_by_the_hundred():
    sid = "_".join(["PSP", "012345", "1000"])
    assert fb.strip_url(sid) == f"{fb.BASE}/PSP/ORB_012300_012399/{sid}/{sid}_RED"


def test_fetch_whole_file(server, tmp_path):
    dest = tmp_path / "x.JP2"
    fb.fetch(server, dest, len(BODY), wait_s=0)
    assert dest.read_bytes() == BODY and not (tmp_path / "x.JP2.part").exists()


def test_fetch_resumes_after_a_lost_connection(server, tmp_path):
    Handler.limit = 1000
    dest = tmp_path / "x.JP2"
    fb.fetch(server, dest, len(BODY), wait_s=0)
    assert dest.read_bytes() == BODY
    assert Handler.ranges == [None, "bytes=1000-"]


def test_fetch_starts_over_when_the_server_ignores_the_range(server, tmp_path):
    Handler.honour_range = False
    (tmp_path / "x.JP2.part").write_bytes(b"\xff" * 1000)
    dest = tmp_path / "x.JP2"
    fb.fetch(server, dest, len(BODY), wait_s=0)
    assert dest.read_bytes() == BODY


def test_incomplete_file_never_takes_the_real_name(server, tmp_path):
    dest = tmp_path / "x.JP2"
    with pytest.raises(OSError):
        fb.fetch(server, dest, len(BODY) + 1, tries=2, wait_s=0)
    assert not dest.exists()


def test_read_ends(tmp_path):
    p = tmp_path / "a.JP2"
    p.write_bytes(fb.JP2_SIGNATURE + b"x" * 10 + fb.JP2_END)
    assert fb.read_ends(p) == (True, True)
    p.write_bytes(b"not a jp2 file at all")
    assert fb.read_ends(p) == (False, False)

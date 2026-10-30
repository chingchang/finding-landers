"""Download the strips of the sealed (heldout) group named in controls/sites.json, item 12c(d).

An agent runs this and never opens the result: the files are checked by size against the server, by the JP2
signature and end marker (bytes only, nothing decoded), and by sha256. The label is not parsed. Each file lands as
<name>.part, resumes from there after a lost connection, and takes its real name and a .done marker only when
complete, so nothing can pick up half a strip. The record holds ids, sizes and hashes, nothing from inside a file.

    uv run --env-file out/landers.env scripts/fetch_blind.py --out docs/reports/2026-10-30-blind-download/fetch.json

Credit for all images: NASA/JPL/University of Arizona.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from landers import config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://hirise.lpl.arizona.edu/PDS/RDR"
CREDIT = "NASA/JPL/University of Arizona (PDS RDR V1.1, hirise.lpl.arizona.edu/PDS/RDR/)"
JP2_SIGNATURE = bytes.fromhex("0000000C6A5020200D0A870A")
JP2_END = bytes.fromhex("FFD9")
CHUNK = 1 << 20
TRIES = 8
KEEP_FREE = 2 * 10**9  # bytes left on the disk after the download, or it does not start


def blind_strips(sites: dict) -> list[tuple[str, str]]:
    """(case directory, observation id) of every strip of the heldout group."""
    return [(f"control_{s['name']}", sid) for s in sites["sites"] if s["group"] == "heldout" for sid in s["strips"]]


def strip_url(observation_id: str) -> str:
    """URL base of a strip in the PDS tree, which bins orbits by the hundred."""
    phase, orbit, _ = observation_id.split("_")
    low = int(orbit) // 100 * 100
    return f"{BASE}/{phase}/ORB_{low:06d}_{low + 99:06d}/{observation_id}/{observation_id}_RED"


def remote_size(url: str) -> int:
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as r:
        return int(r.headers["Content-Length"])


def fetch(url: str, dest: Path, size: int, tries: int = TRIES, wait_s: float = 20.0) -> None:
    """Resumable download to dest.part, then renamed to dest. Raises if the size never comes out right."""
    part = dest.with_name(dest.name + ".part")
    for attempt in range(tries):
        have = part.stat().st_size if part.exists() else 0
        if have > size:
            part.unlink()
            have = 0
        if have < size:
            try:
                req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
                with urllib.request.urlopen(req, timeout=120) as r:
                    if have and r.status != 206:  # the server ignored the range: start over
                        have = 0
                    with open(part, "ab" if have else "wb") as f:
                        shutil.copyfileobj(r, f, CHUNK)
            except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
                print(f"{dest.name}: try {attempt + 1}: {e}", file=sys.stderr, flush=True)
                time.sleep(wait_s)
                continue
        if part.stat().st_size == size:
            part.rename(dest)
            return
    raise OSError(f"{dest.name}: not complete after {tries} tries")


def read_ends(path: Path) -> tuple[bool, bool]:
    """Whether a JP2 starts with the signature box and ends with the end-of-codestream marker. Decodes nothing."""
    with open(path, "rb") as f:
        head = f.read(len(JP2_SIGNATURE))
        f.seek(-len(JP2_END), 2)
        return head == JP2_SIGNATURE, f.read() == JP2_END


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(CHUNK):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="the record to write, updated after each file")
    a = ap.parse_args()
    out = Path(a.out)
    sites = json.loads((ROOT / "controls" / "sites.json").read_text())
    strips = blind_strips(sites)
    sizes = {(sid, ext): remote_size(f"{strip_url(sid)}.{ext}") for _, sid in strips for ext in ("LBL", "JP2")}
    todo = 0
    for (case, sid), ext in ((s, e) for s in strips for e in ("LBL", "JP2")):
        d = config.strips_dir() / case / f"{sid}_RED.{ext}"
        part = d.with_name(d.name + ".part")
        if not d.exists():
            todo += sizes[sid, ext] - (part.stat().st_size if part.exists() else 0)
    free = shutil.disk_usage(config.strips_dir()).free
    print(f"{len(strips)} strips, {todo} bytes to fetch, {free} free", flush=True)
    if free - todo < KEEP_FREE:
        print(f"refused: would leave under {KEEP_FREE} bytes free", file=sys.stderr)
        return 2
    record = {"what": "item 12c(d): the sealed group's strips, downloaded unopened", "credit": CREDIT,
              "free_bytes_before": free, "files": []}
    ok = True
    for case, sid in strips:
        for ext in ("LBL", "JP2"):
            url = f"{strip_url(sid)}.{ext}"
            dest = config.strips_dir() / case / f"{sid}_RED.{ext}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            done = dest.with_name(dest.name + ".done")
            if not done.exists():
                fetch(url, dest, sizes[sid, ext])
                done.touch()
            entry = {"strip": sid, "file": dest.name, "url": url, "bytes_server": sizes[sid, ext], "bytes_disk": dest.stat().st_size,
                     "sha256": sha256(dest)}
            entry["size_equal"] = entry["bytes_server"] == entry["bytes_disk"]
            ok &= entry["size_equal"]
            if ext == "JP2":
                entry["jp2_signature"], entry["jp2_end_marker"] = read_ends(dest)
                ok &= entry["jp2_signature"] and entry["jp2_end_marker"]
            record["files"].append(entry)
            print(f"{dest.name}: {entry['bytes_disk']} bytes, size equal {entry['size_equal']}", flush=True)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(record, indent=1) + "\n")
    record["free_bytes_after"] = shutil.disk_usage(config.strips_dir()).free
    record["ok"] = ok
    out.write_text(json.dumps(record, indent=1) + "\n")
    print(f"ok={ok}; written {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

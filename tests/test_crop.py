import subprocess
import sys
from pathlib import Path

import pytest

from landers import config
from tests.conftest import site_strips

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(not (ROOT / "controls" / "sites.json").exists(), reason="no sites file")
def test_grid_mode_writes_numbered_tiles(tmp_path):
    ids = site_strips("viking1")
    if not ids or config.find_strip(ids[0]) is None:
        pytest.skip("Viking 1 strip not on disk")
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "crop_site.py"),
            "viking1",
            "--grid",
            "--grid-m",
            "300",
            "--tile",
            "256",
            "--out",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    d = next(tmp_path.glob("viking1_*_grid"))
    tiles = sorted(d.glob("tile_*.png"))
    assert len(tiles) == 25 and (d / "index.png").exists()  # 300 m / 0.25 = 1200 px -> 5 x 5 tiles of 256


@pytest.mark.skipif(not (ROOT / "controls" / "sites.json").exists(), reason="no sites file")
def test_sealed_sites_refused(tmp_path):
    import json

    sealed = [
        s["name"]
        for s in json.loads((ROOT / "controls" / "sites.json").read_text())["sites"]
        if s["group"] == "heldout"
    ]
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "crop_site.py"), sealed[0], "--out", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 3 and "refused" in r.stderr

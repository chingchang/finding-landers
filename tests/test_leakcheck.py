import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITES = Path(os.environ.get("LEAKCHECK_SITES", ROOT / "controls" / "sites.json"))


@pytest.mark.skipif(not SITES.exists(), reason="controls/sites.json not in this checkout")
def test_repo_is_clean():
    r = subprocess.run([str(ROOT / "scripts" / "leakcheck.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not SITES.exists(), reason="controls/sites.json not in this checkout")
def test_detects_an_id(tmp_path):
    bad = ROOT / "experiments" / "_leak_probe.py"
    bad.write_text("x = '" + "ESP_" + "000000_0000'\n")
    try:
        r = subprocess.run([str(ROOT / "scripts" / "leakcheck.sh")], capture_output=True, text=True)
    finally:
        bad.unlink()
    assert r.returncode == 1 and "observation id" in r.stdout

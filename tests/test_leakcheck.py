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


def _run_with_probe(path: Path, text: str) -> subprocess.CompletedProcess:
    path.write_text(text)
    try:
        return subprocess.run([str(ROOT / "scripts" / "leakcheck.sh")], capture_output=True, text=True)
    finally:
        path.unlink()


@pytest.mark.skipif(not SITES.exists(), reason="controls/sites.json not in this checkout")
def test_detects_an_id(tmp_path):
    r = _run_with_probe(ROOT / "experiments" / "_leak_probe.py", "x = '" + "ESP_" + "000000_0000'\n")
    assert r.returncode == 1 and "observation id" in r.stdout


@pytest.mark.skipif(not SITES.exists(), reason="controls/sites.json not in this checkout")
def test_reports_may_name_an_id_but_not_a_sealed_site():
    # an observation id in a report is allowed: a report must say which strip a number came from
    r = _run_with_probe(ROOT / "docs" / "reports" / "_leak_probe.md", "strip " + "ESP_" + "000000_0000\n")
    assert r.returncode == 0, r.stdout + r.stderr
    # the sealed-site rules still apply under docs/reports/
    import json

    sealed = next(s for s in json.loads(SITES.read_text())["sites"] if s["group"] in ("heldout", "final_exam"))
    r = _run_with_probe(ROOT / "docs" / "reports" / "_leak_probe.md", f"near {sealed['name']}\n")
    assert r.returncode == 1 and "name of sealed site" in r.stdout
    r = _run_with_probe(ROOT / "docs" / "reports" / "_leak_probe.md", f"at {sealed['lat']}\n")
    assert r.returncode == 1 and "coordinate" in r.stdout

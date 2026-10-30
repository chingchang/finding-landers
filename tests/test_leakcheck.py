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


def _sealed_name():
    import json

    return next(s for s in json.loads(SITES.read_text())["sites"] if s["group"] in ("heldout", "final_exam"))["name"]


def _run_with_leakpy_edit(old: str, new: str) -> subprocess.CompletedProcess:
    """Run the check with one temporary edit to landers/models/leak.py, restoring the file afterwards."""
    path = ROOT / "landers" / "models" / "leak.py"
    original = path.read_text()
    assert old in original
    path.write_text(original.replace(old, new, 1))
    try:
        return subprocess.run([str(ROOT / "scripts" / "leakcheck.sh")], capture_output=True, text=True)
    finally:
        path.write_text(original)


@pytest.mark.skipif(not SITES.exists(), reason="controls/sites.json not in this checkout")
def test_marked_list_allows_a_sealed_name_only_inside_it():
    name = _sealed_name()
    # inside the marked forbidden-names block: allowed
    r = _run_with_leakpy_edit("MISSION_WORDS = (\n", f'MISSION_WORDS = (\n    "{name}",\n')
    assert r.returncode == 0, r.stdout + r.stderr
    # the same name in leak.py outside the block: still a leak
    r = _run_with_leakpy_edit("PNG_SIG = ", f'_PROBE = "{name}"\nPNG_SIG = ')
    assert r.returncode == 1 and "name of sealed site" in r.stdout


@pytest.mark.skipif(not SITES.exists(), reason="controls/sites.json not in this checkout")
def test_marked_list_does_not_relax_other_rules():
    # an observation id inside the marked block is still a leak: the exception covers names only
    r = _run_with_leakpy_edit("MISSION_WORDS = (\n", 'MISSION_WORDS = (\n    "' + "ESP_" + '000000_0000",\n')
    assert r.returncode == 1 and "observation id" in r.stdout


@pytest.mark.skipif(not SITES.exists(), reason="controls/sites.json not in this checkout")
def test_markers_count_only_in_leak_py():
    name = _sealed_name()
    text = (
        "# leakcheck: begin forbidden-names list\n"
        f'WORDS = ("{name}",)\n'
        "# leakcheck: end forbidden-names list\n"
    )
    r = _run_with_probe(ROOT / "experiments" / "_leak_probe.py", text)
    assert r.returncode == 1 and "name of sealed site" in r.stdout

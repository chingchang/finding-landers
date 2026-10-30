import json
import os
from pathlib import Path

import pytest

DATA = Path(os.environ.get("LANDERS_DATA", Path(__file__).resolve().parent.parent / "HiRISE"))

needs_data = pytest.mark.skipif(not (DATA / "strips").is_dir(), reason="HiRISE strips not on disk (set LANDERS_DATA)")


# A person may export run caps (LANDERS_CAP_*) in the shell for a paid run; tests use the defaults unless
# they set a cap themselves. Cleared at import so module- and session-scoped fixtures see the defaults too.
for _name in ("LANDERS_CAP_SAM", "LANDERS_CAP_WONDER", "LANDERS_CAP_SPARK"):
    os.environ.pop(_name, None)


@pytest.fixture(scope="session")
def all_labels():
    if not (DATA / "strips").is_dir():
        pytest.skip("HiRISE strips not on disk (set LANDERS_DATA)")
    sites = Path(__file__).resolve().parent.parent / "controls" / "sites.json"
    blind = {sid for s in json.loads(sites.read_text())["sites"] if s["group"] in ("heldout", "final_exam") for sid in s["strips"]}
    return sorted(p for p in (DATA / "strips").glob("*/*_RED.LBL") if p.name.split("_RED")[0] not in blind)  # a test never opens a blind strip's label


def manifest_ids(case_prefix: str) -> list[str]:
    """Observation ids in the manifest whose case starts with ``case_prefix``."""
    mf = DATA / "manifest.txt"
    if not mf.exists():
        return []
    out = []
    for line in mf.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith(case_prefix):
            out.append(parts[1])
    return out


def site_strips(name: str) -> list[str]:
    sites = Path(__file__).resolve().parent.parent / "controls" / "sites.json"
    if not sites.exists():
        return []
    for s in json.loads(sites.read_text())["sites"]:
        if s["name"] == name:
            return s["strips"]
    return []

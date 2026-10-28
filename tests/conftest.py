import os
from pathlib import Path

import pytest

DATA = Path(os.environ.get("LANDERS_DATA", Path(__file__).resolve().parent.parent / "HiRISE"))

needs_data = pytest.mark.skipif(not (DATA / "strips").is_dir(), reason="HiRISE strips not on disk (set LANDERS_DATA)")


@pytest.fixture(scope="session")
def all_labels():
    if not (DATA / "strips").is_dir():
        pytest.skip("HiRISE strips not on disk (set LANDERS_DATA)")
    return sorted((DATA / "strips").glob("*/*_RED.LBL"))


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
    import json

    sites = Path(__file__).resolve().parent.parent / "controls" / "sites.json"
    if not sites.exists():
        return []
    for s in json.loads(sites.read_text())["sites"]:
        if s["name"] == name:
            return s["strips"]
    return []

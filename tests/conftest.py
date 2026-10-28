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

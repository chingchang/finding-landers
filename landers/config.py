"""Where the data lives.

The strips are never committed. ``LANDERS_DATA`` points at a directory holding ``manifest.txt`` and
``strips/<case>/<id>_RED.{JP2,LBL}``; the default is ``<repo>/HiRISE``.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def data_root() -> Path:
    return Path(os.environ.get("LANDERS_DATA", REPO_ROOT / "HiRISE"))


def strips_dir() -> Path:
    return data_root() / "strips"


def manifest_path() -> Path:
    return data_root() / "manifest.txt"


def find_strip(observation_id: str) -> Path | None:
    """Path of ``<id>_RED.JP2`` under any case directory, or None if not on disk."""
    for p in strips_dir().glob(f"*/{observation_id}_RED.JP2"):
        return p
    return None


def label_path(observation_id: str) -> Path | None:
    for p in strips_dir().glob(f"*/{observation_id}_RED.LBL"):
        return p
    return None

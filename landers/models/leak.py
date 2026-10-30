"""The leak guard: nothing that says where an image is from reaches a model.

A request is refused when any text in it carries a HiRISE observation id, a file name, a date, a
coordinate with a bearing, a published coordinate or the name of a site in ``controls/sites.json``, or a
mission word. Images are refused when the PNG carries a text chunk (tEXt, iTXt, zTXt, eXIf): the crop
builder writes none, so one present means a file came from somewhere else.

The error names the kind of leak and where it sits, never the matched text: a sealed site's name must not
end up in a log either.
"""

from __future__ import annotations

import json
import os
import re
import struct
from functools import lru_cache
from pathlib import Path

from landers import config

OBS_ID = re.compile(r"\b(ESP|PSP)_\d{6}_\d{4}\b")
FILE_NAME = re.compile(r"\b\w+_RED\b|\.(JP2|LBL|IMG|jp2|lbl|img)\b")
DATE = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b|\b(19|20)\d{2}-\d{3}T?\b|\b(19|20)\d{2}_\d{3}\b")
BEARING_COORD = re.compile(r"[-+]?\d{1,3}(\.\d+)?\s*(°|deg|degrees)?\s*[NSEW]\b")
# leakcheck: begin forbidden-names list (scripts/leakcheck.sh lets sealed-site names stand here and nowhere else)
MISSION_WORDS = (
    "schiaparelli",
    "exomars",
    "curiosity",
    "msl",
    "phoenix",
    "viking",
    "spirit",
    "opportunity",
    "pathfinder",
    "sojourner",
    "beagle",
    "polar lander",
    "mpl",
    "mars 3",
    "mars3",
    "deep space 2",
    "gale",
    "gusev",
    "meridiani",
    "isidis",
    "chryse",
    "utopia",
    "planum",
    "hirise",
    "ctx",
    "nasa",
    "esa",
    "jpl",
    "pds",
)
# leakcheck: end forbidden-names list
PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_TEXT_CHUNKS = {b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"tIME"}


class LeakError(ValueError):
    """A request would tell the model where the image is from."""


def sites_path() -> Path:
    return Path(os.environ.get("LEAKCHECK_SITES", config.REPO_ROOT / "controls" / "sites.json"))


@lru_cache(maxsize=1)
def _site_terms() -> tuple[tuple[re.Pattern, ...], tuple[re.Pattern, ...]]:
    """(name patterns, coordinate patterns) from controls/sites.json, every group. Never printed."""
    names: list[str] = list(MISSION_WORDS)
    coords: set[str] = set()
    p = sites_path()
    if p.exists():
        for s in json.loads(p.read_text())["sites"]:
            names.append(re.sub(r"\d+$", "", s["name"]))
            names.append(s["name"])
            for rec in [s, *s.get("pieces_refined", [])]:
                for k in ("lat", "lon_e"):
                    v = rec.get(k)
                    if v is None:
                        continue
                    # values with fewer than three decimals (1 km precision) are too common as
                    # measurements to be a leak on their own; scripts/leakcheck.sh keeps the stricter rule
                    if "." in str(v) and len(str(v).split(".")[1]) >= 3:
                        coords.add(str(v))
                        coords.add(str(abs(float(v))))
    name_pats = tuple(re.compile(r"\b" + re.escape(n) + r"\b", re.I) for n in sorted(set(names)) if n)
    coord_pats = tuple(re.compile(r"(?<![\d.])" + re.escape(c) + r"(?![\d])") for c in sorted(coords))
    return name_pats, coord_pats


def find_leak(text: str) -> str | None:
    """The kind of the first leak in ``text`` and its offset, or None when clean."""
    for kind, pat in (("observation id", OBS_ID), ("file name", FILE_NAME), ("date", DATE)):
        m = pat.search(text)
        if m:
            return f"{kind} at offset {m.start()}"
    m = BEARING_COORD.search(text)
    if m:
        return f"coordinate with bearing at offset {m.start()}"
    names, coords = _site_terms()
    for pat in names:
        m = pat.search(text)
        if m:
            return f"site or mission name at offset {m.start()}"
    for pat in coords:
        m = pat.search(text)
        if m:
            return f"published coordinate at offset {m.start()}"
    return None


def check_text(text: str, where: str = "prompt") -> None:
    hit = find_leak(text)
    if hit:
        raise LeakError(f"{where}: {hit}")


def check_png(png: bytes, where: str = "image") -> None:
    """Refuse a PNG with any text or time chunk; such metadata is where file names and dates hide."""
    if not png.startswith(PNG_SIG):
        raise LeakError(f"{where}: not a PNG")
    pos = len(PNG_SIG)
    while pos + 8 <= len(png):
        (length,) = struct.unpack(">I", png[pos : pos + 4])
        ctype = png[pos + 4 : pos + 8]
        if ctype in PNG_TEXT_CHUNKS:
            raise LeakError(f"{where}: PNG carries a {ctype.decode('ascii', 'replace')} chunk")
        if ctype == b"IEND":
            return
        pos += 12 + length
    raise LeakError(f"{where}: truncated PNG")


def check_strings(obj, where: str = "request") -> None:
    """Walk a JSON-like object and check every string that is not an image data URL."""
    if isinstance(obj, str):
        if obj.startswith("data:image/"):
            return
        check_text(obj, where)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            check_strings(k, where)
            check_strings(v, f"{where}.{k}")
    elif isinstance(obj, list | tuple):
        for i, v in enumerate(obj):
            check_strings(v, f"{where}[{i}]")

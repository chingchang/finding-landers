"""PDS3 label reader for HiRISE RDR strips.

A label is ``KEY = VALUE`` text with ``<UNIT>`` suffixes, quoted strings, parenthesised lists, ``/* */``
comments and nested ``OBJECT``/``GROUP`` blocks. ``parse`` returns nested dicts; ``StripLabel.read`` pulls
out the fields the pipeline uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_UNIT = re.compile(r"^(.*?)\s*<([^>]*)>$", re.S)


def _convert(raw: str):
    raw = raw.strip()
    m = _UNIT.match(raw)
    if m:
        raw = m.group(1).strip()
    if raw.startswith('"') and raw.endswith('"'):
        return " ".join(raw[1:-1].split())
    if raw.startswith("(") and raw.endswith(")"):
        inner = raw[1:-1].strip()
        return [_convert(x) for x in inner.split(",")] if inner else []
    if raw.startswith("{") and raw.endswith("}"):
        inner = raw[1:-1].strip()
        return [_convert(x) for x in inner.split(",")] if inner else []
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _statements(text: str):
    """Yield (key, raw_value) pairs, joining values that run over several lines."""
    text = _COMMENT.sub("", text)
    key = None
    buf: list[str] = []

    def balanced(s: str) -> bool:
        return s.count('"') % 2 == 0 and s.count("(") == s.count(")") and s.count("{") == s.count("}")

    for line in text.splitlines():
        if key is None:
            if "=" not in line:
                if line.strip() == "END":
                    return
                continue
            k, _, v = line.partition("=")
            key, buf = k.strip(), [v.strip()]
        else:
            buf.append(line.strip())
        joined = " ".join(buf)
        if balanced(joined):
            yield key, joined
            key = None
    if key is not None:
        yield key, " ".join(buf)


def parse(text: str) -> dict:
    """Nested dict of the label. OBJECT/GROUP blocks become sub-dicts keyed by their name."""
    root: dict = {}
    stack: list[dict] = [root]
    for key, raw in _statements(text):
        if key in ("OBJECT", "GROUP"):
            child: dict = {}
            stack[-1][raw.strip()] = child
            stack.append(child)
        elif key in ("END_OBJECT", "END_GROUP"):
            if len(stack) > 1:
                stack.pop()
        else:
            stack[-1][key] = _convert(raw)
    return root


@dataclass(frozen=True)
class StripLabel:
    observation_id: str
    rationale: str
    lines: int
    samples: int
    scale_m: float  # MAP_SCALE, metres per pixel
    projection: str  # "EQUIRECTANGULAR" or "POLAR STEREOGRAPHIC"
    center_lat: float
    center_lon: float
    line_offset: float
    sample_offset: float
    map_resolution: float  # pixels per degree
    radius_m: float  # A_AXIS_RADIUS in metres
    min_lat: float
    max_lat: float
    west_lon: float
    east_lon: float
    incidence_deg: float
    sub_solar_azimuth_deg: float
    north_azimuth_deg: float
    solar_longitude_deg: float
    start_time: str

    @classmethod
    def read(cls, path: str | Path) -> StripLabel:
        d = parse(Path(path).read_text(errors="replace"))
        proj = d["IMAGE_MAP_PROJECTION"]
        img = d["UNCOMPRESSED_FILE"]["IMAGE"]
        view = d["VIEWING_PARAMETERS"]
        return cls(
            observation_id=str(d["OBSERVATION_ID"]),
            rationale=str(d.get("RATIONALE_DESC", "")),
            lines=int(img["LINES"]),
            samples=int(img["LINE_SAMPLES"]),
            scale_m=float(proj["MAP_SCALE"]),
            projection=str(proj["MAP_PROJECTION_TYPE"]),
            center_lat=float(proj["CENTER_LATITUDE"]),
            center_lon=float(proj["CENTER_LONGITUDE"]),
            line_offset=float(proj["LINE_PROJECTION_OFFSET"]),
            sample_offset=float(proj["SAMPLE_PROJECTION_OFFSET"]),
            map_resolution=float(proj["MAP_RESOLUTION"]),
            radius_m=float(proj["A_AXIS_RADIUS"]) * 1000.0,
            min_lat=float(proj["MINIMUM_LATITUDE"]),
            max_lat=float(proj["MAXIMUM_LATITUDE"]),
            west_lon=float(proj["WESTERNMOST_LONGITUDE"]),
            east_lon=float(proj["EASTERNMOST_LONGITUDE"]),
            incidence_deg=float(view["INCIDENCE_ANGLE"]),
            sub_solar_azimuth_deg=float(view["SUB_SOLAR_AZIMUTH"]),
            north_azimuth_deg=float(view["NORTH_AZIMUTH"]),
            solar_longitude_deg=float(view["SOLAR_LONGITUDE"]),
            start_time=str(d["TIME_PARAMETERS"]["START_TIME"]),
        )

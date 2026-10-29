"""The tiling plan: strip order, tile counts, and a time estimate from a measured rate.

The rate comes from a detector run's log (``scripts/detect.py`` prints one summary line per strip), never
from a number typed in; the plan records which log it read and what it found there.
"""

from __future__ import annotations

import re
from pathlib import Path

from landers.search.inventory import StripRecord

_LINE = re.compile(r"^(\S+): (\d+) candidates from (\d+) tiles in (\d+)s\s*$")
SESSION_SECONDS = 7200  # the unattended loop waits at most two hours for one foreground run


def baseline_rate(run_log: str | Path) -> dict:
    """Tiles per second of wall time from a detect.py log; per-strip lines kept so the number can be checked."""
    text = Path(run_log).read_text(errors="replace").replace("\r", "\n")
    strips = []
    for line in text.splitlines():
        m = _LINE.match(line.strip())
        if m:
            strips.append({"observation_id": m.group(1), "tiles": int(m.group(3)), "seconds": int(m.group(4))})
    tiles = sum(s["tiles"] for s in strips)
    seconds = sum(s["seconds"] for s in strips)
    if tiles == 0 or seconds == 0:
        raise ValueError(f"{run_log}: no per-strip summary lines")
    return {
        "source": str(run_log),
        "strips": strips,
        "tiles": tiles,
        "seconds": seconds,
        "tiles_per_second": round(tiles / seconds, 4),
    }


def order_key(rec: StripRecord):
    """2007 PSP strips first, then the rest by date; strips whose title is not the search go last."""
    return (not rec.search_title, rec.phase != "PSP", rec.date, rec.observation_id)


def tiling_plan(records: list[StripRecord], rate: dict, session_seconds: int = SESSION_SECONDS) -> dict:
    tps = rate["tiles_per_second"]
    ordered = sorted(records, key=order_key)
    strips = []
    sessions: list[list[str]] = []
    load = 0.0
    cum = 0.0
    for rec in ordered:
        est = rec.tiles / tps
        cum += est
        if sessions and load + est <= session_seconds:
            sessions[-1].append(rec.observation_id)
            load += est
        else:
            sessions.append([rec.observation_id])
            load = est
        note = None
        if not rec.search_title:
            note = "title is not the lander search; docs/data.md calls it a bed for false alarms; last in order"
        strips.append(
            {
                "observation_id": rec.observation_id,
                "phase": rec.phase,
                "date": rec.date,
                "valid_area_km2": rec.valid_area_km2,
                "tiles": rec.tiles,
                "estimated_seconds": round(est),
                "cumulative_seconds": round(cum),
                "session": len(sessions),
                "fits_one_session": est <= session_seconds,
                "note": note,
            }
        )
    total_tiles = sum(r.tiles for r in ordered)
    psp = [r for r in ordered if r.phase == "PSP"]
    return {
        "rate": rate,
        "tile_px": ordered[0].tile_px if ordered else None,
        "overlap_px": ordered[0].overlap_px if ordered else None,
        "session_seconds": session_seconds,
        "strips": strips,
        "sessions": sessions,
        "totals": {
            "strips": len(ordered),
            "tiles": total_tiles,
            "valid_area_km2": round(sum(r.valid_area_km2 for r in ordered), 3),
            "estimated_seconds": round(total_tiles / tps),
            "estimated_hours": round(total_tiles / tps / 3600, 2),
            "psp_strips": len(psp),
            "psp_tiles": sum(r.tiles for r in psp),
            "psp_estimated_hours": round(sum(r.tiles for r in psp) / tps / 3600, 2),
            "sessions": len(sessions),
        },
    }

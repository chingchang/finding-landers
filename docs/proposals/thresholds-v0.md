# Proposal: controls/thresholds.json, version 0

Proposed by the agent on 2026-10-28. A person creates `controls/thresholds.json`; the scoring script refuses
to run without it and the agent never writes it.

```json
{
  "version": 0,
  "match_radius_px": 20,
  "top_n": 20,
  "pass": {"min_recall_at_n": 0.8, "max_false_alarms_per_km2": 2.0}
}
```

Why these numbers:

- `match_radius_px` 20 (5 m at 25 cm/px): the pieces are 1 to 5 m across, a person's recorded position is good
  to a few pixels, and a candidate's centroid can sit anywhere on the piece. 20 px keeps a hit from being counted
  against a neighbouring piece (parachute and backshell are usually tens of metres apart).
- `top_n` 20: a person can check twenty crops per strip by hand in a few minutes.
- `min_recall_at_n` 0.8: with roughly 20 recorded pieces across the six tuning sites, 0.8 allows a few misses
  (Pathfinder at 50 cm/px, fading parachutes) without passing a detector that misses most landers.
- `max_false_alarms_per_km2` 2.0: an MPL strip is 100 to 200 km2, so 2/km2 is a few hundred crops to check per
  strip. That is the most a person can review across 34 strips in the time there is. Lower it once the
  persistence test is in and the number comes down.

Change by a person only. The agent proposes a new version in a new file.

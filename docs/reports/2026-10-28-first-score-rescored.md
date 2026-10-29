# Report: the first score, rescored under thresholds version 1 (2026-10-28)

The person who owns the scoring adopted docs/proposals/scoring-v1.md: one candidate matches at most one
piece; pieces are scored as hardware, fabric or mark; a mark gets a 20 m match radius. `controls/thresholds.json`
is now version 1 and `landers/score.py` implements the matching. The baseline v1 lists are unchanged
(`out/baseline_v1/candidates_baseline_v1.json`, code 3c59e16, saved before the key existed).

```
python3 scripts/score.py out/baseline_v1/candidates_baseline_v1.json
```

## Both numbers

| thresholds | matching | recall@20 | median false alarms per km2 | verdict | file |
|---|---|---|---|---|---|
| v0 | any candidate may serve several pieces, 5 m everywhere | 0.23 (3 of 13) | 708.21 | FAIL | `out/baseline_v1/score_baseline_v1.json` |
| v1 | one candidate per piece; marks at 20 m | 0.15 (2 of 13) | 708.21 | FAIL | `out/baseline_v1/score_baseline_v1_thresholds_v1.json` |

By kind under v1: hardware 1 of 9, fabric 1 of 2, mark 0 of 2.

The 0.23 counted the Schiaparelli canopy detection twice (parachute and backshell are recorded 21 px
apart). Under v1 that detection goes to the nearer recorded point, the backshell at 9.9 px, and the
parachute is scored on what else lies within 20 px of its point, which is nothing. The 20 m radius for
marks changes no rank: the crash scar's best candidate is still the one at 17.7 px (rank 51685) and
the descent-stage fan still has no candidate within 20 m. The number to beat is 2 of 13 at 708 per km2,
and the hardware line, 1 of 9, is the one the search depends on.

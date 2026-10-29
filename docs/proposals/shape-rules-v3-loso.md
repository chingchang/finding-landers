# Proposal: withdraw `tile_top` (shape_v3), from the leave-one-site-out check

Proposed by the tuning loop (docs/plan.md item 8, second session) on 2026-10-29, from
docs/reports/2026-10-29-tuning-loop-2.md. The file to adopt is `docs/proposals/shape_v3.json`:
`landers/shape_v2.json` with `tile_top` removed and the other three rules unchanged. Adopting it means
committing it as `landers/shape_v3.json`. Nothing is applied until then; `landers/shape_v2.json` stays as
adopted, and its adoption note made `tile_top` conditional on this check.

Every number below is copied from `out/loso/shape_v2/loso_shape_v2.json`, written by
`uv run scripts/loso.py --name shape_v2` at this commit (the key board is the 18-piece `controls/tuning.json`
under thresholds v1 rescored from `out/shape_v1/candidates_v02b_features.json`; the injection board is
`out/transplant_t2/transplant_t2.json` with the fold's rules applied to the recorded features).

## What the check does

For each of the six tuning sites, every rule's pass fraction and gain is re-fitted on the false alarms of the
other five sites' strips only (both dates of a two-date site go with the site), and the held-back site's
pieces are scored under those gains, on the key and on the injection run (plantings cut from that site
only). The six folds are pooled. Each rule is then judged by ablation on the pooled held-out boards: the
boards with every rule against the boards with that one rule left out.

Two questions are kept apart. The plan's condition, **lift holds**: on sites the rule was not fitted on,
leaving it out makes no board better and pushes no piece out of the top 20. A stricter one, **pass fraction
stable**: the fraction fitted on every fold, and measured on every single strip, stays at or under the bar
(0.05). The bar as written pools the tuning strips, and pooling by count lets one busy strip carry a rule.

What the check does not do: the thresholds inside the rules (two_sided >= 4.0, and so on) were chosen in
the first session from the pooled quantiles with every piece in view, and are not re-chosen per fold. The
check re-fits gains, not tests. The held-out run (item 10) is where the tests themselves are paid back.

## Pooled held-out boards

| rules applied (gains fitted without the scored site) | key recall@20 | hardware | fabric | injection | hardware | fabric |
|---|---|---|---|---|---|---|
| none | 3 of 18 | 2 of 12 | 1 of 4 | 22 of 108 | 16 of 72 | 6 of 24 |
| all four | 8 of 18 | 7 of 12 | 1 of 4 | 44 of 108 | 35 of 72 | 9 of 24 |
| without saturated | 5 of 18 | 4 of 12 | 1 of 4 | 32 of 108 | 25 of 72 | 7 of 24 |
| without shadow_strong | 8 of 18 | 7 of 12 | 1 of 4 | 43 of 108 | 34 of 72 | 9 of 24 |
| without dark_shadow | 7 of 18 | 6 of 12 | 1 of 4 | 44 of 108 | 35 of 72 | 9 of 24 |
| without tile_top | 8 of 18 | 7 of 12 | 1 of 4 | 42 of 108 | 32 of 72 | 10 of 24 |

The held-out boards with all four rules equal the in-sample boards of the first session (8 of 18, 35 of 72,
9 of 24): fitting the gains without the scored site changes no outcome, so the lift is not an artefact of
in-sample gain fitting. The gains themselves move little between folds: saturated 2.486 to 2.745,
shadow_strong 2.998 to 3.132, dark_shadow 2.666 to 2.997, tile_top 1.091 to 1.611.

## Per rule

| rule | lift holds | pass fraction by fold | pass fraction by strip | verdict |
|---|---|---|---|---|
| saturated | yes: key 8 against 5, injection hardware 35 against 25 | 0.0018 to 0.00327 | 0 to 0.00833 | holds |
| shadow_strong | yes: key 8 against 8, injection hardware 35 against 34; Phoenix backshell 19 to 2 on its held-out fold | 0.00074 to 0.001 | 0 to 0.00234 | holds |
| dark_shadow | yes: key 8 against 7 (Phoenix heat shield 1527 to 7 on its held-out fold, gain fitted on the other five sites), injection unchanged | 0.00101 to 0.00216 | 0.0002 to 0.0039 | holds |
| tile_top | yes: key 8 against 8, injection hardware 35 against 32, fabric 9 against 10 | 0.02447 to 0.0811 | 0.00634 to 0.45351 | fails: pass fraction not stable |

`tile_top` on the held-out key: Schiaparelli parachute fragment 775 to 174, Curiosity backshell 9 to 6,
Curiosity heat shield 214 to 47, Pathfinder backshell 3 to 1; against that, Viking 1 lander 3 to 5, Phoenix
heat shield 5 to 7, Phoenix lander 704 to 1035, Spirit lander 454 to 521, Spirit parachute 125 to 152. No
piece crosses 20 either way. On held-out injection it finds two more Curiosity heat shield plantings
(4 against 2 of 6) and one more Spirit lander (4 against 3), and loses one Spirit parachute (3 against 4).

## Why withdraw it

The rule asks whether the candidate is the strongest bright component in its 2048 px tile. Its pass
fraction is therefore a property of how busy the ground is, not of the object: on the Spirit strip, which
holds 33289 of the 54424 bright and shadow false alarms, it passes 0.006; on the Phoenix second-date strip,
with 699, it passes 0.454; it is over the 0.05 bar on five of the eight strips, and over it pooled (0.081)
as soon as the Spirit strip is held back. The pooled 0.035 that met the bar in the first session is the
Spirit strip's count carrying the other seven. A single gain of 1.45 then over-rewards nearly half of the
bright false alarms on a quiet strip and under-rewards on a busy one. The other three rules sit under the
bar on every strip, by a factor of at least six.

Its lift is real but small and bought on injection, not on the key, and it is the same ground effect. The
shape_v2 proposal said the injection tiles hold hundreds of bright components each, so the test would be
strict there; detector v0.3's `tile_count` says otherwise (`experiments/injection_tile_count.py` on
`out/transplant_t4/transplant_t4.json`): of the 43 injection tiles with a bright detection, 26 hold fewer
than 10 bright components (median 4, a few hold hundreds), and the plantings `tile_top` lifts sit in tiles
with 1 to 6. The rule rewards being on quiet ground, where a planted piece and the handful of false alarms
beside it are all lifted together.

## Options

1. **Adopt shape_v3** (recommended): withdraw `tile_top`. Judged in-sample by the tuning judge against
   shape_v2 (`out/tune/v3_three_vs_v2/tune_v3_three_vs_v2.json`, from
   `uv run scripts/tune.py --name v3_three_vs_v2 --rules docs/proposals/shape_v3.json --reference-rules landers/shape_v2.json`):
   key 8 of 18 against 8, hardware 7 of 12 against 7, injection hardware 32 of 72 against 35, fabric 10 of 24
   against 9, overall 0.389 against 0.407, threshold 0.302 against 0.432, sham hits 1 of 108 either way. The
   judge's verdict on that comparison is REVERT, as it must be (injection hardware drops); the withdrawal is
   proposed on the stability finding, not on the bar. Against shape_v1
   (`out/tune/v3_three/tune_v3_three.json`) the three rules are a KEEP: key 8 of 18 against 6, hardware 7 of
   12 against 5, injection hardware 32 of 72 against 31, fabric 10 of 24 against 10. The held-out board
   without tile_top above says the same.
2. **Keep shape_v2** as adopted, on the plan's written condition (lift holds), accepting the per-strip
   instability and the fabric planting lost. The check's output states both facts either way.
3. **A conditioned form** (tile_top only where the tile holds at least 10 bright components) was tried
   on the v0.3 runs (`out/tune/e11_tile_top_busy/tune_e11_tile_top_busy.json`): 0.0145 of false alarms
   pass, under the bar on every strip, key unchanged at 8 of 18, but the injection lift goes with the quiet
   tiles (hardware 32 of 72 against 35). Reverted; it is in docs/experiments.md.

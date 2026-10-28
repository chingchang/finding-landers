# Report: shape features for the small-object branches, measured on phase 1 injection (2026-10-28)

Item 4 of the four. The features are recorded on every bright, shadow and dark_compact candidate and do
not change any score. The injector draws discs and ellipses, so a score tuned to these numbers would learn
the injector; the real answer key decides which of them matter.

## What I did

- `landers/shape.py`: circularity (4 pi area / perimeter^2), fill (area / bounding box), elongation
  (1 - sqrt(minor/major) of the second moments), edge sharpness (mean |gradient of z| on the boundary over
  the peak |z|), tile rank (how many components of the same sign in the tile have a higher peak; 0 is the
  strongest), and for the shadow branch the shadow-to-object peak ratio. Computed on each component's
  bounding box, so they cost little.
- `scripts/inject.py --features`: for each injected kind and the branch that found it, the AUC of every
  feature between hits and that branch's false alarms (probability a random hit scores above a random
  false alarm; 0.5 is no separation, values far below 0.5 mean hits score lower).

## Numbers

From `out/inject_eval_p1_cal_features.json` (viking1, curiosity, spirit, pathfinder, phase 1 tiles, seed 1,
calibration v0, 8.126 km2). Recall at 2 false alarms per km2 is unchanged from the calibration report
(0.158 overall), as it must be: the features are not in the score.

| kind | branch | hits | false | circularity | edge sharpness | elongation | fill | tile rank | shadow ratio |
|---|---|---|---|---|---|---|---|---|---|
| blob_shadow | bright | 7 | 1313 | 0.461 | 0.565 | 0.127 | 0.603 | 0.008 | |
| blob_shadow | dark_compact | 21 | 1587 | 0.495 | 0.826 | 0.457 | 0.456 | 0.167 | |
| blob_shadow | shadow | 34 | 124 | 0.494 | 0.577 | 0.155 | 0.519 | 0.251 | 0.407 |
| dark_compact | dark_compact | 29 | 1587 | 0.466 | 0.676 | 0.321 | 0.512 | 0.218 | |
| sheet | bright | 6 | 1313 | 0.362 | 0.286 | 0.533 | 0.479 | 0.265 | |

(blob_shadow found by dark_compact is the injected object's own shadow being detected as a dark compact.)

## What it says, and what it cannot say

- **Edge sharpness separates in every small-object branch** (0.57 to 0.83): injected objects have crisper
  z-edges than rocks and slopes at the same peak. This is the one feature that is not obviously a property
  of how the injector draws, since the injector blurs every edge by 1 px like the optics would.
- **Low elongation and low tile rank separate strongly** (0.13 to 0.32, and 0.008 to 0.27), but discs are
  round by construction and the injected contrasts make them the strongest thing in most tiles. On real
  hardware a lander is wider than tall and a backshell is round, so these may hold; the key will say.
- **Circularity does nothing** (0.36 to 0.50), even for injected discs: at 4 to 16 px across, the component
  mask is too coarse for a perimeter to mean much. Drop it or compute it on an upsampled mask.
- **Shadow ratio is weak** (0.41): the injected shadow contrast is fixed, so this measures the ground.

## What I would do next

Nothing to the score until the key has real pieces in it. Then: per piece, where it sits in each feature's
distribution of false alarms on the same strip; a feature in which every real piece is in the top few
percent of false alarms earns a place in the score, with its threshold recorded like every other number.

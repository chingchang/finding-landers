# Item 12d: the replaced strip of the blind set is on disk, unopened

## What I did

Downloaded ESP_046150_2280 and its label into `HiRISE/strips/`, the strip `controls/sites.json` now names in place of
the one whose footprint missed its site (10-30 17:17 decision). `scripts/fetch_blind.py` skipped PSP_009141_1780,
already complete, and rehashed it. Every number below is from `docs/reports/2026-10-30-blind-download-2/fetch.json`.

| file | bytes on the server | bytes on disk | JP2 signature and end marker |
|---|---|---|---|
| ESP_046150_2280_RED.LBL | 8097 | 8097 | not applicable |
| ESP_046150_2280_RED.JP2 | 1343309268 | 1343309268 | both present |
| PSP_009141_1780_RED.LBL | 8129 | 8129 | not applicable |
| PSP_009141_1780_RED.JP2 | 1167368413 | 1167368413 | both present |

The sha256 of each file is in the record, so the person can pin them when sealing the key. Both PSP_009141_1780 hashes
equal those in `docs/reports/2026-10-30-blind-download/fetch.json`, so that strip did not change on disk. Free disk went
from 4383645696 to 3033325568 bytes; the free-disk floor did not refuse.

**These checks do not show the strip decodes, or that it holds its target.** No pixel was read and no label was parsed,
on purpose. A damaged codestream with the right length and end marker would not be caught here, and whether the
footprint contains the site rests on the oracle's reading of the HiRISE index. The first decode is the person's or the
blind run's.

## What I decided, and why

- **No code changed.** The rules of 12c(d) already cover this strip: the script takes its ids from
  `controls/sites.json`, and the test fixture and the detector routes key on the `heldout` group, not on a strip id. The
  test suite ran after the download with this strip in that group.
- **The record's `what` field still reads "item 12c(d)".** It is a constant in the script. I left it rather than change
  the script for a label; the record's path and this report name the item.
- **One line added to `HiRISE/manifest.txt`,** as `docs/data.md` asks for new strips. The line of the replaced strip
  stays, as the last report left the line of the strip it replaced. The file itself is deleted, per the plan; I did not
  check that. `HiRISE/download_hirise.sh` reads the manifest, so running it on `control_viking2` would fetch the old
  strip again. The copy under `LANDERS_DATA` (the main checkout) gets the new line when this branch is merged.

## Not done

- The blind key: the oracle places it from published captioned images and the person seals it, before any v2 scoring.
- Item 12c(c), the JP2 delete, stays on hold for the person. Nothing was deleted here.

## What I would do next

With 3033325568 bytes free and a floor of 2000000000 in the script, another strip of this size would be refused, so any
further download needs the delete first. After that, the next open items in the plan's order.

## Commands

    uv run --env-file out/landers.env scripts/fetch_blind.py --out docs/reports/2026-10-30-blind-download-2/fetch.json

Credit for all images: NASA/JPL/University of Arizona.

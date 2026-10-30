# Item 12c(d): the two strips of the new blind set are on disk, unopened

## What I did

Downloaded the two strips of the `heldout` group in `controls/sites.json`, ESP_077167_2285 and PSP_009141_1780, each
with its label, into `HiRISE/strips/`. The ids are the ones committed there on 10-30 (be80559 for the second). Every
number below is from `docs/reports/2026-10-30-blind-download/fetch.json`.

| file | bytes on the server | bytes on disk | JP2 signature and end marker |
|---|---|---|---|
| ESP_077167_2285_RED.LBL | 8116 | 8116 | not applicable |
| ESP_077167_2285_RED.JP2 | 1237915073 | 1237915073 | both present |
| PSP_009141_1780_RED.LBL | 8129 | 8129 | not applicable |
| PSP_009141_1780_RED.JP2 | 1167368413 | 1167368413 | both present |

The sha256 of each file is in the record, so the person can pin them when sealing the key. Free disk went from
6799450112 to 4393967616 bytes.

**These checks do not show the strips decode.** No pixel was read and no label was parsed, on purpose, so a damaged
codestream with the right length and end marker would not be caught here. The first decode is the person's or the
blind run's.

## What I decided, and why

- **No agent opened either strip.** `scripts/fetch_blind.py` takes the ids from `controls/sites.json`, and checks bytes
  only: size against the server, the first and last bytes of the JP2, and a hash. The record holds ids, sizes and hashes.
- **The tests no longer read blind labels.** The `all_labels` fixture in `tests/conftest.py` took every label on disk,
  so the next test run would have parsed these two and could have printed their contents on a failure. It now skips the
  `heldout` and `final_exam` groups. The other routes were already closed: `scripts/detect.py` and `scripts/crop_site.py`
  refuse these groups, and the export skips them. Run with `--frozen`, `detect.py` will open them, as the blind run must.
- **One line added to `HiRISE/manifest.txt`,** for PSP_009141_1780, as `docs/data.md` asks for new strips. The other
  strip already had its line. The old line of the strip this one replaces stays. The copy under `LANDERS_DATA` (the main
  checkout) gets the line when this branch is merged; no code reads the control lines of it for these strips.
- **The item is marked paused, not done,** as the plan's resume note asks: (c) is still on hold for the person.

## Not done

- (c) The JP2 delete, on hold for the person. This download used free space, so nothing was deleted.
- The blind key for both strips: the oracle places it from published captioned images and the person seals it, before
  any v2 scoring.
- `docs/data.md` still lists the older strip for the second site and an old count of what is on disk. I left it, since
  the file also holds the control tables a person owns; `controls/sites.json` is the current list.

## What I would do next

Item 14's pricing and dry run, then item 15, as the 10-30 15:45 decision orders them. With 4393967616 bytes free, item
15's outputs have room, but another large download would need the delete first.

## Commands

    uv run --env-file out/landers.env scripts/fetch_blind.py --out docs/reports/2026-10-30-blind-download/fetch.json

The script skips files that have a `.done` marker and resumes from a `.part` file, so rerunning it rewrites the record
without downloading again.

Credit for all images: NASA/JPL/University of Arizona.

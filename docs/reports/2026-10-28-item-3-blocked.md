# Report: item 3 blocked, a person fills the key (2026-10-28)

Unattended plan loop. Merged main into this branch first (two commits: the item 2 feedback and the
`.claude/settings.json` deny rules). The first open item under Now is item 3, the key. The key is a
tier-1 file: filled by a person in a private copy, copied to `controls/tuning.json` by a person, never
read or written by the agent. Marked `[blocked]` in `docs/plan.md` and stopped. No code changed.

## What I did

- `git merge --no-edit main`: clean, no conflicts.
- Read `docs/plan.md`. Items 1 and 2 are `[done]`; item 3 is the first `[ ]` and needs a person.
- Marked item 3 `[blocked: a person fills the key; the agent must not read or write it]`.

## What I decided and why

- Did not start item 4 (first score). It needs the key, which does not exist in the repo yet, and the
  loop's rule is one item per session, the first open one.
- Did not act on the two feedback notes under item 2, because item 2 is marked `[done]` and the status of
  an item is the person's to reopen. Checked whether the code already does what the notes ask; it does not:
  - the contact-sheet thumbnails are stretched one crop at a time (`thumbnails` in `landers/sheets.py`
    calls the 0.5 to 99.5 percentile stretch per 128 px crop), so brightness cannot be compared across
    thumbnails; the `cut_grids.py` tiles are already cut from one stretched window, so (a) applies to the
    sheets, not the grids;
  - the sheets rank picks by detector score alone (`select` in `landers/sheets.py`); the detector's shadow
    branch does read the label azimuth, but no rank uses the two-sided test the note asks for (dark on the
    anti-sun side only, not on the sun side);
  - Schiaparelli sheets still use the 1.5 km radius around the refined position, not 3 km around each
    strip's own centre;
  - `scripts/leakcheck.sh` still scans `docs/reports/` for observation ids. The reports on this branch pass
    it only because an earlier session rewrote them to name strips by site and date order (commit 8fb5732),
    with the id kept in the results file; the 16:20 note asks instead that reports carry the id and the
    check allow observation ids under `docs/reports/`, keeping the sealed-site name and coordinate rules
    everywhere. The check is clean today (62 files), so nothing is red; the allowance is still unmade.

## What I would do next

If a person reopens item 2 (change `[done]` to `[ ]`, or add an item 2b), the next loop session would take
it: one global stretch per sheet, a shadow-side rank from the label azimuth, a 3 km area around each
Schiaparelli strip centre, and the leak-check allowance for observation ids in reports. The sheets would
then be rebuilt from the baseline v1 lists without changing the lists.

Otherwise the loop waits on the key. Once `controls/tuning.json` is committed by a person, item 4 is the
first open item and is agent work.

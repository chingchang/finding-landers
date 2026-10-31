# Honest-tail calibration: nothing to adopt into the ranking, one question

Item 15's rule is not met: key 9 against 8 and transplant 17 against 15 at N = 20, but phoenix heat shield (5 to 22) and
schiaparelli backshell (8 to 84) leave the top 20, and moving the split by 500 m turns the two wins into a tie and a loss.
Numbers: `docs/reports/2026-10-30-halfcal.md`, `docs/reports/2026-10-30-halfcal/summary.json`. All on tuning sites;
perseverance, insight, zhurong and beagle2 are not blind.

So no change to the order of any list is proposed.

## The question for the person

Should v2's list carry the half-fitted rate as a column beside its score, with no change to the order?

I recommend yes. A candidate would read "about this many like it per km2 of this strip, measured on the other half of the
strip", or "rarer than one in this colour's area" at the cap. On the tuning strips that rate holds within about 1.4 at
levels 0 and 1 on ground the curve did not see, where the frozen-v1 table's realised rate spans more than three orders of
magnitude between strips. It would give the write-up and the completeness map a false-alarm rate that can be defended.

It costs one more file per strip and no pixels. It decides no grade: a result still becomes a candidate only through the
physical tests and two dates.

If the answer is no, nothing else follows, and the code stays in `landers/halfcal.py` and `scripts/halfcal.py` unused.

## Not proposed

Item 8's extrapolated tail (key 11, transplant 24, none dropped at N = 20) and the better-rank arm (key 10, transplant 22,
none dropped) were reported beside and read after the fact, so they have no standing under the rule. If you want either
tried, it would be labelled as chosen after seeing this result and judged only by the blind run, as item 14's combined
list is. I would not add them: each is one more comparison on the same 32 pieces.

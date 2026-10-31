# Two vote orderings (item 14a), fixed before their boards are computed

The person asked on 10-31 for two orderings built from item 14's recorded votes. No model is called. This file is committed
before the script that scores them exists. By then I had seen item 14's summary (frozen-v1, combined, combined + vote rule,
+ review) and nothing about these two orderings.

Both are post hoc. The votes were read with the pieces of tuning sites on the same board, and only the blind run in item 17
can judge either one. Neither touches a grade. The line in CLAUDE.md, "a model's opinion can lower a result, never raise it",
is about grades, and a list position is what a person reads first, so whether a vote may lift a position is the person's call.

## Definitions

The base list is the combined list. Depth means position on the combined list. A candidate counts as voted only inside the
top 100 of its own list: a strip's list on the key, one fold's pool of detections on the transplant board. On that board a
detection voted because of another fold's top 100 counts as unvoted in this fold, so both boards have the same depth. An
off-schema vote counts as unsure.

## Ordering (a): first vote hardware moves up

Inside the voted top 100, every candidate whose first vote is hardware, at any confidence, moves ahead of every other
candidate, and these keep their combined order among themselves. Everything else keeps its combined order behind them.
Nothing is lowered.

The depth band is the whole voted top 100, one band. The plan's example was a band at the strip's own depth. A band that ends
at a reported cut (10, 20, 50 or 100) cannot move a piece across that cut, so narrow bands would leave the curve looking
unchanged whatever the votes say. One band also has no width to choose.

The extra row (a) + vote rule is (a) with item 14's lowered candidates moved below everything, as in the combined + vote rule
row. A first vote of hardware is never lowered by that rule, so the two do not collide.

## Ordering (b): votes change only the order

Each voted candidate gets a signed vote `s`, the mean over its votes (one, or three in the borderline band) of +confidence
for hardware, -confidence for natural and 0 for unsure. Its sort key is

    key = depth * 4 ** (-s)

An unvoted candidate's key is its depth. The list sorts by key, smallest first, and a tie goes to the better depth. Nothing
is lowered to likely natural, and no grade changes.

So a natural vote at full confidence counts as being four times deeper, and a hardware vote at full confidence as being four
times shallower. Four is a choice with no measurement behind it, made so that a confident vote on a candidate near rank 80
can reach the top 20, and a confident natural vote at rank 6 leaves it. The results file also shows factors 2 and 8, labelled
as sensitivity only and not as further orderings to choose from.

## What is reported, fixed now

1. Recall at 10, 20, 50, 100 and 250 on the key and the transplant board for frozen-v1, combined, combined + vote rule, (a),
   (a) + vote rule and (b), each with a 95 percent Wilson interval.
2. Every recorded or planted piece in the top 20 on the combined list that is out of the top 20 on each other list, by name,
   and every piece that comes in.
3. Which ordering, if any, 16a's switch should use. The oracle and the person decide.

## What would count against an ordering, fixed now

- Any recorded hardware piece leaving the top 20 counts against it, whatever the total does.
- A gain on the key with a loss on transplant is not a gain: the transplant board is the stand-in for ground with no lander
  site's own texture.
- A gain of one or two pieces of 32 sits inside the interval, and the report says so.

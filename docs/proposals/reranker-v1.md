# Item 13: two decisions for a person

The re-ranker as declared does not meet the rule and is not proposed for adoption. Numbers and caveats are in
`docs/reports/2026-10-30-reranker.md`, copied from `docs/reports/2026-10-30-reranker/summary.json`. The agent changes
nothing here; the person decides. All of it is not blind on the four sites sealed for frozen-v1.

## 1. Which list does item 14 run on?

Item 14 says it runs on item 13's re-ranked list. There is none that earned that place.

- **Frozen-v1's list.** Key at 20: 8 of 32. Transplant at 20: 15 of 128.
- **The re-ranker as declared.** Key 16, transplant 11, two pieces dropped. It fails the rule.
- **The fusion (the better of the two ranks).** Key 16, transplant 21, none dropped. It was designed after the result
  was seen, so its numbers are optimistic.

Recommendation: the fusion, labelled as chosen after seeing the result, shown beside frozen-v1, and judged only by the
blind run in item 17. If you want the rule kept strictly, use frozen-v1's list.

Adopting anything here also needs the fold models replaced by one model trained on all ten sites, which has no
leave-one-site-out number of its own; only the blind run can measure it.

## 2. Do the two strips with no ground texture stay on the transplant board?

At 20, frozen-v1 finds 8 of 43 plantings on them and 7 of 85 elsewhere; the re-ranker finds 1 and 10. Taking them off
would change this comparison, and it would be doing so after seeing it, so the rule above was applied with them on. The
disk-work report already recommended counting them as not searched in item 17's completeness map. Recommendation: keep
them on this item's record as it stands, and decide for item 17 on the images' merits, reporting both numbers.

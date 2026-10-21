# Relevance Annotation Rubric

Applied uniformly across all 36 trade-off queries. Each query specifies one
**priority** aspect and one **sacrificed** aspect. Products are drawn from a
pool formed by the union of the top-8 results from every system under test.

Judgements are made from price and aspect scores only. The annotator is not
shown any system's ranking or utility value.

## Scale

| Label | Meaning |
|---|---|
| 3 | Excellent — strongly satisfies the priority aspect, no serious weakness |
| 2 | Good — solid on the priority aspect, minor weaknesses elsewhere |
| 1 | Marginal — mediocre, or a real weakness on something that matters |
| 0 | Bad — fails the priority aspect, or broken on the sacrificed one |

## Procedure

Applied in order. Later steps may only lower the label, never raise it.

### Step 1 — Priority aspect

| Priority score | Starting label |
|---|---|
| ≥ 0.80 | 3 |
| 0.60 – 0.79 | 2 |
| 0.40 – 0.59 | 1 |
| < 0.40, or no data | 0 (stop) |

A product with no review evidence for the priority aspect cannot be
recommended for it, regardless of its other scores.

### Step 2 — Sacrificed aspect

The user accepted that this aspect may be *worse*. They did not accept that
it may be *broken*.

| Sacrificed score | Adjustment |
|---|---|
| ≥ 0.35 | No change — within what the user accepted |
| 0.15 – 0.34 | Drop one level |
| < 0.15 | Drop to 0 or 1 — this is failure, not compromise |

### Step 3 — Unmentioned aspects

If any aspect the user did *not* mention scores below 0.20, drop one level.
No compromise was offered on that aspect.

## Exclusions

**Flipkart star rating is ignored.** Rating-sort is a baseline system under
test; judging by it would make that baseline unbeatable by construction.

**Price is ignored** unless grossly disproportionate to the product's
quality. Price efficiency is evaluated as a separate ranking component, not
as product quality.

## Limitation

Relevance judgements were made by a single annotator using the same aspect
scores on which the system ranks. This introduces a degree of circularity.
Independent annotation, or annotation from raw review text rather than
derived scores, would strengthen the evaluation.
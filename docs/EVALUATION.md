# Evaluation

Reproduce everything here with:

```bash
cd backend && .venv/bin/ringsentinel generate && .venv/bin/ringsentinel evaluate --from-disk
```

Seed `20260904`. Written to `artifacts/evaluation/report.json`.

## The split

Split by **account creation time**, not at random:

- **train** — accounts created on or before day 55, featurised *as of day 55*
- **test** — accounts created after day 55, featurised as of day 120

No account appears in both. No training feature can see anything after day 55.
This mirrors deployment: fit on what you knew then, score accounts you had not
met yet.

A random split scores materially better on this data and is **wrong**: graph
features leak future co-membership across the boundary, because an account's
neighbours in a random split include accounts whose labels the model trained on.

| | |
|---|---|
| Train | 7,938 accounts, 6.50% prevalence |
| Test | 6,945 accounts, 5.28% prevalence (367 ring accounts) |
| Abuse exposure in test fold | ₹13.53 L in refund claims by ring accounts |

## Headline

| Metric | Model | Rules baseline |
|---|---|---|
| Average precision | **0.978** | 0.890 |
| ROC AUC | 0.998 | — |
| Precision @ cost-optimal | 0.915 | 0.937 |
| Recall @ cost-optimal | 0.973 | 0.845 |
| F1 | 0.943 | 0.888 |
| TP / FP / FN | 357 / 33 / 10 | 310 / 21 / 57 |
| False positive rate | 0.50% | 0.32% |
| Net benefit | ₹20.34 L | ₹17.85 L |

ROC AUC is reported because reviewers expect it, but at 5% prevalence it
flatters every classifier and should not drive decisions. Average precision is
the honest headline.

Note the rules baseline has **higher precision** than the model. It achieves
this by only flagging the obvious, and pays for it with 57 misses against the
model's 10.

## The result that matters

| Evasion level | Ring accounts | Rules recall | Model recall | Δ |
|---|---|---|---|---|
| L0 naive | 32 | 1.000 | 1.000 | — |
| L1 | 36 | 1.000 | 1.000 | — |
| L2 | 47 | 1.000 | 1.000 | — |
| L3 | 36 | 1.000 | 1.000 | — |
| L4 | 47 | 1.000 | 1.000 | — |
| L5 | 36 | 1.000 | 1.000 | — |
| L6 | 40 | 0.900 | 1.000 | +0.100 |
| L7 evasive | 34 | 0.471 | 0.941 | **+0.471** |
| L8 | 27 | 0.593 | 0.889 | +0.296 |
| L9 adaptive | 32 | 0.250 | 0.844 | **+0.594** |

Against careless operators a hand-written rule set is exactly as good as the
model. The entire value of this system is concentrated in L7–L9, where the
operator partitions into disjoint cells and rotates infrastructure. Anyone
reporting only the 0.978 would be hiding the only interesting finding.

## Why evasion is not free

The most useful finding in the project. `devices_per_order` is the third most
important feature by permutation importance:

| | Ring (L9) | Legitimate |
|---|---|---|
| Devices per order | 0.90 | 0.33 |
| Cards per order | — | 0.29 |
| Claim rate | 9.3% | 3.1% |

To break graph edges, a sophisticated operator must burn a fresh device on 86%
of orders. That destroys the shared-device link — and creates a per-account
**identifier-churn signature** that is itself detectable. The evasion that
defeats the graph leaves a different trail. This is why L9 recall is 0.84
rather than the 0.19 that pure component-size analysis would predict.

## Money, not just accounts

Account counts and rupees are different questions. Catching many small abusers
while missing the large ones is a bad outcome that recall hides.

- Abuse exposure in the fold: **₹13.53 L**
- Caught at the operating point: **₹13.53 L (100%)**
- Legitimate customer value disrupted: **₹3,754**

## Choosing the threshold

Not by F1. Each candidate threshold is priced:

| Assumption | Value |
|---|---|
| Recovery per abuser caught | ₹5,920 |
| Cost of restricting a real customer | ₹2,400 |
| Manual review | ₹180 |

All three are **assumptions, not measurements** (see `MODEL_CARD.md`). The
cost-optimal threshold is 0.696.

## The shipped policy

A single threshold is not what ships. Three bands:

| Band | Accounts | Outcome |
|---|---|---|
| score ≥ 0.95 | 305 auto-actioned | precision **0.990** |
| 0.278 ≤ score < 0.95 | 172 queued to a human | ₹30,960 review cost |
| below | allowed | 7 missed entirely |

Recall including review: **0.970**. Net benefit **₹20.50 L**, above the
single-threshold ₹20.34 L — the review queue pays for itself.

On top of this, **an account that has filed no refund claim is never
auto-restricted**. Nothing to hold, no loss to prevent, and a shared card is
consistent with a household. Effect:

| | Before rule | After rule |
|---|---|---|
| Customer-visible actions on legitimate accounts | 33 | **4** |
| Precision on customer-visible actions | 87% | **98.4%** |

## Where it fails

**Every false positive is a family or a hostel resident.** Of 33 raw false
positives: 29 multi-account households, 4 hub-address residents. Zero are
isolated accounts. The system fails precisely on legitimate shared-identity
clusters, which is the irreducible core of this problem and why the policy
routes rather than restricts.

**L9 recall is 0.84, and the 16% missed are the most valuable to catch.**

**Calibration is weak in the mid-band.** The 0.3–0.5 bucket (46 accounts) has
an actual rate of 0.000 and the 0.5–0.7 bucket 0.091 — over-confident where
there are fewest training positives. The top bucket is well calibrated (0.993
actual at ≈1.0 predicted). Mid-band scores should be read as ordering, not as
probabilities.

**Prevalence is 5.3%**, at the high end of plausible for organised refund abuse.
At 1% prevalence, precision at a fixed threshold would fall materially. This is
not measured here and is the first thing to re-run against real data.

## Finding the artefacts

The benchmark went through four rounds of catching itself cheating. Each was
found by interrogating a result that looked too good.

**Round 1 — card collisions.** Tokens drawn from a 54,000-value space produced
1,484 shared cards across 11,084 cards, where only ~240 should come from real
household sharing. Unrelated accounts were fused by birthday collisions into a
331-node blob. *Fix: collision-free fingerprints.*

**Round 2 — chain-linked cells.** Ring identifiers were assigned per type by
`j % n_devices`, `j % n_addrs`. Because the groupings interleaved, every ring
resolved to one connected component regardless of evasion level, and
`component_size >= 5` alone scored **F1 0.96**. *Fix: disjoint cells that share
no infrastructure.*

**Round 3 — a cap that never bound.** The degree cap interpolated 99 → 3, but
ring sizes are 4–18, so it only constrained at L9. Levels 0–6 all collapsed to
a single cell. *Fix: an explicit schedule calibrated to actual ring sizes.*

**Round 4 — two label proxies.** Legitimate clusters signed up uniformly at
random over 102 days while rings signed up in bursts, making
`community_signup_span_days` the single most important feature by a factor of
four. And legitimate accounts never used a promotion after their first order,
making `promo_rate` near-categorical. *Fix: families and hostel intakes sign up
together; real shoppers keep redeeming promotions.*

After the fixes, permutation importance is led by genuine graph structure
(`component_size` 0.052, `graph_weighted_degree` 0.020, `devices_per_order`
0.014) and `community_signup_span_days` has left the top eight entirely.

`tests/test_no_leakage.py::test_no_feature_is_a_perfect_label_proxy` now asserts
no single feature exceeds F1 0.98 alone, so this class of bug fails the build.

## Robustness studies

Four studies address what a single backtest cannot — seed variance, feature
ablation, prevalence sensitivity and fairness. Full results in
[`STUDIES.md`](STUDIES.md). The three that change how the headline should be
read:

- **The committed seed is a good one.** Across seven populations, AP is
  0.968 ± 0.016 against this seed's 0.978. Its 33 false positives are the worst
  of the seven (mean 21).
- **Behavioural features alone reach AP 0.487** and catch 5.5% of L7–L9 rings.
  Graph features alone catch every naive ring but only 58% of sophisticated
  ones. The two halves solve different problems.
- **The neighbour features contribute nothing measurable.** Dropping all three
  gives AP 0.981 versus 0.978 with them — within seed noise. They are retained
  for explanatory value in the evidence packet, but the claim that guilt-by-
  association is a load-bearing signal was wrong: that information is already
  carried by the graph and community features.

## What is not evaluated

- **Real data.** Every number is synthetic. The generator encodes my model of
  how rings behave; a real operator will differ.
- **Concept drift.** One 120-day window, no retraining schedule.
- **Cost-assumption sensitivity.** The 2.5:1 recovery-to-false-positive ratio is
  held fixed everywhere.
- **Adaptive adversaries.** Evasion levels are static. A real operator observes
  which accounts get caught and adapts. Nothing here measures that loop.
- **Fairness across customer segments.** Not measured; see `MODEL_CARD.md`.

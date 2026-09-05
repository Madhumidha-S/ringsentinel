# Model card

## Details

| | |
|---|---|
| Model | `HistGradientBoostingClassifier`, 4-fold isotonic calibration |
| Task | Binary: is this account part of a refund/promotion abuse ring? |
| Unit | Account, scored as of a timestamp |
| Features | 41 — behavioural, identity-churn, graph, community, temporal |
| Training data | 7,938 synthetic accounts as of day 55, 6.50% prevalence |
| Seed | 20260904, fully reproducible |
| Baseline | Transparent rule set on the same graph |

## Intended use

Prioritising a human abuse-review queue for a merchant, and pausing individual
refunds pending review. It is a **triage instrument, not a verdict**.

## Out of scope

Do not use this for credit decisions, employment, insurance, law-enforcement
referral, or any customer-facing consequence beyond the bounded actions in
`THREAT_MODEL.md`. Do not use the score as evidence of fraud — it is evidence
that a human should look.

## Performance

Time-ordered held-out fold, 6,945 accounts, 5.28% prevalence:

| Metric | Model | Rules |
|---|---|---|
| Average precision | 0.978 | 0.890 |
| Precision / recall @ 0.696 | 0.915 / 0.973 | 0.937 / 0.845 |
| Net benefit | ₹20.34 L | ₹17.85 L |

Recall degrades with adversary sophistication: **1.00 at L0–L6, 0.94 at L7,
0.89 at L8, 0.84 at L9.** Report the breakdown, never the headline alone.

## Cost assumptions

Every figure below is an **assumption, not a measurement**. They are in one
place (`config.py`) so a reviewer can challenge them and re-run.

| Constant | Value | Basis |
|---|---|---|
| Recovery per abuser caught | ₹5,920 | ~3.2 fraudulent refunds × ~₹1,850 |
| Cost of restricting a real customer | ₹2,400 | Forgone contribution margin on remaining lifetime + one support contact |
| Manual review | ₹180 | ~12 minutes fully loaded |
| Reviewer accuracy | 93% | Assumed, not observed |

The 2.5:1 ratio between recovery and false-positive cost drives the operating
point. If a merchant's true ratio is 1:1, the optimal threshold rises and recall
falls. Re-run `ringsentinel evaluate` with their numbers.

## Calibration

Isotonic, 4-fold. Reliable at the top, weak in the middle:

| Predicted | n | Actual rate |
|---|---|---|
| ≈1.00 | 303 | 0.993 |
| 0.9–0.999 | 24 | 0.875 |
| 0.7–0.9 | 63 | 0.556 |
| 0.5–0.7 | 33 | 0.091 |
| 0.3–0.5 | 46 | 0.000 |

Mid-band scores should be treated as an ordering, not as probabilities. This is
a consequence of few training positives in that region.

## Failure modes

**Families and shared accommodation.** All 33 false positives are multi-account
households (29) or hub-address residents (4). A family sharing one card looks
structurally identical to a two-account ring cell. Mitigated by sufficiency
gating and the no-claims rule, not solved.

**Sophisticated rings.** 16% of L9 rings are missed, and they are the most
valuable to catch.

**Cold start.** Accounts with fewer than two orders are marked `insufficient`
and never auto-actioned. Correct, but it means a brand-new ring is invisible
until it transacts.

**Live-data degradation.** Device and IP are not exposed by the Razorpay API.
Without merchant checkout telemetry the graph is materially weaker, and worst
on the high-evasion rings. See `ARCHITECTURE.md`.

**Prevalence shift.** Evaluated at 5.3%. Precision at a fixed threshold falls if
true prevalence is 1%.

## Fairness

**Not measured, and this is a real gap.** The known failure mode has a
disparate-impact shape: the model's errors concentrate on multi-account
households and shared-address residents — hostels, PG accommodation, joint
families — which correlate with younger, lower-income and migrant customers in
India. A system that adds friction to exactly those customers is a fairness
problem, not only an accuracy one.

Before any real deployment: measure action rates by address type, household
size, city tier and account age, and set a ceiling on customer-visible actions
against shared-address cohorts.

## Ethical considerations

Every customer-visible action is reversible, and every high-severity one
requires human confirmation. The system is designed so the expensive error
(restricting a real customer) is structurally harder to make than the cheap one
(queuing an alert nobody needed). That is a deliberate asymmetry and it costs
measured recall.

## Maintenance

Retrain when prevalence, product mix or promotion structure shifts. Watch the
per-level recall table rather than the headline: a ring population that grows
more sophisticated shows up there first, and in the headline last.

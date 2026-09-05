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
| Average precision (7 seeds) | **0.968 ± 0.016** | 0.855 ± 0.029 |
| Average precision (committed seed) | 0.978 | 0.890 |
| Precision / recall @ 0.696 | 0.915 / 0.973 | 0.937 / 0.845 |
| Net benefit | ₹20.34 L | ₹17.85 L |

Precision is quoted at 5.3% prevalence. At 1% it falls to **0.660**; see
[`STUDIES.md`](STUDIES.md).

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

**Prevalence shift.** Evaluated at 5.3%. Measured: precision falls to 0.660 at
1% prevalence with recall unchanged — roughly one flag in three would be wrong.

## Fairness

**Measured.** Among legitimate accounts only, on the held-out fold:

| Cohort | Legitimate accounts | Restricted | Rate | Queued for review |
|---|---|---|---|---|
| solo | 4,406 | 0 | 0.000% | 0 (0.00%) |
| household | 1,444 | 4 | 0.277% | 88 (6.09%) |
| hub (hostel/PG/office) | 728 | 0 | 0.000% | 8 (1.10%) |

**No solo shopper is ever restricted or queued.** The disparate-impact ratio
against that reference group is therefore *undefined*, not merely large — a
stronger result than any finite ratio. Every wrongly restricted customer lives
in a multi-account household; households are 22% of the legitimate population
and absorb **100% of restrictions and 92% of all flags**.

This has a real-world shape: multi-account households and shared addresses in
India correlate with joint families, migrant workers, students in PG
accommodation and lower-income shared housing. A system that spends its entire
error budget on those customers is a fairness problem, not only an accuracy one,
and it is invisible to anyone reporting only precision and recall.

The absolute harm is small (four customers, 0.277%) because the no-claims rule
and evidence gating divert most household flags into the invisible review queue.
The 6.09% household review rate is the true cost, and analysts bear it rather
than customers.

**Before deployment:** cap customer-visible actions against shared-address
cohorts; require a second reviewer for any restriction on a household account;
and monitor this table continuously, since it drifts as the ring population
changes. Also measure by city tier and account age, which this study does not
cover. See [`STUDIES.md`](STUDIES.md).

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

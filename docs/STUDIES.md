# Robustness studies

Four questions the headline backtest cannot answer. Reproduce all of them with:

```bash
cd backend && .venv/bin/ringsentinel study
```

Written to `artifacts/evaluation/studies.json`. Runtime ~4 minutes.

---

## 1. Is 0.978 real, or one lucky seed?

Every headline in this repository originally came from a single generated
population. That is the easiest attack on a synthetic benchmark, so: seven
independently generated populations, full pipeline on each.

| Metric | Mean | SD | Range |
|---|---|---|---|
| Test prevalence | 0.0499 | 0.0055 | 0.043 – 0.057 |
| **Model average precision** | **0.968** | 0.016 | 0.935 – 0.982 |
| Rules average precision | 0.855 | 0.029 | 0.814 – 0.890 |
| Precision @ cost-optimal | 0.940 | 0.029 | 0.900 – 0.976 |
| Recall @ cost-optimal | 0.945 | 0.023 | 0.908 – 0.973 |
| False positives | 21.3 | 10.6 | 8 – 33 |
| Recall L0–L6 | 0.992 | 0.010 | 0.973 – 1.000 |
| **Recall L7–L9 (model)** | **0.832** | 0.059 | 0.720 – 0.891 |
| **Recall L7–L9 (rules)** | **0.358** | 0.099 | 0.211 – 0.465 |

**The seed I originally reported was a good one.** Its AP of 0.978 sits near the
top of the range against a mean of 0.968; the honest headline is **0.968 ±
0.016**. Its 33 false positives, on the other hand, were the *worst* of the
seven — the mean is 21.

**The central claim survives comfortably.** The model beats the rules baseline
on L7–L9 by 0.47 on average, and the two distributions do not overlap: the
model's worst seed (0.720) is well above the rules' best (0.465).

---

## 2. Is the graph earning its keep?

The question any reviewer should ask: would ordinary per-account behavioural
features get you to the same place, making the entire graph layer decoration?

Same population, same model, trained on subsets of the feature families.

| Feature set | Features | AP | Recall L0–L6 | **Recall L7–L9** |
|---|---|---|---|---|
| behavioural only | 15 | 0.487 | 0.436 | **0.055** |
| behavioural + temporal | 19 | 0.635 | 0.589 | 0.128 |
| behavioural + churn | 22 | 0.810 | 0.735 | 0.829 |
| no graph | 26 | 0.897 | 0.895 | 0.831 |
| graph only | 15 | 0.943 | **1.000** | 0.581 |
| no neighbour | 38 | 0.981 | 1.000 | 0.901 |
| **all** | 41 | 0.978 | 1.000 | 0.891 |

Three findings.

**Per-account behaviour alone is close to useless against real rings.** Fifteen
behavioural features get AP 0.487 and catch **5.5%** of sophisticated rings. The
answer to "would simple features do this?" is an emphatic no.

**The graph and the churn features solve different halves of the problem.**
Graph features alone catch *every* naive ring (1.000 on L0–L6) but only 58% of
sophisticated ones — because sophisticated rings are precisely the ones that
break graph edges. Identity-churn features are the reverse: adding them to
behavioural features lifts L7–L9 recall from 0.055 to 0.829, because rotating
infrastructure to escape the graph is itself a signature. Neither half is
sufficient; the combination is what wins.

**The neighbour features contribute nothing measurable, and I was wrong about
them.** Dropping all three "guilt by association" features gives AP 0.981
against 0.978 with them — *better*, though well inside the ±0.016 seed noise, so
the honest reading is "no measurable contribution". I had earlier highlighted
these as the top signal on the basis of a univariate effect size; permutation
importance and now ablation both say the information is already carried by the
graph and community features. They are retained because they cost nothing and
carry real explanatory value in the evidence packet, but they should not be
described as load-bearing.

---

## 3. What happens at realistic prevalence?

The benchmark runs at 5.3% prevalence, which is at the top of plausible for
organised refund abuse. To isolate the prevalence effect from retraining noise,
the model and threshold are held fixed and the held-out fold is resampled to
each target rate (300 bootstraps).

| Prevalence | Positives | Precision | 95% CI | Recall |
|---|---|---|---|---|
| 1.0% | 66 | **0.660** | [0.653, 0.667] | 0.973 |
| 2.0% | 134 | 0.798 | [0.794, 0.801] | 0.973 |
| 3.0% | 203 | 0.857 | [0.855, 0.859] | 0.972 |
| 4.0% | 274 | 0.890 | [0.889, 0.891] | 0.973 |
| 5.3% | 367 | 0.915 | [0.915, 0.915] | 0.973 |

Recall is invariant, as it must be — subsampling positives does not change what
fraction of them you catch. Precision degrades steeply: **at 1% prevalence,
one flag in three is wrong.**

This is a material caveat and it was worth measuring rather than hand-waving. If
a merchant's true organised-abuse rate is nearer 1%, the threshold must be
raised and the review queue will carry more of the load. The banded policy
already absorbs this — the auto-action band sits at 0.95, far above the
cost-optimal 0.696 — but the headline precision figure should not be quoted at
a prevalence a merchant does not have.

---

## 4. Who gets hurt when we are wrong?

The accuracy numbers say the model is right 91.5% of the time. They say nothing
about *who* absorbs the other 8.5%. Among **legitimate accounts only**:

| Cohort | Legitimate accounts | Restricted | Restriction rate | Queued for review | Share of all restrictions |
|---|---|---|---|---|---|
| solo | 4,406 | **0** | 0.000% | 0 | 0% |
| household | 1,444 | **4** | 0.277% | 88 (6.09%) | **100%** |
| hub (hostel/PG/office) | 728 | 0 | 0.000% | 8 (1.10%) | 0% |

**No solo shopper is ever restricted or even queued.** The disparate-impact
ratio against the solo reference group is not large — it is *undefined*, because
the reference rate is exactly zero. That is a stronger finding than any finite
ratio.

Every wrongly restricted customer lives in a multi-account household.
Households are 22% of the legitimate population and absorb **100% of the
restrictions and 92% of all flags**.

This has a real-world shape. In India, multi-account households and shared
addresses correlate with joint families, migrant workers, students in PG
accommodation and lower-income shared housing. A system whose entire error
budget is spent on those customers is a fairness problem, not merely an accuracy
one — and it would be invisible to anyone reporting only precision and recall.

**What limits the harm today.** The absolute rate is low (0.277%, four
customers), because the no-claims rule and evidence sufficiency gating divert
most household flags into the invisible review queue rather than a restriction.
The 6.09% household review rate is the real cost, and it is borne by analysts,
not customers.

**What should happen before deployment.** Set an explicit ceiling on
customer-visible actions against shared-address cohorts; require a second
reviewer for any restriction on a household account; and monitor this table
continuously, because it will drift as the ring population changes.

---

## What these studies still do not cover

- **Adaptive adversaries.** Evasion levels are static. A real operator observes
  which accounts get caught and adapts; nothing here measures that loop, and it
  remains the largest single gap.
- **Real data.** All four studies run on synthetic populations.
- **Cost-assumption sensitivity.** The 2.5:1 ratio between recovery and
  false-positive cost is held fixed throughout.

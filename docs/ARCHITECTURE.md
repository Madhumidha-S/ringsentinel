# Architecture

## The problem, precisely

Refund and promotion abuse at scale is not committed by individuals. One
operator runs many accounts, spreads claims thinly across them so no single
account looks abnormal, and cashes out through refunds and first-order
promotions. Per-account scoring is structurally blind to this: each account
looks like a slightly unlucky customer.

So the unit of detection is the **ring**, and the core question is not "is this
account bad?" but **"how much evidence is there that these accounts are one
hand?"**

## Data flow

```
 Razorpay test-mode API ─┐
                         ├─→ normalise ─→ identity graph ─→ features ─→ model ─→ score
 synthetic generator ────┘   (email,       (weighted,       (as-of      (GBDT +
                              address)      degree-          cutoff)     isotonic)
                                            discounted)                      │
                                                                             ▼
                                                            evidence packet ─→ sufficiency
                                                                             │
                                                       ┌─────────────────────┤
                                                       ▼                     ▼
                                            bounded action          hash-chained ledger
                                        (allow/monitor/review/         (append-only,
                                         step-up/hold refund)           verifiable)
```

## 1. Normalisation

Identifiers become graph edges only after canonicalisation. Gmail dot and
`+tag` variants collapse to one inbox — the cheapest form of multi-accounting
dies here. Addresses are canonicalised for case, punctuation, abbreviations and
city aliases (Bengaluru/Bangalore).

Address normalisation is **deliberately imperfect**. It survives cosmetic
variation and fails on unit-number drift and token reordering, which is roughly
where a good heuristic matcher actually sits. In the benchmark, 34% of jittered
addresses still link after normalisation. A perfect normaliser would make the
graph perfect and the problem disappear.

## 2. The identity graph

Accounts connect to identifiers (inbox, phone, device, card, shipping address,
egress IP); we project that bipartite graph onto accounts. Edge weight answers
"how much evidence that these two are one hand?" and combines two terms:

**Prior by identifier type** — how much identity a shared value implies:

| Identifier | Prior | Reasoning |
|---|---|---|
| `email_norm` | 1.00 | Same inbox is near-proof |
| `phone` | 0.95 | Rarely shared between unrelated people |
| `device_id` | 0.85 | Strong, but households share laptops |
| `card_token` | 0.80 | Strong, but families share a card constantly |
| `ship_address_norm` | 0.55 | Families, offices, hostels all share |
| `ip` | 0.20 | Campus/office/CGNAT — nearly worthless alone |

**Inverse degree** — an identifier used by exactly two accounts is far stronger
evidence than one used by fifty. Contribution is `prior / (degree - 1)`, so a
two-account device contributes 1.0 and a fifty-account device 0.02.

This is what stops shared infrastructure from fusing the population into one
component. In the benchmark it discounts 8–35-resident hostel addresses to
below the edge threshold automatically, without a hand-written hostel rule.
Identifiers touching more than 120 accounts are dropped entirely as
infrastructure rather than identity.

Communities come from weighted Louvain **within** each connected component.
Components alone are too coarse: one slipped device links two otherwise
separate cells. In the benchmark, communities of size ≥3 come out 98 pure-ring
and 313 pure-legitimate with zero mixed.

## 3. Features, computed as of a cutoff

41 features in five families: behavioural, identity-churn, graph, community and
temporal. Two design points matter.

**Guilt by association uses behaviour, never labels.** We aggregate what an
account's graph neighbours *do* — their claim rates, their claim volume — never
their labels.

Ablation shows these three features contribute **nothing measurable** to
accuracy: removing them changes AP from 0.978 to 0.981, inside the ±0.016 seed
noise. The information is already carried by the graph and community features.
They are kept because they make the evidence packet legible to a human reviewer,
not because they are load-bearing. See `STUDIES.md`.

**Everything is computed as of a timestamp.** Accounts created after the cutoff
are excluded; later orders and claims are invisible; the graph is rebuilt from
the truncated history. See `EVALUATION.md`.

## 4. Model

`HistGradientBoostingClassifier` with 4-fold isotonic calibration. Deliberately
boring — the contribution here is the graph features and the evaluation
discipline, not the estimator.

Calibration is not cosmetic: every downstream decision is a rupee threshold, so
`p = 0.3` has to mean 30%. Measured on the held-out fold, the top isotonic bin
(303 accounts scoring ≈1.0) has an actual abuse rate of 0.993.

A **transparent rule baseline** using the same graph runs alongside every
evaluation. If the model cannot beat a good hand-written rule set, it does not
deserve to ship.

## 5. Evidence and sufficiency

Every alert carries peers, the identifier type binding each (values redacted to
a 10-char hash — a reviewer needs to know two accounts share a card, not what
the card is), behavioural facts, and contributing factors versus the
population baseline.

The packet also carries a **sufficiency verdict** — `strong`, `moderate`,
`weak`, `insufficient` — which gates the action independently of the score.
Links via shared address or IP alone are consistent with a household and
downgrade to `weak` no matter how confident the model is.

## 6. Narration

An LLM renders the packet into prose under three constraints: it sees only the
packet; every account id and identifier reference in the output is checked
against the packet's citable set and the narration is **rejected** if it invents
one; and if the key is absent, the call fails or validation rejects, a
deterministic template built from the same evidence is used. The product
degrades to "less fluent", never to "unavailable" or to plausible fiction.

The narration is a rendering of the evidence, never itself evidence. The action
is chosen before it runs and does not depend on it.

## 7. Bounded actions and the ledger

Actions are a fixed enum, ordered by severity, each with a declared reversal.
Nothing can move money. The most severe automatic action pauses one pending
refund for 72h. `close_account`, `seize_funds`, `blocklist_identifier` and
`report_to_authority` are explicitly prohibited, enforced by test.

Every score, action and human override is appended to a hash-chained ledger
before it takes effect. `verify()` re-derives the chain and reports the exact
index where any tampering occurred.

## Live Razorpay data: what degrades

The adapter maps payments → orders, refunds → claims, customers → accounts.
Amounts convert from paise once, at the boundary. Two of our strongest signals
are **not available** from the API:

| Signal | Status | Consequence |
|---|---|---|
| `device_id` | Not in API | Needs merchant checkout telemetry joined on `order_id` |
| `ip` | Not in API | Same |
| `card_token` | Available (`card_id`) | Strong link preserved |
| `claim_type` | Usually absent | The item-not-received feature weakens |

Without device and IP, the graph forms fewer edges and recall drops hardest on
exactly the high-evasion rings that rotate infrastructure — the rings the model
is most valuable against. We state this rather than hide it; the honest
deployment path is to ship a fingerprinting SDK on the storefront first.

## Component map

| Path | Responsibility |
|---|---|
| `simulator/` | Adversarial population generator, evasion profiles |
| `graph/build.py` | Identity graph construction and weighting |
| `graph/communities.py` | Weighted Louvain within components |
| `graph/features.py` | Leakage-free featurisation |
| `detect/model.py` | Calibrated GBDT |
| `detect/rules.py` | Transparent baseline |
| `evaluation/replay.py` | Time-ordered backtest |
| `evaluation/cost.py` | Rupee cost curve, banded policy |
| `agent/evidence.py` | Evidence packets, sufficiency |
| `agent/narrate.py` | Grounded narration with validation |
| `agent/actions.py` | Bounded action policy |
| `ledger/ledger.py` | Hash-chained audit log |
| `ingest/razorpay.py` | Test-mode API adapter |
| `api/` | FastAPI service |

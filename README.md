# RingSentinel

**Abuse-ring detection for merchant refund and promotion fraud.**
Razorpay AI Buildathon — Track 2, AI Risk Manager. Defence-only.

Organised abuse does not look like one bad customer. It looks like eleven
accounts that share a device, ship to three flats in the same building, and
each file one item-not-received claim a month. RingSentinel finds the ring
rather than the account, prices the decision in rupees, and refuses to act when
the evidence will not carry it.

---

## Headline result

Measured on a **time-ordered held-out fold**: trained on accounts known at day
55, scored on 6,945 accounts first seen *after* that cutoff (5.28% prevalence).

| | Model | Rules baseline |
|---|---|---|
| Average precision | **0.978** | 0.890 |
| Precision @ cost-optimal | **0.915** | 0.937 |
| Recall @ cost-optimal | **0.973** | 0.845 |
| False positives | 33 | 21 |
| Net benefit | **₹20.3 L** | ₹17.8 L |

The overall numbers are the least interesting part. This is the result that matters:

| Adversary | L0–L6 (naive → evasive) | L7 | L8 | L9 (adaptive) |
|---|---|---|---|---|
| Rules baseline recall | 1.00 – 0.90 | 0.47 | 0.59 | **0.25** |
| Model recall | 1.00 | 0.94 | 0.89 | **0.84** |

A hand-written rule set is *indistinguishable from the model* against careless
rings, and collapses to 25% against a disciplined operator. Every rupee of the
model's advantage is earned against adversaries who partition into cells and
rotate infrastructure. Reporting only the headline would have hidden that
completely.

**After the action policy**, of 245 customer-visible actions, **4 land on
legitimate customers** (98.4% precision on anything a customer actually feels).

---

## Why this is not another fraud demo

**1. The benchmark is adversarial, and it fought back.**
The generator has a tunable evasion level (0–9) controlling device/card/IP
rotation, address obfuscation, signup-burst spreading, sub-ring cell splitting,
dormancy and cover-order ratio. Rings from all ten levels coexist in one
population, so recall is reported per level.

Building it honestly took four rounds of finding my own dataset cheating:

| Artefact found | Effect before fix | Fix |
|---|---|---|
| Card tokens drawn from a 54,000-value space | 1,484 accidental shared cards fabricating graph edges | Collision-free fingerprints |
| Ring identifiers assigned by `j % n` per type | Cells chain-linked; every ring one component; naive rule scored **F1 0.96** | Disjoint cells |
| Degree cap interpolated 99→3 | Cap never bound below L9 | Explicit schedule calibrated to ring size |
| Legit clusters signed up uniformly at random | `community_signup_span` alone nearly separated the classes | Families and hostels sign up together |
| Legit accounts never used a promo after order #1 | `promo_rate` a categorical label | Real shoppers keep redeeming |

`tests/test_no_leakage.py` now asserts that **no single feature achieves F1 >
0.98** on its own, so this class of bug fails the build rather than inflating a
slide.

**2. Legitimate people share identifiers, and it costs us.**
22% of the population lives in multi-account households; 11% ship to hostel, PG
or office hub addresses carrying 8–35 unrelated residents; 35% sit behind shared
egress IPs. Every one of the model's 33 false positives is a family (29) or a
hostel resident (4). That is the real problem, so it is in the benchmark.

**3. Evaluation is leakage-free by construction.**
Features are computed *as of* a cutoff; accounts created later are invisible and
so is every later event. `test_features_are_invariant_to_future_data` asserts
the frame is byte-identical whether or not future rows are present. A random
split scores better and is wrong.

**4. Decisions are priced in rupees, not F1.**
Catching an abuser recovers ~₹5,920; wrongly restricting a customer costs
~₹2,400 in forgone lifetime value and support. The threshold is the peak of that
curve. Every constant is declared in `config.py` and is an assumption, not a
measurement.

**5. Evidence gates the action, separately from the score.**
A confident score on thin evidence is routed to a human, not executed. And an
account that has **filed no refund claim is never auto-restricted** — there is
nothing to hold and no loss to prevent, and a shared card is consistent with a
household. That one rule cut customer-visible false positives from 33 to 4.

**6. Every decision is hash-chained.**
Append-only ledger; each entry carries its predecessor's hash. `verify()`
reports the exact index where any tampering occurred.

---

## Quick start

```bash
cd backend && uv venv && uv pip install -e ".[dev]"
```

```bash
cd backend && .venv/bin/ringsentinel generate && .venv/bin/ringsentinel evaluate --from-disk
```

Run the dashboard (API on :8000, UI on :3100):

```bash
cd backend && .venv/bin/python -m uvicorn ringsentinel.api.main:app --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Tests:

```bash
cd backend && .venv/bin/pytest tests/ -q && .venv/bin/ruff check .
```

---

## Documentation

| Document | What it covers |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design, graph weighting, data flow, live-data degradation |
| [`docs/EVALUATION.md`](docs/EVALUATION.md) | Full results, the artefact hunt, what the numbers do not show |
| [`docs/MODEL_CARD.md`](docs/MODEL_CARD.md) | Intended use, failure modes, cost assumptions, fairness |
| [`docs/DATA_CARD.md`](docs/DATA_CARD.md) | Generator design, evasion profiles, known unrealism |
| [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) | Defence-only posture, abuse surface, what is out of scope |

## Defence-only

This system detects, explains and escalates. It has **no capability to move
funds, close accounts, blocklist identifiers or contact customers**. The most
severe automatic action pauses one pending refund for review and is reversible
in one call. The prohibited-action list is enforced in code
(`test_no_action_can_move_money_or_be_irreversible`) rather than promised in
prose. The data generator produces evaluation fixtures only; it models evasion
in order to measure detection against it, and contains nothing that would help
execute abuse against a real merchant.

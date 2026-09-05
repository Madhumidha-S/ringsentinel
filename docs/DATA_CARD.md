# Data card

All data is **synthetic**. No real customer, merchant or payment data is used
anywhere in this repository.

## Why synthetic, and why that is a risk

Track 2 provides no dataset, and real abuse-ring data is not obtainable. So the
generator is not a convenience — it is the load-bearing artefact, and if it is
naive every metric downstream is theatre. This card documents what it models,
what it deliberately makes hard, and where it is still unrealistic.

## Shape

Seed `20260904`, 120-day horizon.

| | |
|---|---|
| Accounts | 14,883 |
| Ring accounts | 883 (**5.9%**) |
| Orders | 81,124 |
| Claims | 4,385 |
| Refunds granted | ₹66.79 L |
| Of which to ring accounts | ₹31.03 L (46.5%) |

### Population

| Cohort | Share | Behaviour |
|---|---|---|
| `solo` | 4,690 | Independent shoppers |
| `household` | 1,540 (22%) | 2–4 accounts sharing an address; 55% share a card; 35% share a device; signups cluster within ~8 days |
| `hub` | 770 (11%) | 8–35 unrelated residents of a hostel/PG/office sharing one address; 80% behind one wifi egress; 10% share a roommate's device; signups cluster within ~15 days |
| `ring` | 883 | Abuse rings, evasion levels 0–9 |

35% of legitimate accounts sit behind shared egress IP pools (campus, office,
CGNAT), which is what makes the IP edge weak by construction.

**The legitimate co-sharing is the point.** Without households and hubs, ring
detection collapses to "find any shared identifier" and every score is
inflated. With them, a family sharing a card is structurally indistinguishable
from a two-account ring cell — which is the real problem.

## Adversary model

Rings from all ten evasion levels coexist in one population, roughly 40 accounts
per level in the test fold, so recall is reported per level. Level parameters
interpolate between two anchors:

| Parameter | L0 naive | L9 adaptive |
|---|---|---|
| Device rotation | 0.02 | 0.86 |
| IP rotation | 0.05 | 0.94 |
| Card rotation | 0.03 | 0.72 |
| Address jitter | 0.00 | 0.80 |
| Signup spread | 0.08 d | 21 d |
| Cell size cap | 99 | 2 |
| Dormancy | 0.5 d | 16 d |
| Cover-order ratio | 0.05 | 0.70 |
| Claim rate | 0.88 | 0.34 |
| Operational slippage | 0.12 | 0.015 |

**Cells.** A disciplined operator partitions the ring into disjoint cells; each
cell's device, card and drop address are its own and are shared with no other
cell. A ring of 18 at L9 becomes nine cells of two, each of which looks like a
couple sharing a card.

**Slippage** is what makes a well-run ring detectable at all: occasionally an
account is touched from another cell's device. Careless operators leak
constantly; disciplined ones rarely.

Realised difficulty gradient:

| Level | Claim rate | Max accounts per device |
|---|---|---|
| Legit | 3.8% | — |
| L0 | 82% | 17 |
| L5 | 34% | 15 |
| L9 | **7.9%** | **2** |

At L9 a ring account claims at roughly twice the legitimate rate and shares a
device with one other account. That is genuinely hard, and it is why L9 recall
is 0.84 rather than 1.00.

## Identifier realism

- **Email.** Normalisation collapses Gmail dot/`+tag` variants. Low-evasion
  rings farm one inbox this way and die to normalisation; high-evasion rings use
  unrelated disposable inboxes.
- **Address.** Jitter mixes cosmetic mutations (abbreviations, city aliases,
  punctuation) that normalisation survives with structural ones (unit-number
  drift, token reordering, pincode transposition) that defeat it. Measured: 34%
  of jittered addresses still link.
- **Card.** Collision-free fingerprints. An earlier version used BIN + last4
  only — a 54,000-value space — which produced ~1,200 accidental shared cards
  and fabricated graph edges between unrelated accounts.
- **Device.** SHA-256 of a random 62-bit value; collision-free.

## Labels

`label_is_ring`, `label_ring_id`, `label_evasion_level`, `cohort`. All are
dropped before featurisation and asserted absent by
`tests/test_no_leakage.py::test_no_label_column_reaches_the_model`.

## Known unrealism

Stated plainly, because these are the things that would make the reported
numbers optimistic.

1. **Prevalence of 5.9% is high.** Convenient for measurement, at the top of
   plausible for organised refund abuse. Precision at a fixed threshold would
   fall at 1%.
2. **Ring behaviour is stationary.** Each ring picks an evasion level and keeps
   it. Real operators adapt *after* observing which accounts get caught. Nothing
   here measures that feedback loop, and it is the largest single gap.
3. **Claim outcomes are independent draws.** No dispute negotiation, no partial
   refunds, no merchant-side investigation changing later behaviour.
4. **One product category, one currency, no seasonality.** No festive spikes,
   which are exactly when promotion abuse peaks in India.
5. **Households and hubs are the only legitimate clusters.** Real merchants also
   see resellers, corporate buyers and social-commerce sellers — high-volume,
   many-address, entirely legitimate patterns that would be new false-positive
   sources.
6. **Order amounts are lognormal** rather than drawn from a real catalogue.
7. **Every account is reachable.** No bot traffic, no failed payments, no
   partial checkouts.

## Live data

`ingest/razorpay.py` maps Razorpay test-mode payments, refunds and customers
into this schema. Device fingerprint and IP are **not available** from the API
and must come from merchant checkout telemetry; the field mapping and the
resulting degradation are documented in `ARCHITECTURE.md`.

## Regenerate

```bash
cd backend && .venv/bin/ringsentinel generate --seed 20260904
```

Writes `artifacts/dataset/{accounts,orders,claims}.csv` and `meta.json`.

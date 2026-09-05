# RingSentinel — 5-minute pitch script

**~780 spoken words. At a measured pace with pauses for screen actions, this lands at 4:50–5:10.**
Bold = say with emphasis. `[BRACKETS]` = what's on screen, don't read aloud.

---

## [0:00–0:32] Cold open

`[SCREEN: a plain table of refund claims — boring, nothing flagged]`

Here's a merchant's refund report. Nothing looks wrong. Every account has one
or two claims. Normal rates. Nothing trips a threshold.

`[SCREEN: switch to the evidence graph — the cluster snaps into view]`

Here's the same data as a graph. Eleven of those accounts share four devices,
ship to three flats in one building, and were created within the same nine
minutes.

That's not eleven unlucky customers. That's **one person**, and they've taken
three lakh rupees in refunds.

Per-account fraud scoring is structurally blind to this. So RingSentinel
doesn't score accounts. It scores a different question: **how much evidence is
there that these accounts are one hand?**

---

## [0:32–1:10] The trap

`[SCREEN: the track page, then your terminal]`

Track 2 gives you no dataset. So most submissions will generate a synthetic
CSV, train XGBoost, report 0.99 AUC, and wrap it in a dashboard.

I know that, because that's exactly what my first version did.

It scored **F1 0.96** — from a one-line rule. `component_size >= 5`.

The model wasn't good. The benchmark was rigged. And it was rigged by me, by
accident, **four separate times**.

---

## [1:10–2:12] The artifact hunt

`[SCREEN: the artifact table in EVALUATION.md, scrolling slowly]`

Round one. My card tokens came from a fifty-four-thousand-value space. Eleven
thousand cards — birthday collisions. Fourteen hundred unrelated accounts fused
by pure chance into one 331-node blob.

Round two. I assigned ring identifiers with `j mod n_devices`. Because the
device and address groupings interleaved, every ring chain-linked into a single
component no matter how careful the operator was. Sub-ring splitting — the
thing sophisticated fraudsters actually do — did nothing at all.

Round three. My degree cap interpolated from 99 down to 3. But rings are four
to eighteen accounts, so the cap only ever bound at level nine.

Round four, and this is the worst one. My legitimate families signed up at
uniformly random times across a hundred days, while rings signed up in bursts.
So signup-span alone nearly separated the classes. And my legitimate accounts
never used a promo code after their first order — which made promo rate a
near-categorical label.

Every one of those I found by **refusing to believe a good number**.

`[SCREEN: the test file]`

There's now a test that fails the build if any single feature scores F1 above
0.98 on its own.

---

## [2:12–3:00] The system

`[SCREEN: evasion profile table]`

The benchmark has ten adversary levels. Level zero puts seventeen accounts on
one device. Level nine partitions into disjoint cells of two, burns a fresh
device on eighty-six percent of orders, waits sixteen days before extracting,
and hides claims behind cover purchases.

And critically — **legitimate people share identifiers too**. Twenty-two
percent of my population is multi-account households. Eleven percent ship to
hostels and PGs: eight to thirty-five unrelated residents on one address, which
in India is completely normal.

`[SCREEN: the graph weighting table in ARCHITECTURE.md]`

So the graph weights every shared identifier by type and by inverse degree. A
device shared by two accounts contributes 1.0. Shared by fifty, it contributes
0.02. That discounts hostel addresses automatically — with no hand-written
hostel rule anywhere.

---

## [3:00–3:52] Results

`[SCREEN: the dashboard, KPI row]`

Trained on accounts known at day 55. Scored on 6,945 accounts I had never seen.
Average precision **0.978**, against 0.890 for a genuinely good hand-written
baseline.

`[SCREEN: the recall-by-evasion-level chart — hold here]`

But that comparison is the whole point. Look at recall by adversary level.
Against levels zero through six, the rules are **exactly as good as the model**.
Identical. Against level nine — rules catch twenty-five percent. The model
catches eighty-four.

Every rupee of value is in the last three columns. If I'd reported only the
headline, you would never have seen that.

And here's what I didn't expect. To break my graph, a sophisticated ring has to
burn a fresh device on nearly every order. That destroys the device link — and
creates an **identifier-churn signature** that is now my third most important
feature. Evasion isn't free. It just moves the trail.

---

## [3:52–4:38] Where it fails

`[SCREEN: false positive breakdown]`

Now — where it fails. All thirty-three false positives are families and hostel
residents sharing a payment instrument. A family with one shared card is
structurally identical to a two-account ring cell. That is irreducible.

So the score doesn't decide the action. **Evidence does.** Plus one rule: an
account that has filed no refund claim is never auto-restricted. There's
nothing to hold, and no loss to prevent.

`[SCREEN: the customer-visible KPI]`

That took customers wrongly restricted from thirty-three down to **four**. Model
precision is 91.5 percent. Precision on anything a customer actually feels is
**98.4**.

---

## [4:38–5:05] Close

`[SCREEN: ledger verify output, then tamper → chain breaks]`

Every decision is hash-chained. Tamper with one entry and verify names the exact
index. Every action is bounded and reversible — nothing here can move money,
close an account, or blocklist an identifier. That's enforced by test, not by a
promise in a README.

Thirty-four hundred lines, thirty-seven tests, reproducible from a seed.

`[SCREEN: back to the level-9 bar]`

The number I'd defend isn't 0.978. It's **0.84 at level nine** — and the fact
that I can tell you exactly where the other sixteen percent went.

---

## Delivery notes

- **Slow down on the artifact section.** It's the differentiator and it's dense.
  If you run long, cut round three (the degree cap) — it's the weakest of the four.
- **Hold on the recall chart for a full three seconds** before speaking. Let the
  L7–L9 gap land visually before you explain it.
- Don't apologise anywhere. The failure modes are stated as findings, not
  confessions — that tone is the point.
- If you need 20 seconds back: cut "Round three" and the "thirty-four hundred
  lines" sentence.

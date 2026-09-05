# RingSentinel — 3-minute pitch script

**Talking to camera. No screen recording, no slides — just you.**
~470 words. At a natural pace with pauses, this lands at **3:00–3:10**.

Bold = land these words. `/` = breathe here.

---

### The problem  ·  ~30s

A merchant's refund report looks clean. Every account has one or two claims.
Nothing trips a threshold. /

But eleven of those accounts share four devices, ship to three flats in the
same building, and were created within nine minutes of each other. /

That's not eleven unlucky customers. That's **one person** — and they've taken
three lakh rupees.

So my system doesn't score accounts. It asks: **how much evidence is there that
these accounts are one hand?**

---

### The trap  ·  ~35s

Track 2 gives you no data. So most people will generate fake data, train a model,
report ninety-nine percent, and call it done. /

My first version did exactly that. It scored an F1 of **0.96** — until I found
that a single one-line rule scored the same thing.

The model wasn't good. My benchmark was rigged — and I'd rigged it myself, by
accident, **four separate times**. /

I found all four by refusing to believe a good number. There's now a test that
**fails the build** if any one feature is too predictive.

---

### The result  ·  ~65s

Once it was honest, here's what it showed. /

I built ten levels of attacker. Level zero is careless. Level nine splits into
pairs, uses a fresh device almost every order, and waits sixteen days before
cashing out.

And innocent people share things too. A hostel address in India has thirty
unrelated residents on it. A family shares one card. That's the hard part — it
looks **identical** to a ring. /

Against careless attackers, a hand-written rule is exactly as good as my model.
Identical.

Against the disciplined ones — the rule catches about **a third**. Mine catches
over **eighty percent**. That gap is the entire product. /

One thing surprised me. To break my graph, a ring has to burn a new device almost
every order. But that *itself* is a pattern — now one of my strongest signals.
**Evasion isn't free. It just moves the trail.**

---

### Where it fails, and the close  ·  ~55s

Every false positive I have is a family or a hostel resident sharing a card.
That's irreducible. /

So I measured **who gets hurt when I'm wrong**. And the answer is
uncomfortable. A solo shopper in my data is *never* restricted — not once.
**Every single** wrongly-restricted customer lives in a shared household. In
India, that's joint families and students in PGs. /

So the score doesn't decide the action — the **evidence** does. Plus one rule:
an account that has never filed a claim is never restricted. Nothing to hold, no
loss to prevent.

That took wrongly-restricted customers from thirty-three down to **four**. /

Every decision is hash-chained and reversible. Nothing here can move money —
enforced by a test, not a promise. /

The number I'd defend isn't the headline. It's **eighty percent against the
hardest attacker** — and the fact that I can tell you exactly where the rest
went.

---

## Delivery notes

- **Only three numbers matter:** 0.96 · a-third vs eighty-percent · thirty-three
  to four. Don't reach for more figures on camera.
- Strongest moment: "**I'd rigged it myself, four separate times.**" Pause
  before it. Nobody else will say anything like that.
- Second strongest: the fairness beat. Almost nobody measures who absorbs their
  false positives. Slow right down on "*never* restricted — not once."
- Say the failure modes as **findings, not confessions**. Same words, different
  posture — that's the whole tone.
- **If you run short**, add either of these — both are true and both land:
  *"And that's not one lucky run — seven separate populations. My worst run still
  beats the rule's best run."* or *"Behavioural features alone catch five percent
  of the hard rings. The graph is doing the work."*

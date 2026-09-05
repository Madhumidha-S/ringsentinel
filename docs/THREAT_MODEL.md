# Threat model and defence-only posture

## Posture

RingSentinel **detects, explains and escalates**. It has no capability to move
funds, close accounts, blocklist identifiers, or contact customers. Track 2
disqualifies anything offence-capable; this document states plainly what the
system can and cannot do, and the boundary is enforced by tests rather than
promised in prose.

## What it defends against

Organised refund and promotion abuse: one operator running many accounts,
sharing infrastructure, spreading fraudulent item-not-received and damage
claims thinly enough that no single account looks abnormal, and farming
first-order promotions through multi-accounting.

## The action boundary

| Action | Customer-visible | Reversal |
|---|---|---|
| `allow` | no | n/a |
| `monitor` | **no** | clear the flag |
| `queue_for_review` | **no** | dismiss from queue |
| `step_up_verification` | yes | remove the requirement |
| `hold_refund` | yes | release immediately |

`hold_refund` is the most severe automatic action available. It pauses one
pending refund for up to 72 hours pending human review. The order is unaffected,
no money moves, and a human must confirm before any refund is actually denied.

### Explicitly prohibited

| Prohibited | Why |
|---|---|
| `close_account` | Permanent and hard to reverse; a human decision |
| `seize_funds` | This system has no authority to move money in any direction |
| `blocklist_identifier` | Collateral damage to households and shared addresses is too high |
| `report_to_authority` | A legal step, never automated |

Enforced by `tests/test_actions.py::test_no_action_can_move_money_or_be_irreversible`.

## Why the generator is not an offence tool

The simulator models evasion — infrastructure rotation, cell partitioning,
dormancy, cover orders. That is necessary: you cannot honestly claim a detector
works against sophisticated rings without generating sophisticated rings to
test it on. The alternative is the industry norm of reporting 0.99 on a naive
benchmark, which is worse for defenders.

It produces **evaluation fixtures only**:

- It emits synthetic rows into an in-process DataFrame. It has no network
  capability and touches no external system.
- It encodes nothing not already public in the fraud-detection literature. Every
  technique it models is one defenders already know; none is a novel bypass.
- It generates no working credentials, payment instruments, or account
  registrations. Card tokens are random hashes with no relationship to any real
  card, BIN or network.
- Nothing in it targets a specific merchant, platform, or person.

The asymmetry matters: real abuse operators already know how to rotate devices.
Defenders are the ones who mostly lack an honest benchmark to measure against.

## Abuse surface of the system itself

**False positives harm real customers.** The dominant risk. Every false positive
in the backtest is a family or hostel resident sharing a payment instrument, and
these are correlated with lower-income and shared-accommodation households.
Mitigations: inverse-degree weighting that discounts shared infrastructure;
sufficiency gating that downgrades address-and-IP-only evidence; the rule that
an account with no claim history is never auto-restricted; and a human in the
loop for every high-severity action.

**Score-based discrimination.** Nothing here should be used for credit,
employment or any purpose beyond abuse review. See `MODEL_CARD.md`.

**Ledger as evidence.** The hash chain proves the log has not been altered since
writing. It does **not** prove the decision was correct, and it is not a
notarised or externally anchored timestamp.

**LLM prompt injection.** The narration model receives only a structured
evidence packet built from our own database — never customer free text. If
customer-supplied text (claim descriptions, support notes) is ever added to the
packet, it becomes an injection surface and must be treated as untrusted data.
Today the validator rejects any narration citing an identifier not present in
the packet, which limits the blast radius but is not a complete defence.

**Model inversion / probing.** An operator with dashboard access could learn
which of their accounts are flagged and adapt. Scores should not be exposed to
anyone outside the risk team, and the API has no authentication today — it is a
demo, not a deployment.

## Privacy

Identifier values are never returned in evidence packets; they are replaced by
a 10-character SHA-256 prefix. A reviewer learns that two accounts share a card,
not what the card is. The live adapter derives account keys from a hash of
contact details rather than storing raw email addresses when no customer id is
present.

Retention, deletion and DPDP Act obligations are **not implemented**. This is a
buildathon prototype; a production deployment needs a retention policy, a
subject-access path, and a documented lawful basis for processing.

## Known gaps

- No authentication or authorisation on the API.
- No rate limiting.
- The ledger is local-file, not replicated or externally anchored.
- No adversarial-drift monitoring; a ring that adapts after deployment would not
  be detected as a distribution shift.

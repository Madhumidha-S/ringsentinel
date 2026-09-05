"""Bounded action policy.

Three rules govern everything this system is allowed to do.

**Bounded.** The action set is a fixed enum. There is no free-form "do what
seems right" path, and nothing here can move money. The most severe automatic
action pauses a refund and asks the customer to verify - it never seizes,
never charges, never closes an account.

**Reversible.** Every action carries an explicit reversal, and the ledger
records enough to perform it.

**Refusable.** An action is only permitted when the evidence supports it. A
high score on thin evidence is routed to a human, not executed. Weak evidence
downgrades the action even when the model is confident.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Action(StrEnum):
    ALLOW = "allow"
    MONITOR = "monitor"
    QUEUE_FOR_REVIEW = "queue_for_review"
    STEP_UP_VERIFICATION = "step_up_verification"
    HOLD_REFUND = "hold_refund"


#: Human-readable effect and the reversal that undoes it.
ACTION_SPEC: dict[Action, dict[str, str]] = {
    Action.ALLOW: {
        "effect": "No restriction. Account proceeds normally.",
        "reversal": "n/a",
        "severity": "none",
    },
    Action.MONITOR: {
        "effect": "Flagged internally for observation. Customer sees nothing.",
        "reversal": "Clear the monitoring flag.",
        "severity": "none",
    },
    Action.QUEUE_FOR_REVIEW: {
        "effect": "Placed in the analyst queue. No customer-visible change.",
        "reversal": "Dismiss from queue.",
        "severity": "low",
    },
    Action.STEP_UP_VERIFICATION: {
        "effect": "Customer is asked to confirm identity before the next refund is released.",
        "reversal": "Remove the verification requirement.",
        "severity": "medium",
    },
    Action.HOLD_REFUND: {
        "effect": "Pending refund is paused for up to 72h awaiting review. Order is unaffected.",
        "reversal": "Release the refund immediately.",
        "severity": "high",
    },
}

# Actions this system will never take automatically, and why. Listing them is
# part of the defence-only posture: see docs/THREAT_MODEL.md.
PROHIBITED_AUTOMATIC_ACTIONS = {
    "close_account": "Permanent and hard to reverse; requires a human decision.",
    "seize_funds": "This system has no authority to move money in any direction.",
    "blocklist_identifier": "Collateral damage to households and shared addresses is too high.",
    "report_to_authority": "A legal step, never an automated one.",
}


@dataclass
class Decision:
    account_id: str
    score: float
    band: str
    action: Action
    rationale: str
    requires_human: bool
    reversal: str
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "score": self.score,
            "band": self.band,
            "action": self.action.value,
            "rationale": self.rationale,
            "requires_human": self.requires_human,
            "reversal": self.reversal,
            "severity": self.severity,
        }


def band_for(score: float, review_threshold: float, action_threshold: float) -> str:
    if score >= action_threshold:
        return "act"
    if score >= review_threshold:
        return "review"
    return "allow"


def decide(
    account_id: str,
    score: float,
    band: str,
    sufficiency: str,
    sufficiency_reason: str,
    exposure_inr: float = 0.0,
    high_value_threshold_inr: float = 25_000.0,
    claims_filed: int = 0,
) -> Decision:
    """Map a score plus an evidence verdict onto a bounded action.

    `claims_filed` gates every customer-visible action. An account that has
    never filed a refund claim has cost the merchant nothing, so there is
    nothing to hold and no justification for adding friction to it - however
    confident the model is about its cluster. Identity linkage on its own is a
    reason to watch an account, never a reason to restrict a customer.

    This single rule removes the system's worst failure mode. Every false
    positive in the backtest is a family or a hostel resident sharing a payment
    instrument, and almost none of them have filed a claim.
    """
    if band == "allow":
        return Decision(
            account_id, score, band, Action.ALLOW,
            "Score below the review threshold.", False,
            ACTION_SPEC[Action.ALLOW]["reversal"], "none",
        )

    # Evidence gates the action, not just the score. This is where a confident
    # model is deliberately overruled.
    if sufficiency == "insufficient":
        return Decision(
            account_id, score, band, Action.MONITOR,
            f"Score is {score:.2f} but evidence is insufficient to act: {sufficiency_reason}. "
            "Observing only.",
            False, ACTION_SPEC[Action.MONITOR]["reversal"], "none",
        )

    if sufficiency == "weak":
        return Decision(
            account_id, score, band, Action.QUEUE_FOR_REVIEW,
            f"Score is {score:.2f} but {sufficiency_reason}. Routed to a human rather than "
            "actioned automatically.",
            True, ACTION_SPEC[Action.QUEUE_FOR_REVIEW]["reversal"], "low",
        )

    if band == "review":
        return Decision(
            account_id, score, band, Action.QUEUE_FOR_REVIEW,
            f"Score {score:.2f} sits in the review band; {sufficiency_reason}.",
            True, ACTION_SPEC[Action.QUEUE_FOR_REVIEW]["reversal"], "low",
        )

    # No claim on record: nothing to restrict, and no loss to prevent yet.
    if claims_filed <= 0:
        return Decision(
            account_id, score, band, Action.MONITOR,
            f"Score {score:.2f} with {sufficiency} evidence, but this account has filed no "
            "refund claim. There is nothing to hold and no loss to prevent, so it is watched "
            "rather than restricted. A shared card or address is consistent with a household.",
            False, ACTION_SPEC[Action.MONITOR]["reversal"], "none",
        )

    # band == "act" with moderate or strong evidence.
    if exposure_inr >= high_value_threshold_inr:
        return Decision(
            account_id, score, band, Action.HOLD_REFUND,
            f"Score {score:.2f} with {sufficiency} evidence and INR {exposure_inr:,.0f} "
            "of claims at stake. Refund paused pending review; a human must confirm "
            "before it is denied.",
            True, ACTION_SPEC[Action.HOLD_REFUND]["reversal"], "high",
        )

    return Decision(
        account_id, score, band, Action.STEP_UP_VERIFICATION,
        f"Score {score:.2f} with {sufficiency} evidence. Identity confirmation required "
        "before the next refund is released.",
        False, ACTION_SPEC[Action.STEP_UP_VERIFICATION]["reversal"], "medium",
    )

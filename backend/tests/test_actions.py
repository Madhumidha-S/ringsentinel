from ringsentinel.agent.actions import (
    PROHIBITED_AUTOMATIC_ACTIONS,
    Action,
    band_for,
    decide,
)


def test_insufficient_evidence_never_restricts_a_customer():
    d = decide("acc_1", 0.99, "act", "insufficient", "no links on record")
    assert d.action == Action.MONITOR
    assert d.severity == "none"


def test_weak_evidence_goes_to_a_human_not_an_action():
    d = decide("acc_1", 0.97, "act", "weak", "only a shared address")
    assert d.action == Action.QUEUE_FOR_REVIEW
    assert d.requires_human


def test_high_exposure_holds_the_refund_and_needs_confirmation():
    d = decide("acc_1", 0.95, "act", "strong", "two device links", exposure_inr=80_000,
               claims_filed=9)
    assert d.action == Action.HOLD_REFUND
    assert d.requires_human, "a high-severity action must not complete without a human"


def test_low_score_allows():
    assert decide("acc_1", 0.01, "allow", "strong", "").action == Action.ALLOW


def test_bands():
    assert band_for(0.9, 0.3, 0.8) == "act"
    assert band_for(0.5, 0.3, 0.8) == "review"
    assert band_for(0.1, 0.3, 0.8) == "allow"


def test_no_action_can_move_money_or_be_irreversible():
    """The defence-only guarantee, enforced in code rather than prose."""
    for action in Action:
        assert action.value not in PROHIBITED_AUTOMATIC_ACTIONS
    assert "seize_funds" in PROHIBITED_AUTOMATIC_ACTIONS
    assert "close_account" in PROHIBITED_AUTOMATIC_ACTIONS


def test_an_account_with_no_claims_is_never_auto_restricted():
    """The household-protection rule.

    Every false positive in the backtest is a family or hostel resident sharing
    a card. Almost none have filed a claim, so gating customer-visible actions
    on claim history removes the failure mode without touching recall on
    accounts that have actually extracted money.
    """
    d = decide("acc_1", 1.0, "act", "strong", "two card links", exposure_inr=0.0,
               claims_filed=0)
    assert d.action == Action.MONITOR
    assert d.severity == "none"
    assert not d.requires_human


def test_an_account_with_claims_is_still_actioned():
    d = decide("acc_1", 0.95, "act", "strong", "two device links", exposure_inr=4_000,
               claims_filed=3)
    assert d.action == Action.STEP_UP_VERIFICATION

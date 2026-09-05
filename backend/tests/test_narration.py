"""Narration must never invent a reference, and must never simply fail."""

from __future__ import annotations

from ringsentinel.agent.evidence import EvidencePacket, LinkEvidence
from ringsentinel.agent.narrate import _validate, narrate


def _packet() -> EvidencePacket:
    return EvidencePacket(
        account_id="acc_R001_002", score=0.94, band="act", community_id=7,
        community_size=4, peers=["acc_R001_001", "acc_R001_003"],
        links=[
            LinkEvidence("acc_R001_001", "device_id", "aabbccddee",
                         "same device fingerprint", 0.85)
        ],
        facts={"orders": 5, "claims": 3, "claim_rate": 0.6, "total_spend_inr": 12000.0,
               "claimed_inr": 7000.0, "granted_refunds_inr": 7000.0,
               "account_age_days": 40.0, "distinct_devices": 1, "distinct_cards": 1,
               "linked_accounts": 2},
        contributing_factors=[{"feature": "claim_rate", "value": 0.6,
                               "population_median": 0.0, "lift": None,
                               "statement": "files a refund claim on 60% of its orders"}],
        sufficiency="strong", sufficiency_reason="one strong-identifier link",
    )


def test_a_narration_citing_an_invented_account_is_rejected():
    ok, note = _validate(
        "Account acc_R001_002 colluded with acc_R999_999 to defraud the merchant.",
        _packet(),
    )
    assert not ok
    assert "acc_R999_999" in note


def test_a_narration_citing_only_real_references_passes():
    ok, _ = _validate(
        "Account acc_R001_002 shares a device with acc_R001_001 (reference aabbccddee) "
        "and files claims on most of its orders, which warrants review.",
        _packet(),
    )
    assert ok


def test_template_fallback_is_used_when_the_llm_is_disabled():
    n = narrate(_packet(), allow_llm=False)
    assert n.source == "template"
    assert "acc_R001_002" in n.text
    assert len(n.text) > 80


def test_template_fallback_cites_nothing_it_should_not():
    packet = _packet()
    n = narrate(packet, allow_llm=False)
    ok, note = _validate(n.text, packet)
    assert ok, note

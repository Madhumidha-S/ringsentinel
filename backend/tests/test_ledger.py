import dataclasses

from ringsentinel.ledger.ledger import DecisionLedger


def test_chain_verifies_when_intact(tmp_path):
    ledger = DecisionLedger(path=tmp_path / "ledger.ndjson")
    for i in range(5):
        ledger.append("score", {"score": i / 10}, f"acc_{i}")
    ok, detail = ledger.verify()
    assert ok, detail


def test_tampering_with_a_payload_breaks_the_chain(tmp_path):
    ledger = DecisionLedger(path=tmp_path / "ledger.ndjson")
    ledger.append("score", {"score": 0.9}, "acc_1")
    ledger.append("action", {"action": "hold_refund"}, "acc_1")
    ledger.append("action", {"action": "allow"}, "acc_2")

    ledger.entries[1] = dataclasses.replace(ledger.entries[1], payload={"action": "allow"})
    ok, detail = ledger.verify()
    assert not ok
    assert "entry 1" in detail


def test_ledger_survives_a_reload(tmp_path):
    path = tmp_path / "ledger.ndjson"
    first = DecisionLedger(path=path)
    first.append("score", {"score": 0.5}, "acc_1")
    first.append("action", {"action": "monitor"}, "acc_1")
    head = first.head()

    reloaded = DecisionLedger(path=path)
    assert len(reloaded.entries) == 2
    assert reloaded.head() == head
    assert reloaded.verify()[0]


def test_entries_are_retrievable_per_account(tmp_path):
    ledger = DecisionLedger(path=tmp_path / "l.ndjson")
    ledger.append("score", {}, "acc_1")
    ledger.append("score", {}, "acc_2")
    ledger.append("action", {}, "acc_1")
    assert len(ledger.for_account("acc_1")) == 2

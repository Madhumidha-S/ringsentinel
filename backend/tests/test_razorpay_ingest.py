"""Razorpay adapter, exercised against fixtures so it is testable without keys."""

from __future__ import annotations

import pandas as pd
import pytest

from ringsentinel.ingest.razorpay import (
    RazorpayClient,
    RazorpayCredentialsError,
    map_customers_to_accounts,
    map_payments_to_orders,
    map_refunds_to_claims,
)

PAYMENTS = [
    {"id": "pay_A", "order_id": "order_A", "customer_id": "cust_1", "status": "captured",
     "amount": 249900, "created_at": 1735689600, "card_id": "card_x",
     "email": "a@x.com", "contact": "+919900000001",
     "notes": {"device_id": "dev_1", "ip": "1.2.3.4",
               "shipping_address": "Flat 2B, 9 MG Road, Bengaluru 560001"}},
    {"id": "pay_B", "order_id": "order_B", "customer_id": "cust_1", "status": "refunded",
     "amount": 150000, "created_at": 1735776000, "card_id": "card_x",
     "email": "a@x.com", "contact": "+919900000001", "notes": {}},
    # No customer_id: the adapter must fall back to a pseudonymous key.
    {"id": "pay_C", "order_id": "order_C", "status": "captured", "amount": 99900,
     "created_at": 1735862400, "card_id": "card_y",
     "email": "b@x.com", "contact": "+919900000002", "notes": {}},
    # Failed payments are not orders.
    {"id": "pay_D", "order_id": "order_D", "status": "failed", "amount": 500000,
     "created_at": 1735862400, "notes": {}},
]
REFUNDS = [
    {"id": "rfnd_1", "payment_id": "order_B", "amount": 150000,
     "created_at": 1735948800, "status": "processed", "notes": {"reason": "item_not_received"}},
    {"id": "rfnd_2", "payment_id": "order_C", "amount": 50000,
     "created_at": 1736035200, "status": "pending", "notes": {}},
]
CUSTOMERS = [{"id": "cust_1", "email": "A.Person+shop@gmail.com",
              "contact": "+919900000001", "created_at": 1735603200}]


def test_paise_convert_to_rupees_exactly_once():
    orders = map_payments_to_orders(PAYMENTS)
    assert orders.loc[orders.order_id == "order_A", "amount_inr"].iloc[0] == 2499.00


def test_failed_payments_are_not_orders():
    orders = map_payments_to_orders(PAYMENTS)
    assert "order_D" not in set(orders.order_id)
    assert len(orders) == 3


def test_a_payment_without_a_customer_id_gets_a_pseudonymous_key():
    orders = map_payments_to_orders(PAYMENTS)
    key = orders.loc[orders.order_id == "order_C", "account_id"].iloc[0]
    assert key.startswith("cust_")
    assert "b@x.com" not in key, "raw email must not appear in the account key"


def test_first_order_is_flagged_per_account():
    orders = map_payments_to_orders(PAYMENTS)
    cust1 = orders[orders.account_id == "cust_1"].sort_values("ts")
    assert list(cust1.is_first_order) == [True, False]


def test_refund_status_maps_to_granted():
    orders = map_payments_to_orders(PAYMENTS)
    claims = map_refunds_to_claims(REFUNDS, orders)
    assert claims.set_index("claim_id").loc["rfnd_1", "granted"]
    assert not claims.set_index("claim_id").loc["rfnd_2", "granted"]


def test_missing_refund_reason_becomes_unknown():
    orders = map_payments_to_orders(PAYMENTS)
    claims = map_refunds_to_claims(REFUNDS, orders)
    assert claims.set_index("claim_id").loc["rfnd_2", "claim_type"] == "unknown"


def test_customer_email_is_normalised():
    orders = map_payments_to_orders(PAYMENTS)
    accounts = map_customers_to_accounts(CUSTOMERS, orders)
    assert accounts.set_index("account_id").loc["cust_1", "email_norm"] == "aperson@gmail.com"


def test_accounts_seen_only_in_payments_are_backfilled():
    orders = map_payments_to_orders(PAYMENTS)
    accounts = map_customers_to_accounts(CUSTOMERS, orders)
    assert set(orders.account_id) <= set(accounts.account_id)


def test_device_and_ip_are_absent_when_the_merchant_sends_no_telemetry():
    """The documented live-data gap, asserted so it cannot be forgotten."""
    orders = map_payments_to_orders(PAYMENTS)
    order_b = orders[orders.order_id == "order_B"].iloc[0]
    # pandas represents the absent value as NA in an object column.
    assert pd.isna(order_b["device_id"])
    assert pd.isna(order_b["ip"])


def test_a_live_key_is_refused(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_abc123")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
    with pytest.raises(RazorpayCredentialsError, match="non-test key"):
        RazorpayClient.from_env()


def test_missing_credentials_give_an_actionable_error(monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    with pytest.raises(RazorpayCredentialsError, match="simulator"):
        RazorpayClient.from_env()

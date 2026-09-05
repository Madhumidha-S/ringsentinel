"""Razorpay test-mode ingestion.

Maps live Razorpay API entities onto the internal schema, so the detector runs
against a real merchant's data rather than only against the simulator.

What the API gives us, and what it does not
-------------------------------------------
Payments, refunds, customers and card fingerprints come straight from the API.
Two of our strongest graph signals do **not**:

* ``device_id`` - no device fingerprint is exposed. In production this comes
  from the merchant's own checkout telemetry (a fingerprinting SDK on the
  storefront), joined on ``order_id``.
* ``ip`` - not exposed on the payment entity either; same source.

We do not paper over this. The adapter emits ``None`` for both and the graph
builder simply forms fewer edges, which lowers recall on exactly the rings that
rotate infrastructure. ``docs/ARCHITECTURE.md`` quantifies that degradation.
The card fingerprint (``card_id``) is available and is a strong link on its own.

Amounts arrive in paise and are converted to rupees exactly once, here.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

import httpx
import pandas as pd

API_BASE = "https://api.razorpay.com/v1"
PAISE_PER_RUPEE = 100


class RazorpayCredentialsError(RuntimeError):
    """Raised when test-mode credentials are absent or malformed."""


@dataclass
class RazorpayClient:
    """Thin read-only client. Test mode only - keys must start with `rzp_test_`."""

    key_id: str
    key_secret: str
    timeout: float = 20.0

    @classmethod
    def from_env(cls) -> RazorpayClient:
        key_id = os.environ.get("RAZORPAY_KEY_ID", "")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
        if not key_id or not key_secret:
            raise RazorpayCredentialsError(
                "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET (test mode) to ingest live data. "
                "Without them, run against the simulator instead."
            )
        if not key_id.startswith("rzp_test_"):
            raise RazorpayCredentialsError(
                f"Refusing to run against a non-test key ({key_id[:12]}...). "
                "This tool is read-only but is scoped to test mode by policy."
            )
        return cls(key_id=key_id, key_secret=key_secret)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{API_BASE}{path}", params=params, auth=(self.key_id, self.key_secret)
            )
            response.raise_for_status()
            return response.json()

    def fetch_payments(self, count: int = 100, skip: int = 0) -> list[dict[str, Any]]:
        return self._get("/payments", {"count": min(count, 100), "skip": skip}).get("items", [])

    def fetch_refunds(self, count: int = 100, skip: int = 0) -> list[dict[str, Any]]:
        return self._get("/refunds", {"count": min(count, 100), "skip": skip}).get("items", [])

    def fetch_customers(self, count: int = 100, skip: int = 0) -> list[dict[str, Any]]:
        return self._get("/customers", {"count": min(count, 100), "skip": skip}).get("items", [])


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------

def _pseudonymous_account_id(payment: dict[str, Any]) -> str:
    """Stable account key.

    Razorpay payments are not always attached to a customer id, so we fall back
    to a hash of the contact details. Hashing rather than storing the raw email
    keeps the graph key non-identifying while remaining joinable.
    """
    customer_id = payment.get("customer_id")
    if customer_id:
        return str(customer_id)
    seed = (payment.get("email") or "") + "|" + (payment.get("contact") or "")
    if seed == "|":
        return f"anon_{payment.get('id', 'unknown')}"
    return "cust_" + hashlib.sha256(seed.encode()).hexdigest()[:16]


def _normalise_address(notes: dict[str, Any] | None) -> str | None:
    """Shipping address, if the merchant puts one in payment notes."""
    if not notes:
        return None
    for key in ("shipping_address", "address", "ship_to"):
        if notes.get(key):
            from ..simulator.entities import normalise_address

            return normalise_address(str(notes[key]))
    return None


def map_payments_to_orders(payments: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for payment in payments:
        if payment.get("status") not in ("captured", "authorized", "refunded"):
            continue
        notes = payment.get("notes") or {}
        rows.append(
            {
                "order_id": payment.get("order_id") or payment["id"],
                "account_id": _pseudonymous_account_id(payment),
                "ts": float(payment.get("created_at", 0)),
                "amount_inr": float(payment.get("amount", 0)) / PAISE_PER_RUPEE,
                # Not exposed by the API - supplied by checkout telemetry.
                "device_id": notes.get("device_id"),
                "ip": notes.get("ip"),
                "card_token": payment.get("card_id"),
                "ship_address": notes.get("shipping_address"),
                "ship_address_norm": _normalise_address(notes),
                "promo_code": notes.get("promo_code") or notes.get("coupon"),
                "is_first_order": False,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("ts").reset_index(drop=True)
        first = df.groupby("account_id")["ts"].idxmin()
        df.loc[first, "is_first_order"] = True
    return df


def map_refunds_to_claims(
    refunds: list[dict[str, Any]], orders: pd.DataFrame
) -> pd.DataFrame:
    """A refund is the observable trace of a claim.

    The API does not carry the customer's stated reason, so ``claim_type`` is
    recorded as ``unknown`` unless the merchant writes one into notes. Our
    item-not-received feature is therefore weaker on live data than on the
    simulator, which is stated in the model card rather than hidden.
    """
    payment_to_account = (
        orders.set_index("order_id")["account_id"].to_dict() if not orders.empty else {}
    )
    rows = []
    for refund in refunds:
        payment_id = refund.get("payment_id")
        notes = refund.get("notes") or {}
        rows.append(
            {
                "claim_id": refund["id"],
                "order_id": payment_id,
                "account_id": payment_to_account.get(payment_id, f"unknown_{payment_id}"),
                "ts": float(refund.get("created_at", 0)),
                "claim_type": notes.get("reason", "unknown"),
                "amount_inr": float(refund.get("amount", 0)) / PAISE_PER_RUPEE,
                "granted": refund.get("status") == "processed",
            }
        )
    df = pd.DataFrame(rows)
    return df.sort_values("ts").reset_index(drop=True) if not df.empty else df


def map_customers_to_accounts(
    customers: list[dict[str, Any]], orders: pd.DataFrame
) -> pd.DataFrame:
    """Build the account table, backfilling any account seen only in payments."""
    from ..simulator.entities import normalise_email

    rows = []
    seen: set[str] = set()
    for customer in customers:
        account_id = str(customer["id"])
        seen.add(account_id)
        email = customer.get("email") or ""
        rows.append(
            {
                "account_id": account_id,
                "created_ts": float(customer.get("created_at", 0)),
                "email": email,
                "email_norm": normalise_email(email) if email else "",
                "phone": customer.get("contact") or "",
                "home_address": None,
                "home_address_norm": None,
                "cohort": "live",
                "label_ring_id": None,
                "label_is_ring": False,
                "label_evasion_level": -1,
            }
        )

    if not orders.empty:
        for account_id, first_ts in orders.groupby("account_id")["ts"].min().items():
            if account_id in seen:
                continue
            rows.append(
                {
                    "account_id": account_id,
                    "created_ts": float(first_ts),
                    "email": "",
                    "email_norm": "",
                    "phone": "",
                    "home_address": None,
                    "home_address_norm": None,
                    "cohort": "live",
                    "label_ring_id": None,
                    "label_is_ring": False,
                    "label_evasion_level": -1,
                }
            )
    return pd.DataFrame(rows)


def ingest(client: RazorpayClient, max_records: int = 500) -> dict[str, pd.DataFrame]:
    """Pull test-mode data and map it into the internal schema."""
    payments: list[dict[str, Any]] = []
    refunds: list[dict[str, Any]] = []
    customers: list[dict[str, Any]] = []

    for skip in range(0, max_records, 100):
        batch = client.fetch_payments(100, skip)
        payments.extend(batch)
        if len(batch) < 100:
            break
    for skip in range(0, max_records, 100):
        batch = client.fetch_refunds(100, skip)
        refunds.extend(batch)
        if len(batch) < 100:
            break
    customers = client.fetch_customers(100)

    orders = map_payments_to_orders(payments)
    return {
        "orders": orders,
        "claims": map_refunds_to_claims(refunds, orders),
        "accounts": map_customers_to_accounts(customers, orders),
    }


#: Documented field mapping, rendered by `ringsentinel ingest --explain`.
FIELD_MAPPING = [
    ("payment.id / payment.order_id", "orders.order_id", "direct"),
    ("payment.customer_id or sha256(email|contact)", "orders.account_id", "pseudonymised"),
    ("payment.created_at", "orders.ts", "epoch seconds, direct"),
    ("payment.amount", "orders.amount_inr", "paise -> rupees"),
    ("payment.card_id", "orders.card_token", "network fingerprint, direct"),
    ("payment.notes.device_id", "orders.device_id", "NOT in API - checkout telemetry"),
    ("payment.notes.ip", "orders.ip", "NOT in API - checkout telemetry"),
    ("payment.notes.shipping_address", "orders.ship_address_norm", "normalised"),
    ("refund.id", "claims.claim_id", "direct"),
    ("refund.amount", "claims.amount_inr", "paise -> rupees"),
    ("refund.status == processed", "claims.granted", "derived"),
    ("refund.notes.reason", "claims.claim_type", "often absent -> 'unknown'"),
    ("customer.id", "accounts.account_id", "direct"),
    ("customer.email", "accounts.email_norm", "normalised (gmail dots/plus)"),
]

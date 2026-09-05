"""Synthetic merchant population with embedded abuse rings.

Design notes that matter for whether the resulting metrics mean anything:

* **Legitimate accounts share identifiers too.** Families share a shipping
  address and often a card. Housemates share a device. Campuses, offices and
  mobile CGNAT put thousands of unrelated users behind one IP. Roughly a fifth
  of the legitimate population here sits in such a cluster. Without this, ring
  detection collapses to "find any shared identifier" and every reported score
  is inflated.

* **Rings span the full evasion range in one dataset**, rather than us
  generating ten separate easy-to-hard files. A real merchant faces naive and
  sophisticated operators simultaneously. We record each ring's evasion level
  as held-out metadata so recall can be reported per level without ever
  exposing it to the model.

* **Nothing the detector can see encodes the label.** Ring membership, ring id
  and evasion level live only in the label columns, which are dropped before
  featurisation. See tests/test_no_leakage.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..config import SimulationConfig
from . import entities as ent
from .profiles import MAX_LEVEL, MIN_LEVEL, profile_for

CLAIM_TYPES = ["item_not_received", "damaged_on_arrival", "wrong_item", "not_as_described"]
PROMO_CODES = ["WELCOME150", "FIRST200", "FESTIVE300", "NEWUSER250", "SAVE100"]

SECONDS_PER_DAY = 86_400


@dataclass
class Dataset:
    """A generated merchant history plus its held-out ground truth."""

    accounts: pd.DataFrame
    orders: pd.DataFrame
    claims: pd.DataFrame
    meta: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        n_ring = int(self.accounts["label_is_ring"].sum())
        n_acc = len(self.accounts)
        gross = self.claims.loc[self.claims["granted"], "amount_inr"].sum()
        abusive = self.claims.merge(
            self.accounts[["account_id", "label_is_ring"]], on="account_id", how="left"
        )
        leak = abusive.loc[abusive["granted"] & abusive["label_is_ring"], "amount_inr"].sum()
        return (
            f"accounts={n_acc:,} (ring={n_ring:,}, {n_ring / n_acc:.1%})  "
            f"orders={len(self.orders):,}  claims={len(self.claims):,}\n"
            f"refunds granted=INR {gross:,.0f}  of which to ring accounts=INR {leak:,.0f} "
            f"({leak / gross:.1%})"
        )


def _order_amount(rng: np.random.Generator) -> float:
    return float(np.round(np.clip(rng.lognormal(6.9, 0.75), 199, 45_000), 2))


def _poisson_at_least(rng: np.random.Generator, lam: float, floor: int = 1) -> int:
    return max(floor, int(rng.poisson(lam)))


# --------------------------------------------------------------------------
# Legitimate population
# --------------------------------------------------------------------------

def _build_legit(
    rng: np.random.Generator, cfg: SimulationConfig, t0: float
) -> tuple[list[dict], list[dict], list[dict]]:
    accounts: list[dict] = []
    orders: list[dict] = []
    claims: list[dict] = []

    n = cfg.n_legit_accounts
    horizon_s = cfg.horizon_days * SECONDS_PER_DAY

    # Shared egress IP pools (campus / office / CGNAT). Deliberately large so
    # that the IP edge is high-degree and therefore weak evidence.
    n_pools = max(4, int(n * cfg.shared_ip_fraction / 180))
    ip_pools = [ent.make_ip(rng) for _ in range(n_pools)]

    # Household assignment: consecutive accounts are grouped into families that
    # genuinely share an address, and sometimes a card and a device.
    household_of: dict[int, int] = {}
    household_addr: dict[int, str] = {}
    household_card: dict[int, str | None] = {}
    household_device: dict[int, str | None] = {}
    household_base_ts: dict[int, float] = {}
    idx = 0
    hh_id = 0
    n_household_accounts = int(n * cfg.household_fraction)
    while idx < n_household_accounts:
        size = int(rng.integers(2, 5))
        addr = ent.make_address(rng)
        shared_card = ent.make_card(rng) if rng.random() < 0.55 else None
        shared_dev = ent.make_device(rng) if rng.random() < 0.35 else None
        # Families sign up in a cluster - one member discovers the merchant and
        # the rest follow within days. Without this, legitimate clusters have a
        # signup span of ~100 days against a ring's ~5, and signup-span alone
        # separates them almost perfectly. That was the single largest
        # artefact in an earlier version of this generator.
        hh_base = t0 + float(rng.uniform(0, horizon_s * 0.85))
        for _ in range(size):
            if idx >= n_household_accounts:
                break
            household_of[idx] = hh_id
            household_addr[hh_id] = addr
            household_card[hh_id] = shared_card
            household_device[hh_id] = shared_dev
            household_base_ts[hh_id] = hh_base
            idx += 1
        hh_id += 1

    # Hub assignment: hostels, PG accommodations, offices. Unrelated people
    # sharing one shipping address and usually one wifi egress. Roommates
    # occasionally share a device; they never share a card or an inbox.
    hub_of: dict[int, int] = {}
    hub_addr: dict[int, str] = {}
    hub_ip: dict[int, str] = {}
    hub_device: dict[int, str | None] = {}
    hub_base_ts: dict[int, float] = {}
    n_hub_accounts = int(n * cfg.address_hub_fraction)
    hub_id = 0
    while idx < n_household_accounts + n_hub_accounts:
        hub_size = int(rng.integers(8, 36))
        addr = ent.make_address(rng)
        wifi = ent.make_ip(rng)
        roommate_device = ent.make_device(rng)
        # Hostel and PG residents arrive together at intake, so their signups
        # bunch just as tightly as a ring's - by design, this is the hardest
        # legitimate cohort to separate on temporal features alone.
        hub_base = t0 + float(rng.uniform(0, horizon_s * 0.85))
        for _ in range(hub_size):
            if idx >= n_household_accounts + n_hub_accounts:
                break
            hub_of[idx] = hub_id
            hub_addr[hub_id] = addr
            hub_ip[hub_id] = wifi
            hub_device[hub_id] = roommate_device
            hub_base_ts[hub_id] = hub_base
            idx += 1
        hub_id += 1

    for i in range(n):
        first, last = ent.make_name(rng)
        email = ent.make_email(rng, first, last)
        hh = household_of.get(i)
        hub = hub_of.get(i)
        # Same signup window as rings (0 - 0.85 of horizon). If the two
        # populations spanned different windows, any temporal split would have
        # a distorted prevalence in the test period and the reported precision
        # would be an artefact of the split rather than of the model.
        if hh is not None:
            created = household_base_ts[hh] + float(rng.normal(0, 8 * SECONDS_PER_DAY))
        elif hub is not None:
            created = hub_base_ts[hub] + float(rng.normal(0, 15 * SECONDS_PER_DAY))
        else:
            created = t0 + float(rng.uniform(0, horizon_s * 0.85))
        created = float(np.clip(created, t0, t0 + horizon_s * 0.85))
        if hh is not None:
            home_addr = household_addr[hh]
        elif hub is not None:
            home_addr = hub_addr[hub]
        else:
            home_addr = ent.make_address(rng)

        account_id = f"acc_L{i:06d}"
        accounts.append(
            {
                "account_id": account_id,
                "created_ts": created,
                "email": email,
                "email_norm": ent.normalise_email(email),
                "phone": ent.make_phone(rng),
                "home_address": home_addr,
                "home_address_norm": ent.normalise_address(home_addr),
                "cohort": (
                    "household" if hh is not None else ("hub" if hub is not None else "solo")
                ),
                "label_ring_id": None,
                "label_is_ring": False,
                "label_evasion_level": -1,
            }
        )

        if hh is not None and household_device[hh] and rng.random() < 0.6:
            own_device = household_device[hh]
        elif hub is not None and rng.random() < 0.10:
            # Roommates who genuinely share a laptop.
            own_device = hub_device[hub]
        else:
            own_device = ent.make_device(rng)
        own_card = (
            household_card[hh]
            if hh is not None and household_card[hh] and rng.random() < 0.7
            else ent.make_card(rng)
        )
        if hub is not None and rng.random() < 0.80:
            own_ip = hub_ip[hub]
        elif rng.random() < cfg.shared_ip_fraction:
            own_ip = ip_pools[int(rng.integers(0, n_pools))]
        else:
            own_ip = ent.make_ip(rng)

        n_orders = _poisson_at_least(rng, 5.5)
        for k in range(n_orders):
            ts = created + float(rng.uniform(0, max(1.0, t0 + horizon_s - created)))
            amount = _order_amount(rng)
            # Occasional second device (phone vs laptop) and gift addresses.
            device = own_device if rng.random() < 0.82 else ent.make_device(rng)
            card = own_card if rng.random() < 0.88 else ent.make_card(rng)
            ship = home_addr if rng.random() < 0.86 else ent.make_address(rng)
            ip = own_ip if rng.random() < 0.75 else ent.make_ip(rng)
            order_id = f"ord_L{i:06d}_{k:03d}"
            orders.append(
                {
                    "order_id": order_id,
                    "account_id": account_id,
                    "ts": ts,
                    "amount_inr": amount,
                    "device_id": device,
                    "ip": ip,
                    "card_token": card,
                    "ship_address": ship,
                    "ship_address_norm": ent.normalise_address(ship),
                    # Real shoppers keep using promos: festive sales, cart
                    # nudges, win-back offers. An earlier version gave
                    # legitimate accounts a promo only on their first order,
                    # which made promo_rate a near-categorical ring label.
                    "promo_code": (
                        PROMO_CODES[int(rng.integers(0, len(PROMO_CODES)))]
                        if rng.random() < (0.55 if k == 0 else 0.22)
                        else None
                    ),
                    "is_first_order": k == 0,
                }
            )
            if rng.random() < cfg.legit_claim_rate:
                claims.append(
                    {
                        "claim_id": f"clm_L{i:06d}_{k:03d}",
                        "order_id": order_id,
                        "account_id": account_id,
                        "ts": ts + float(rng.uniform(1, 12)) * SECONDS_PER_DAY,
                        "claim_type": CLAIM_TYPES[int(rng.integers(0, len(CLAIM_TYPES)))],
                        "amount_inr": amount,
                        "granted": bool(rng.random() < 0.93),
                    }
                )

    return accounts, orders, claims


# --------------------------------------------------------------------------
# Abuse rings
# --------------------------------------------------------------------------

def _build_ring(
    rng: np.random.Generator,
    cfg: SimulationConfig,
    t0: float,
    ring_idx: int,
    level: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    prof = profile_for(level)
    size = int(rng.integers(cfg.ring_size_min, cfg.ring_size_max + 1))
    horizon_s = cfg.horizon_days * SECONDS_PER_DAY

    accounts: list[dict] = []
    orders: list[dict] = []
    claims: list[dict] = []

    # Shared infrastructure, sized by the operator's degree discipline. A
    # sloppy ring reuses one device; a careful one keeps each device under a
    # threshold number of accounts.
    # Cell structure. A careful operator does not merely cap how many accounts
    # touch one device - they partition the ring into *disjoint cells* where a
    # cell's device, card and drop address are all its own. Cells share no
    # infrastructure, so the ring does not resolve to one connected component;
    # it looks like several unrelated small households.
    #
    # (An earlier version assigned identifiers by `j % n_devices` independently
    # per identifier type. Because the device and address groupings interleaved,
    # every ring chain-linked into a single component regardless of evasion
    # level, and a one-line component-size rule scored F1 0.96. Cells are the
    # difference between a rigged benchmark and a real one.)
    cap = max(2, prof.max_shared_degree)
    cell_size = min(cap, size)
    n_cells = max(1, math.ceil(size / cell_size))
    cell_device = [ent.make_device(rng) for _ in range(n_cells)]
    cell_card = [ent.make_card(rng) for _ in range(n_cells)]
    cell_drop = [ent.make_address(rng) for _ in range(n_cells)]
    cell_ip = [ent.make_ip(rng) for _ in range(n_cells)]
    ring_ip = ent.make_ip(rng)

    slip_rate = prof.slip_rate

    # Low-evasion rings farm one Gmail inbox with dot/plus variants, which our
    # normaliser collapses. High-evasion rings use unrelated disposable inboxes.
    first, last = ent.make_name(rng)
    base_email = f"{first}.{last}{rng.integers(100, 999)}@gmail.com"
    use_variants = rng.random() > (level / MAX_LEVEL)

    # Ring signup bursts span the same window as legitimate signups. When this
    # was 0.6 of the horizon, almost every ring was created before any sensible
    # train/test cutoff and the test fold held 28 positives - too few to
    # support a per-level claim about anything.
    burst_centre = t0 + float(rng.uniform(0, horizon_s * 0.80))
    spread_s = prof.signup_spread_days * SECONDS_PER_DAY
    ring_id = f"ring_{ring_idx:03d}"

    for j in range(size):
        created = burst_centre + float(rng.normal(0, max(60.0, spread_s / 2)))
        created = float(np.clip(created, t0, t0 + horizon_s * 0.85))
        if use_variants:
            email = ent.gmail_variant(rng, base_email)
        else:
            f2, l2 = ent.make_name(rng)
            email = ent.make_email(rng, f2, l2, disposable=rng.random() < 0.45)

        account_id = f"acc_R{ring_idx:03d}_{j:03d}"
        home = cell_drop[j // cell_size]
        accounts.append(
            {
                "account_id": account_id,
                "created_ts": created,
                "email": email,
                "email_norm": ent.normalise_email(email),
                "phone": ent.make_phone(rng),
                "home_address": home,
                "home_address_norm": ent.normalise_address(home),
                "cohort": "ring",
                "label_ring_id": ring_id,
                "label_is_ring": True,
                "label_evasion_level": level,
            }
        )

        cell = j // cell_size
        my_device = cell_device[cell]
        my_card = cell_card[cell]
        my_ip = cell_ip[cell] if n_cells > 1 else ring_ip
        dormancy_s = prof.dormancy_days * SECONDS_PER_DAY

        n_orders = _poisson_at_least(rng, 4.0)
        for k in range(n_orders):
            is_cover = rng.random() < prof.cover_order_ratio
            offset = float(rng.uniform(0, 20)) * SECONDS_PER_DAY
            ts = created + (0.0 if is_cover else dormancy_s) + offset
            ts = float(np.clip(ts, t0, t0 + horizon_s))
            amount = _order_amount(rng)
            if not is_cover:
                # Abusive orders skew expensive: the refund is the payload.
                amount = float(np.round(min(45_000, amount * rng.uniform(1.3, 2.4)), 2))

            if rng.random() < prof.device_rotation:
                device = ent.make_device(rng)
            elif n_cells > 1 and rng.random() < slip_rate:
                device = cell_device[int(rng.integers(0, n_cells))]
            else:
                device = my_device

            card = ent.make_card(rng) if rng.random() < prof.card_rotation else my_card
            ip = ent.make_ip(rng) if rng.random() < prof.ip_rotation else my_ip
            ship = cell_drop[cell] if rng.random() > slip_rate else cell_drop[
                int(rng.integers(0, n_cells))
            ]
            if rng.random() < prof.address_jitter:
                ship = ent.jitter_address(rng, ship)

            order_id = f"ord_R{ring_idx:03d}_{j:03d}_{k:03d}"
            orders.append(
                {
                    "order_id": order_id,
                    "account_id": account_id,
                    "ts": ts,
                    "amount_inr": amount,
                    "device_id": device,
                    "ip": ip,
                    "card_token": card,
                    "ship_address": ship,
                    "ship_address_norm": ent.normalise_address(ship),
                    "promo_code": (
                        PROMO_CODES[int(rng.integers(0, len(PROMO_CODES)))]
                        if k == 0 or rng.random() < 0.4
                        else None
                    ),
                    "is_first_order": k == 0,
                }
            )
            if not is_cover and rng.random() < prof.claim_rate:
                claims.append(
                    {
                        "claim_id": f"clm_R{ring_idx:03d}_{j:03d}_{k:03d}",
                        "order_id": order_id,
                        "account_id": account_id,
                        "ts": ts + float(rng.uniform(1, 9)) * SECONDS_PER_DAY,
                        "claim_type": (
                            "item_not_received"
                            if rng.random() < 0.62
                            else CLAIM_TYPES[int(rng.integers(0, len(CLAIM_TYPES)))]
                        ),
                        "amount_inr": amount,
                        "granted": bool(rng.random() < 0.88),
                    }
                )

    return accounts, orders, claims


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def generate(cfg: SimulationConfig | None = None) -> Dataset:
    cfg = cfg or SimulationConfig()
    rng = np.random.default_rng(cfg.seed)
    t0 = 1_735_689_600.0  # 2025-01-01T00:00:00Z

    accounts, orders, claims = _build_legit(rng, cfg, t0)

    # Spread rings uniformly across the evasion range so that per-level recall
    # is measurable from a single dataset.
    levels = np.tile(np.arange(MIN_LEVEL, MAX_LEVEL + 1), math.ceil(cfg.n_rings / 10))
    levels = levels[: cfg.n_rings]
    rng.shuffle(levels)

    for ring_idx, level in enumerate(levels):
        a, o, c = _build_ring(rng, cfg, t0, ring_idx, int(level))
        accounts.extend(a)
        orders.extend(o)
        claims.extend(c)

    acc_df = pd.DataFrame(accounts)
    ord_df = pd.DataFrame(orders).sort_values("ts").reset_index(drop=True)
    clm_df = pd.DataFrame(claims).sort_values("ts").reset_index(drop=True)

    return Dataset(
        accounts=acc_df,
        orders=ord_df,
        claims=clm_df,
        meta={
            "seed": cfg.seed,
            "horizon_days": cfg.horizon_days,
            "t0": t0,
            "n_rings": cfg.n_rings,
            "prevalence": float(acc_df["label_is_ring"].mean()),
        },
    )

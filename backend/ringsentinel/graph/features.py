"""Leakage-free feature construction.

Every feature is computed *as of* a cutoff timestamp. Accounts created after
the cutoff are excluded, and orders and claims after it are invisible. The
graph itself is rebuilt from the truncated history, so an account cannot
inherit evidence from an edge that had not formed yet.

This is stricter than a random train/test split and it is the correct
discipline for a risk model: at scoring time you only ever know the past. It
also costs real accuracy, which is the point - a model evaluated on a random
split would look better and be wrong.

Feature families
----------------
behavioural : what this account did on its own
identity    : how many distinct devices/cards/addresses it burned through
graph       : how strongly and how widely it is bound to other accounts
community   : what the cohort it sits in looks like, in aggregate
temporal    : signup bursts and dormancy, which survive infrastructure rotation
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .build import IdentityGraph, build_identity_graph
from .communities import Communities, community_cohesion, detect_communities

SECONDS_PER_DAY = 86_400

# Columns that must never reach the model.
LABEL_COLUMNS = ("label_is_ring", "label_ring_id", "label_evasion_level", "cohort")


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b else 0.0


def build_features(
    accounts: pd.DataFrame,
    orders: pd.DataFrame,
    claims: pd.DataFrame,
    as_of: float,
    identity: IdentityGraph | None = None,
    communities: Communities | None = None,
) -> tuple[pd.DataFrame, IdentityGraph, Communities]:
    """Featurise every account visible at `as_of`.

    Returns the feature frame plus the graph and communities it was built
    from, so that callers (the API, the evidence builder) can reuse them
    without recomputing.
    """
    acc = accounts[accounts["created_ts"] <= as_of].copy()
    ords = orders[orders["ts"] <= as_of]
    clms = claims[claims["ts"] <= as_of]

    if identity is None:
        identity = build_identity_graph(acc, ords)
    if communities is None:
        communities = detect_communities(identity)

    graph = identity.graph

    # ---------------- behavioural aggregates ----------------
    order_agg = ords.groupby("account_id").agg(
        n_orders=("amount_inr", "size"),
        total_amount=("amount_inr", "sum"),
        mean_amount=("amount_inr", "mean"),
        max_amount=("amount_inr", "max"),
        std_amount=("amount_inr", "std"),
        first_order_ts=("ts", "min"),
        last_order_ts=("ts", "max"),
        n_devices=("device_id", "nunique"),
        n_cards=("card_token", "nunique"),
        n_addresses=("ship_address_norm", "nunique"),
        n_ips=("ip", "nunique"),
        n_promos=("promo_code", "count"),
    )

    claim_agg = clms.groupby("account_id").agg(
        n_claims=("amount_inr", "size"),
        claimed_amount=("amount_inr", "sum"),
        first_claim_ts=("ts", "min"),
    )
    granted = clms[clms["granted"]].groupby("account_id")["amount_inr"].sum()
    inr_claim = (
        clms[clms["claim_type"] == "item_not_received"].groupby("account_id").size()
    )

    df = acc[["account_id", "created_ts"]].set_index("account_id")
    df = df.join(order_agg).join(claim_agg)
    df["granted_amount"] = granted
    df["n_inr_claims"] = inr_claim
    df = df.fillna(
        {
            "n_orders": 0, "total_amount": 0, "mean_amount": 0, "max_amount": 0,
            "std_amount": 0, "n_devices": 0, "n_cards": 0, "n_addresses": 0,
            "n_ips": 0, "n_promos": 0, "n_claims": 0, "claimed_amount": 0,
            "granted_amount": 0, "n_inr_claims": 0,
        }
    )

    df["account_age_days"] = (as_of - df["created_ts"]) / SECONDS_PER_DAY
    df["claim_rate"] = df["n_claims"] / df["n_orders"].clip(lower=1)
    df["inr_claim_share"] = df["n_inr_claims"] / df["n_claims"].clip(lower=1)
    df["claimed_value_share"] = df["claimed_amount"] / df["total_amount"].clip(lower=1)
    df["promo_rate"] = df["n_promos"] / df["n_orders"].clip(lower=1)
    df["devices_per_order"] = df["n_devices"] / df["n_orders"].clip(lower=1)
    df["cards_per_order"] = df["n_cards"] / df["n_orders"].clip(lower=1)
    df["addresses_per_order"] = df["n_addresses"] / df["n_orders"].clip(lower=1)

    # Dormancy: gap between signup and the first loss event. Evasive operators
    # deliberately age accounts before extracting, so this separates them from
    # impulsive abuse while surviving device/card rotation entirely.
    df["days_to_first_order"] = (df["first_order_ts"] - df["created_ts"]) / SECONDS_PER_DAY
    df["days_to_first_claim"] = (df["first_claim_ts"] - df["created_ts"]) / SECONDS_PER_DAY
    df["days_to_first_claim"] = df["days_to_first_claim"].fillna(-1.0)
    df["days_to_first_order"] = df["days_to_first_order"].fillna(-1.0)
    df["order_span_days"] = (df["last_order_ts"] - df["first_order_ts"]) / SECONDS_PER_DAY
    df["order_span_days"] = df["order_span_days"].fillna(0.0)

    # ---------------- graph structure ----------------
    degree = dict(graph.degree())
    wdegree = dict(graph.degree(weight="weight"))
    comp_size: dict[str, int] = {}
    import networkx as nx

    for comp in nx.connected_components(graph):
        for a in comp:
            comp_size[a] = len(comp)

    idx = df.index
    df["graph_degree"] = [degree.get(a, 0) for a in idx]
    df["graph_weighted_degree"] = [round(wdegree.get(a, 0.0), 4) for a in idx]
    df["component_size"] = [comp_size.get(a, 1) for a in idx]
    df["max_edge_weight"] = [
        max((d["weight"] for d in graph[a].values()), default=0.0) if a in graph else 0.0
        for a in idx
    ]
    df["community_size"] = [communities.size_of(a) for a in idx]

    two_hop = []
    for a in idx:
        if a not in graph:
            two_hop.append(0)
            continue
        seen = set()
        for nb in graph[a]:
            seen.add(nb)
            seen.update(graph[nb])
        seen.discard(a)
        two_hop.append(len(seen))
    df["two_hop_size"] = two_hop

    # Strongest identifier type binding this account to any other. A shared
    # inbox is near-proof; a shared campus IP is nearly meaningless. Collapsing
    # this into one number lets the model learn the difference.
    strongest = []
    n_strong_ids = []
    for a in idx:
        best = 0.0
        strong = 0
        if a in graph:
            for nb in graph[a]:
                for id_type, _value, contribution in identity.edge_evidence(a, nb):
                    best = max(best, contribution)
                    if id_type in ("email_norm", "phone", "device_id", "card_token"):
                        strong += 1
        strongest.append(round(best, 4))
        n_strong_ids.append(strong)
    df["strongest_link"] = strongest
    df["n_strong_links"] = n_strong_ids

    # ---------------- guilt by association ----------------
    # Aggregate the *behaviour* of graph neighbours, never their labels. An
    # account whose neighbours all file item-not-received claims is suspicious
    # even when its own record is clean, which is exactly how a ring's freshest
    # account gets caught.
    claim_rate_map = df["claim_rate"].to_dict()
    n_claims_map = df["n_claims"].to_dict()
    nb_claim_rate, nb_claims, nb_max_claim = [], [], []
    for a in idx:
        if a not in graph or graph.degree(a) == 0:
            nb_claim_rate.append(0.0)
            nb_claims.append(0.0)
            nb_max_claim.append(0.0)
            continue
        rates, counts = [], []
        for nb in graph[a]:
            rates.append(claim_rate_map.get(nb, 0.0))
            counts.append(n_claims_map.get(nb, 0.0))
        nb_claim_rate.append(round(float(np.mean(rates)), 4))
        nb_claims.append(float(np.sum(counts)))
        nb_max_claim.append(round(float(np.max(rates)), 4))
    df["neighbour_claim_rate"] = nb_claim_rate
    df["neighbour_total_claims"] = nb_claims
    df["neighbour_max_claim_rate"] = nb_max_claim

    # ---------------- community aggregates ----------------
    created_map = df["created_ts"].to_dict()
    total_amt_map = df["total_amount"].to_dict()
    comm_stats: dict[int, dict[str, float]] = {}
    for cid, mem in communities.members.items():
        mem = [m for m in mem if m in df.index]
        if not mem:
            continue
        signups = [created_map[m] for m in mem]
        rates = [claim_rate_map.get(m, 0.0) for m in mem]
        comm_stats[cid] = {
            "community_claim_rate": float(np.mean(rates)),
            "community_signup_span_days": (max(signups) - min(signups)) / SECONDS_PER_DAY,
            "community_total_value": float(sum(total_amt_map.get(m, 0.0) for m in mem)),
            "community_cohesion": community_cohesion(identity, mem) if len(mem) > 1 else 0.0,
        }

    default = {
        "community_claim_rate": 0.0,
        "community_signup_span_days": 0.0,
        "community_total_value": 0.0,
        "community_cohesion": 0.0,
    }
    for key in default:
        df[key] = [
            round(comm_stats.get(communities.community_of(a), default)[key], 4) for a in idx
        ]

    # Signup burst: how many accounts in this community appeared within 24h of
    # this one. Survives every form of infrastructure rotation, because the
    # operator still has to create the accounts.
    burst = []
    for a in idx:
        cid = communities.community_of(a)
        if cid is None:
            burst.append(0)
            continue
        t = created_map[a]
        mem = [m for m in communities.members[cid] if m in created_map]
        burst.append(sum(1 for m in mem if m != a and abs(created_map[m] - t) <= SECONDS_PER_DAY))
    df["signup_burst_24h"] = burst

    df = df.drop(columns=["first_order_ts", "last_order_ts", "first_claim_ts", "created_ts"])
    df = df.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return df.reset_index(), identity, communities


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in ("account_id", *LABEL_COLUMNS)]

"""Identity graph construction and weighting.

The graph is bipartite at heart: accounts connect to the identifiers they use
(email inbox, phone, device, card, shipping address, egress IP). We project it
to an account-to-account graph whose edge weight answers one question: *how
much evidence is there that these two accounts are the same hand?*

Two weighting decisions carry most of the signal.

**Prior by identifier type.** Sharing a normalised email inbox or a phone is
near-proof. Sharing a device or card is strong. Sharing a shipping address is
moderate - families and offices do it constantly. Sharing an egress IP is
almost worthless on its own, because campuses, offices and mobile CGNAT put
thousands of unrelated people behind one address.

**Inverse degree.** An identifier used by exactly two accounts is far stronger
evidence than one used by fifty. We weight each shared identifier by
1/(degree-1), so a two-account device contributes 1.0 and a fifty-account
device contributes 0.02. This is what stops shared-IP pools and public kiosks
from fusing the whole population into one giant component.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx
import pandas as pd

# Evidence weight per identifier type, before degree discounting.
IDENTIFIER_PRIORS: dict[str, float] = {
    "email_norm": 1.00,
    "phone": 0.95,
    "device_id": 0.85,
    "card_token": 0.80,
    "ship_address_norm": 0.55,
    "ip": 0.20,
}

# Identifiers touching more than this many accounts are treated as
# infrastructure, not identity, and are dropped from pair generation. Without
# a cap, a single CGNAT pool generates millions of meaningless pairs.
MAX_IDENTIFIER_DEGREE = 120

# Account-pair edges below this total weight are discarded as noise.
MIN_EDGE_WEIGHT = 0.15


@dataclass
class IdentityGraph:
    """Weighted account-to-account graph plus the evidence behind each edge."""

    graph: nx.Graph
    # (account_a, account_b) -> list of (identifier_type, value, contribution)
    evidence: dict[tuple[str, str], list[tuple[str, str, float]]] = field(default_factory=dict)
    dropped_identifiers: dict[str, int] = field(default_factory=dict)
    identifier_degree: dict[tuple[str, str], int] = field(default_factory=dict)

    def neighbours(self, account_id: str) -> list[tuple[str, float]]:
        if account_id not in self.graph:
            return []
        return sorted(
            ((n, d["weight"]) for n, d in self.graph[account_id].items()),
            key=lambda kv: -kv[1],
        )

    def edge_evidence(self, a: str, b: str) -> list[tuple[str, str, float]]:
        return self.evidence.get(_pair(a, b), [])


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _collect_identifier_map(
    accounts: pd.DataFrame, orders: pd.DataFrame
) -> dict[str, dict[str, set[str]]]:
    """identifier_type -> identifier_value -> set of account_ids."""
    idmap: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for col in ("email_norm", "phone"):
        for value, account_id in zip(accounts[col], accounts["account_id"], strict=True):
            if value:
                idmap[col][value].add(account_id)

    for col in ("device_id", "card_token", "ship_address_norm", "ip"):
        sub = orders[[col, "account_id"]].dropna()
        for value, account_id in zip(sub[col], sub["account_id"], strict=True):
            if value:
                idmap[col][value].add(account_id)

    return idmap


def build_identity_graph(
    accounts: pd.DataFrame,
    orders: pd.DataFrame,
    max_degree: int = MAX_IDENTIFIER_DEGREE,
    min_edge_weight: float = MIN_EDGE_WEIGHT,
) -> IdentityGraph:
    """Project the account-identifier bipartite graph onto accounts."""
    idmap = _collect_identifier_map(accounts, orders)

    graph = nx.Graph()
    graph.add_nodes_from(accounts["account_id"].tolist())

    evidence: dict[tuple[str, str], list[tuple[str, str, float]]] = defaultdict(list)
    dropped: dict[str, int] = defaultdict(int)
    degrees: dict[tuple[str, str], int] = {}
    pair_weight: dict[tuple[str, str], float] = defaultdict(float)

    for id_type, values in idmap.items():
        prior = IDENTIFIER_PRIORS.get(id_type, 0.3)
        for value, account_set in values.items():
            degree = len(account_set)
            degrees[(id_type, value)] = degree
            if degree < 2:
                continue
            if degree > max_degree:
                dropped[id_type] += 1
                continue

            contribution = prior / (degree - 1)
            members = sorted(account_set)
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    key = (members[i], members[j])
                    pair_weight[key] += contribution
                    evidence[key].append((id_type, value, contribution))

    for (a, b), weight in pair_weight.items():
        if weight >= min_edge_weight:
            graph.add_edge(a, b, weight=round(weight, 6))

    kept_evidence = {k: v for k, v in evidence.items() if graph.has_edge(*k)}

    return IdentityGraph(
        graph=graph,
        evidence=kept_evidence,
        dropped_identifiers=dict(dropped),
        identifier_degree=degrees,
    )

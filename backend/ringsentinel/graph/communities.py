"""Community detection over the weighted account graph.

Connected components are too coarse to act on: one slipped device links two
otherwise separate cells, and a single component can span several rings plus
innocent bystanders. We run weighted Louvain inside each component to carve it
into cohesive communities, which become the unit a human reviews.

Louvain is non-deterministic under ties, so the seed is fixed and recorded.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from .build import IdentityGraph


@dataclass
class Communities:
    """account_id -> community_id, plus per-community membership."""

    of_account: dict[str, int]
    members: dict[int, list[str]]
    seed: int

    def community_of(self, account_id: str) -> int | None:
        return self.of_account.get(account_id)

    def size_of(self, account_id: str) -> int:
        cid = self.of_account.get(account_id)
        return len(self.members[cid]) if cid is not None else 1


def detect_communities(
    identity: IdentityGraph, resolution: float = 1.0, seed: int = 20260904
) -> Communities:
    graph = identity.graph
    of_account: dict[str, int] = {}
    members: dict[int, list[str]] = {}
    next_id = 0

    for component in nx.connected_components(graph):
        sub = graph.subgraph(component)
        if len(component) <= 2:
            groups: list[set[str]] = [set(component)]
        else:
            groups = nx.community.louvain_communities(
                sub, weight="weight", resolution=resolution, seed=seed
            )
        for group in groups:
            members[next_id] = sorted(group)
            for account_id in group:
                of_account[account_id] = next_id
            next_id += 1

    return Communities(of_account=of_account, members=members, seed=seed)


def community_cohesion(identity: IdentityGraph, accounts: list[str]) -> float:
    """Mean internal edge weight of a community. High = tightly bound."""
    sub = identity.graph.subgraph(accounts)
    n = sub.number_of_nodes()
    if n < 2:
        return 0.0
    total = sum(d["weight"] for _, _, d in sub.edges(data=True))
    possible = n * (n - 1) / 2
    return float(total / possible)

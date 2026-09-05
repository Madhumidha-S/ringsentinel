"""Graph weighting: the decisions that stop shared infrastructure fusing everyone."""

from __future__ import annotations

import pandas as pd

from ringsentinel.graph.build import IDENTIFIER_PRIORS, build_identity_graph
from ringsentinel.simulator.entities import normalise_address, normalise_email


def _frames(order_rows):
    accounts = pd.DataFrame(
        [
            {"account_id": a, "email_norm": f"{a}@x.com", "phone": f"+9199{i:08d}"}
            for i, a in enumerate(sorted({r["account_id"] for r in order_rows}))
        ]
    )
    return accounts, pd.DataFrame(order_rows)


def _order(account_id, device="d0", card="c0", addr="a0", ip="i0"):
    return {
        "account_id": account_id, "device_id": device, "card_token": card,
        "ship_address_norm": addr, "ip": ip,
    }


def test_two_accounts_on_one_device_link_strongly():
    accounts, orders = _frames([_order("A"), _order("B")])
    g = build_identity_graph(accounts, orders)
    assert g.graph.has_edge("A", "B")
    # degree 2 -> contribution is the full prior for every shared identifier
    assert g.graph["A"]["B"]["weight"] > IDENTIFIER_PRIORS["device_id"]


def test_a_widely_shared_identifier_is_discounted_to_nothing():
    """A device touched by 60 accounts must not bind them into a ring."""
    rows = [_order(f"A{i}", device="kiosk", card=f"c{i}", addr=f"a{i}", ip=f"i{i}")
            for i in range(60)]
    accounts, orders = _frames(rows)
    g = build_identity_graph(accounts, orders)
    assert g.graph.number_of_edges() == 0, (
        "60 accounts sharing one kiosk device should fall below the edge threshold"
    )


def test_identifiers_above_the_degree_cap_are_dropped_entirely():
    rows = [_order(f"A{i}", device=f"d{i}", card=f"c{i}", addr=f"a{i}", ip="cgnat")
            for i in range(200)]
    accounts, orders = _frames(rows)
    g = build_identity_graph(accounts, orders)
    assert g.dropped_identifiers.get("ip", 0) == 1
    assert g.graph.number_of_edges() == 0


def test_edge_evidence_names_the_identifier_type():
    accounts, orders = _frames([_order("A"), _order("B")])
    g = build_identity_graph(accounts, orders)
    kinds = {t for t, _v, _c in g.edge_evidence("A", "B")}
    assert {"device_id", "card_token", "ship_address_norm"} <= kinds


def test_gmail_tricks_collapse_but_other_providers_keep_dots():
    assert normalise_email("r.a.hul+deals@gmail.com") == normalise_email("rahul@gmail.com")
    assert normalise_email("r.ahul@yahoo.in") != normalise_email("rahul@yahoo.in")


def test_address_normalisation_survives_cosmetic_variation():
    a = normalise_address("Flat 12B, 44 MG Road, Bengaluru 560001")
    b = normalise_address("flat 12b, 44 M.G. Road, Bangalore 560001")
    assert a == b

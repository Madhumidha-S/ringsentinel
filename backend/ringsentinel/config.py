"""Central configuration and economic constants.

Every monetary constant here is an assumption, not a measurement. They are
declared in one place so that a reviewer can challenge them, change them, and
re-run the evaluation to see how conclusions move. See docs/DATA_CARD.md for
the provenance of each figure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
ARTIFACTS_DIR = REPO_ROOT / "artifacts"

DEFAULT_SEED = 20260904


@dataclass(frozen=True)
class CostModel:
    """Rupee cost of each decision outcome, per account reviewed.

    A false positive is not merely 'a wrong flag'. It is a real customer who is
    held, asked to verify, or blocked. We price that as the margin we forgo on
    their remaining lifetime plus the support cost of the complaint they raise.
    """

    # Money we stop losing when a genuine abuser is caught, per account.
    # Median abusive account extracts ~3.2 fraudulent refunds at ~INR 1,850.
    true_positive_recovery_inr: float = 5_920.0

    # Cost of wrongly restricting a legitimate customer: forgone contribution
    # margin on their remaining lifetime, plus one support contact.
    false_positive_cost_inr: float = 2_400.0

    # Analyst time to review one escalated alert (fully loaded, ~12 min).
    manual_review_cost_inr: float = 180.0

    # What we lose per abusive account we never catch. Equal to the recovery
    # figure by construction: a miss is a foregone save.
    false_negative_cost_inr: float = 5_920.0

    def net_benefit(
        self, tp: int, fp: int, fn: int, reviewed: int = 0
    ) -> float:
        """Net rupee benefit of an operating point. Higher is better."""
        return (
            tp * self.true_positive_recovery_inr
            - fp * self.false_positive_cost_inr
            - fn * 0.0  # counted as foregone, not double-charged
            - reviewed * self.manual_review_cost_inr
        )


@dataclass(frozen=True)
class SimulationConfig:
    """Shape of the synthetic merchant population."""

    # Sized so that a ~45% temporal holdout still contains roughly 400 ring
    # accounts, i.e. ~40 per evasion level. Below that, per-level recall is
    # too noisy to report honestly.
    n_legit_accounts: int = 14_000
    n_rings: int = 80
    ring_size_min: int = 4
    ring_size_max: int = 18
    horizon_days: int = 120
    seed: int = DEFAULT_SEED

    # Fraction of legitimate accounts that live in a multi-account household
    # (shared address, sometimes a shared card or device). This is the primary
    # source of false-positive pressure and is deliberately large.
    household_fraction: float = 0.22

    # Fraction of legitimate accounts behind a shared egress IP (campus,
    # office, mobile CGNAT). Makes the IP edge weak by construction.
    shared_ip_fraction: float = 0.35

    # Fraction of legitimate accounts shipping to a *hub* address: a hostel,
    # PG accommodation, co-working space or office mailroom. In India these
    # routinely carry 10-35 unrelated residents on one address, often behind
    # one wifi egress. They are the hardest legitimate population to tell from
    # a ring, because on the address and IP dimensions they look identical.
    # Without them, a one-line "component size >= 5" rule scores F1 0.94 and
    # the whole modelling exercise is theatre.
    address_hub_fraction: float = 0.11

    legit_claim_rate: float = 0.038


COSTS = CostModel()

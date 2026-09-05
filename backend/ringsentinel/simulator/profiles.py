"""Adversary evasion profiles.

The central claim of this project is that a fraud detector's score is
meaningless without stating *which adversary* it was scored against. A ring
that reuses one device and one card is caught by a GROUP BY. A ring that
rotates infrastructure, splits below degree thresholds and waits out a
dormancy window is a genuinely hard problem.

We therefore parameterise the adversary on a 0-9 scale and report every metric
per level. Level 0 is the strawman most fraud demos are secretly scored on.
Level 9 is a competent operator who has read the same detection literature we
have.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_LEVEL = 0
MAX_LEVEL = 9


@dataclass(frozen=True)
class EvasionProfile:
    """How hard a ring works to avoid leaving a shared-identifier trail."""

    level: int
    device_rotation: float
    ip_rotation: float
    card_rotation: float
    address_jitter: float
    signup_spread_days: float
    max_shared_degree: int
    dormancy_days: float
    cover_order_ratio: float
    claim_rate: float
    slip_rate: float

    @property
    def label(self) -> str:
        if self.level <= 2:
            return f"L{self.level} (naive)"
        if self.level <= 5:
            return f"L{self.level} (moderate)"
        if self.level <= 7:
            return f"L{self.level} (evasive)"
        return f"L{self.level} (adaptive)"


# Anchor points. Everything between is linearly interpolated so that the
# difficulty curve is smooth and the degradation plot is readable.
_NAIVE = {
    "device_rotation": 0.02,
    "ip_rotation": 0.05,
    "card_rotation": 0.03,
    "address_jitter": 0.00,
    "signup_spread_days": 0.08,
    "max_shared_degree": 99,
    "dormancy_days": 0.5,
    "cover_order_ratio": 0.05,
    "claim_rate": 0.88,
    # Operational slippage: how often an account is touched from another
    # cell's device or ships to another cell's drop. This is the residual
    # signal that links cells together, and it is the main reason a
    # well-partitioned ring is detectable at all. Careless operators leak
    # constantly; disciplined ones almost never do.
    "slip_rate": 0.12,
}

# Maximum accounts an operator lets touch one device/card/address, by level.
#
# This is a table rather than an interpolation because it has to be calibrated
# against the actual ring sizes in the population (4-18 accounts). An earlier
# version interpolated 99 -> 3, which meant the cap only ever bound at level 9;
# every ring below that collapsed into a single cell and was trivially visible
# as one connected component. The schedule below bites across the whole range.
DEGREE_CAP_BY_LEVEL = [99, 14, 11, 9, 7, 6, 5, 4, 3, 2]

_ADAPTIVE = {
    "device_rotation": 0.86,
    "ip_rotation": 0.94,
    "card_rotation": 0.72,
    "address_jitter": 0.80,
    "signup_spread_days": 21.0,
    "max_shared_degree": 3,
    "dormancy_days": 16.0,
    "cover_order_ratio": 0.70,
    "claim_rate": 0.34,
    "slip_rate": 0.015,
}


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def profile_for(level: int) -> EvasionProfile:
    """Build the adversary profile for an evasion level in [0, 9]."""
    if not MIN_LEVEL <= level <= MAX_LEVEL:
        raise ValueError(f"evasion level must be in [{MIN_LEVEL}, {MAX_LEVEL}], got {level}")

    t = level / MAX_LEVEL
    values = {
        key: _lerp(_NAIVE[key], _ADAPTIVE[key], t)
        for key in _NAIVE
        if key != "max_shared_degree"
    }
    return EvasionProfile(
        level=level, max_shared_degree=DEGREE_CAP_BY_LEVEL[level], **values
    )


def all_profiles() -> list[EvasionProfile]:
    return [profile_for(level) for level in range(MIN_LEVEL, MAX_LEVEL + 1)]

"""Identity primitives: emails, phones, devices, cards, addresses, IPs.

Two ideas matter here.

1. Identifiers are *normalised* before they become graph edges, exactly as a
   real risk system would. Gmail dot/plus tricks collapse; addresses are
   canonicalised. A ring that relies on raw-string differences is caught by
   normalisation alone, which is why higher evasion levels stop relying on it.

2. Normalisation is imperfect on purpose. Address canonicalisation here is a
   realistic-but-lossy heuristic, not an oracle. If it were perfect, the graph
   would be perfect, and the detection problem would disappear.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

FIRST_NAMES = [
    "aarav", "vivaan", "aditya", "vihaan", "arjun", "reyansh", "krishna", "ishaan",
    "ananya", "diya", "aadhya", "myra", "sara", "ira", "kiara", "riya",
    "rahul", "priya", "neha", "karthik", "sneha", "rohan", "meera", "farhan",
    "zoya", "imran", "lakshmi", "ganesh", "divya", "nikhil", "tanvi", "yash",
]
LAST_NAMES = [
    "sharma", "verma", "patel", "reddy", "nair", "iyer", "menon", "gupta",
    "singh", "khan", "das", "bose", "rao", "pillai", "joshi", "shetty",
    "chauhan", "mehta", "kulkarni", "banerjee", "kapoor", "malhotra",
]
FREE_PROVIDERS = ["gmail.com", "yahoo.in", "outlook.com", "rediffmail.com", "hotmail.com"]
DISPOSABLE_PROVIDERS = ["mailinator.com", "tempmail.dev", "guerrillamail.com", "10mail.org"]

CITIES = [
    ("Bengaluru", "560001"), ("Mumbai", "400001"), ("Delhi", "110001"),
    ("Hyderabad", "500001"), ("Chennai", "600001"), ("Pune", "411001"),
    ("Kolkata", "700001"), ("Ahmedabad", "380001"), ("Jaipur", "302001"),
]
STREETS = [
    "MG Road", "Brigade Road", "Linking Road", "Park Street", "Anna Salai",
    "FC Road", "Residency Road", "Church Street", "Nehru Nagar", "Gandhi Marg",
]
CITY_ALIASES = {"Bengaluru": "Bangalore", "Mumbai": "Bombay", "Kolkata": "Calcutta",
                "Chennai": "Madras"}

_BIN_RANGES = ["411111", "522222", "601100", "353011", "455612", "540123"]


def _h(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:length]


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

def normalise_email(email: str) -> str:
    """Canonical form used for graph edges.

    Collapses the Gmail-family tricks (dots, +tags) that low-effort multi-
    accounting relies on. Non-Gmail providers get case folding only, matching
    what those providers actually do.
    """
    email = email.strip().lower()
    if "@" not in email:
        return email
    local, _, domain = email.partition("@")
    local = local.split("+", 1)[0]
    if domain in {"gmail.com", "googlemail.com"}:
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def make_email(rng: np.random.Generator, first: str, last: str, disposable: bool = False) -> str:
    provider = (
        rng.choice(DISPOSABLE_PROVIDERS) if disposable else rng.choice(FREE_PROVIDERS)
    )
    style = rng.integers(0, 4)
    if style == 0:
        local = f"{first}.{last}{rng.integers(1, 999)}"
    elif style == 1:
        local = f"{first}{last[:3]}{rng.integers(10, 9999)}"
    elif style == 2:
        local = f"{first}_{rng.integers(100, 99999)}"
    else:
        local = f"{last}{first[:2]}{rng.integers(1, 99)}"
    return f"{local}@{provider}"


def gmail_variant(rng: np.random.Generator, base_email: str) -> str:
    """A dot/plus variant of a Gmail address: distinct raw string, same inbox."""
    local, _, domain = base_email.partition("@")
    local = local.split("+", 1)[0].replace(".", "")
    if len(local) > 2 and rng.random() < 0.7:
        cut = int(rng.integers(1, len(local)))
        local = f"{local[:cut]}.{local[cut:]}"
    if rng.random() < 0.5:
        local = f"{local}+{rng.choice(['shop', 'deals', 'x', 'buy'])}{rng.integers(1, 99)}"
    return f"{local}@{domain}"


# --------------------------------------------------------------------------
# Address
# --------------------------------------------------------------------------

_ADDR_NOISE = re.compile(r"[^a-z0-9]+")
_ADDR_TOKENS = {
    "rd": "road", "st": "street", "mg": "mg", "apt": "flat", "apartment": "flat",
    "no": "", "hno": "", "opp": "", "near": "",
}


def normalise_address(raw: str) -> str:
    """Lossy canonicalisation, deliberately imperfect.

    Real address matching is one of the hardest parts of a risk stack. This
    handles case, punctuation, common abbreviations and city aliases, and fails
    on reordering and unit-number drift, which is roughly where a good
    heuristic matcher sits.
    """
    text = raw.lower()
    for canonical, alias in CITY_ALIASES.items():
        text = text.replace(alias.lower(), canonical.lower())
    tokens = [t for t in _ADDR_NOISE.split(text) if t]

    # Punctuated initialisms: "M.G. Road" splits to ["m", "g", "road"] while
    # "MG Road" gives ["mg", "road"], so the two spellings of the same street
    # would not match. Merge runs of single alphabetic characters back together.
    merged: list[str] = []
    run: list[str] = []
    for token in tokens:
        if len(token) == 1 and token.isalpha():
            run.append(token)
            continue
        if run:
            merged.append("".join(run))
            run = []
        merged.append(token)
    if run:
        merged.append("".join(run))

    tokens = [_ADDR_TOKENS.get(t, t) for t in merged]
    tokens = [t for t in tokens if t]
    return " ".join(tokens)


def make_address(rng: np.random.Generator) -> str:
    city, pin_base = CITIES[int(rng.integers(0, len(CITIES)))]
    pin = str(int(pin_base) + int(rng.integers(0, 90)))
    return (
        f"Flat {rng.integers(1, 40)}{rng.choice(list('ABCD'))}, "
        f"{rng.integers(1, 200)} {rng.choice(STREETS)}, {city} {pin}"
    )


def jitter_address(rng: np.random.Generator, raw: str) -> str:
    """Mutate an address so naive matching fails but a human sees one place."""
    out = raw
    roll = rng.random()
    if roll < 0.35:
        out = re.sub(r"Flat (\d+)", lambda m: f"#{m.group(1)}", out)
    elif roll < 0.6:
        out = out.replace("Road", "Rd.").replace("Street", "St")
    for canonical, alias in CITY_ALIASES.items():
        if canonical in out and rng.random() < 0.5:
            out = out.replace(canonical, alias)
    if rng.random() < 0.3:
        out = re.sub(r"Flat (\d+)([A-D])", lambda m: f"Flat {m.group(1)}, Block {m.group(2)}", out)
    if rng.random() < 0.25:
        # Unit-number drift: defeats normalisation regardless of street name.
        out = re.sub(
            r"Flat (\d+)([A-D])",
            lambda m: f"Flat {int(m.group(1)) + int(rng.integers(1, 4))}{m.group(2)}",
            out,
        )
    return out


# --------------------------------------------------------------------------
# Device / IP / card
# --------------------------------------------------------------------------

def make_device(rng: np.random.Generator) -> str:
    return "dev_" + _h(f"device{rng.integers(0, 2**62)}", 14)


def make_ip(rng: np.random.Generator) -> str:
    octets = (
        rng.integers(1, 224), rng.integers(0, 256), rng.integers(0, 256), rng.integers(1, 255)
    )
    return ".".join(str(o) for o in octets)


def make_card(rng: np.random.Generator) -> str:
    """Token standing in for a network fingerprint (BIN + last4 + hash).

    The trailing hash matters. Real card fingerprints are collision-free: two
    unrelated shoppers never share one. An earlier version of this generator
    used only BIN + last4, a 54,000-value space, which produced ~1,200
    accidental collisions across ~11,000 cards and fabricated graph edges
    between unrelated accounts. Card sharing in this dataset is now always
    deliberate - a household or a ring - never a birthday collision.
    """
    bin_ = _BIN_RANGES[int(rng.integers(0, len(_BIN_RANGES)))]
    suffix = _h(f"card{rng.integers(0, 2**62)}", 10)
    return f"card_{bin_}_{rng.integers(1000, 9999)}_{suffix}"


def make_phone(rng: np.random.Generator) -> str:
    return f"+91{rng.integers(6, 10)}{rng.integers(100000000, 999999999)}"


def make_name(rng: np.random.Generator) -> tuple[str, str]:
    return (
        FIRST_NAMES[int(rng.integers(0, len(FIRST_NAMES)))],
        LAST_NAMES[int(rng.integers(0, len(LAST_NAMES)))],
    )

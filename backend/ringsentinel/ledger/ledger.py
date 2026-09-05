"""Append-only, hash-chained decision ledger.

Every score, every action and every human override is written here before it
takes effect. Each entry carries the hash of its predecessor, so any silent
edit to history invalidates every subsequent link and `verify()` reports the
exact index where the chain breaks.

This is not cryptographic overkill for its own sake. A risk system that
restricts customer accounts has to be able to answer, months later and to
someone hostile, three questions: what did you do, what did you know when you
did it, and has this record been altered since. A plain log answers the first
two.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class LedgerEntry:
    index: int
    entry_id: str
    timestamp: float
    event_type: str
    account_id: str | None
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str = ""

    def compute_hash(self) -> str:
        body = {
            "index": self.index,
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "account_id": self.account_id,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass
class DecisionLedger:
    """Hash-chained ledger, optionally persisted to newline-delimited JSON."""

    path: Path | None = None
    entries: list[LedgerEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.path and self.path.exists():
            self._load()

    # -- writing ---------------------------------------------------------
    def append(
        self, event_type: str, payload: dict[str, Any], account_id: str | None = None
    ) -> LedgerEntry:
        prev_hash = self.entries[-1].entry_hash if self.entries else GENESIS_HASH
        entry = LedgerEntry(
            index=len(self.entries),
            entry_id=str(uuid.uuid4()),
            timestamp=time.time(),
            event_type=event_type,
            account_id=account_id,
            payload=payload,
            prev_hash=prev_hash,
        )
        entry = LedgerEntry(**{**asdict(entry), "entry_hash": entry.compute_hash()})
        self.entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(json.dumps(asdict(entry), separators=(",", ":")) + "\n")
        return entry

    # -- reading ---------------------------------------------------------
    def _load(self) -> None:
        assert self.path is not None
        self.entries = [
            LedgerEntry(**json.loads(line))
            for line in self.path.read_text().splitlines()
            if line.strip()
        ]

    def for_account(self, account_id: str) -> list[LedgerEntry]:
        return [e for e in self.entries if e.account_id == account_id]

    def verify(self) -> tuple[bool, str]:
        """Re-derive the chain. Returns (ok, human-readable detail)."""
        prev = GENESIS_HASH
        for i, entry in enumerate(self.entries):
            if entry.index != i:
                return False, f"entry {i}: index field is {entry.index}"
            if entry.prev_hash != prev:
                return False, f"entry {i}: prev_hash does not match entry {i - 1}"
            recomputed = entry.compute_hash()
            if recomputed != entry.entry_hash:
                return False, f"entry {i}: content altered (hash mismatch)"
            prev = entry.entry_hash
        return True, f"chain intact across {len(self.entries)} entries"

    def head(self) -> str:
        return self.entries[-1].entry_hash if self.entries else GENESIS_HASH

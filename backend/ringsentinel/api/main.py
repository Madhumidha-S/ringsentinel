"""FastAPI service backing the RingSentinel dashboard."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..agent.actions import ACTION_SPEC, PROHIBITED_AUTOMATIC_ACTIONS
from .engine import Engine

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine.build()
    return _engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Build the population, backtest and score before serving the first request."""
    get_engine()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="RingSentinel",
    version="0.1.0",
    description=(
        "Abuse-ring detection for merchant refund and promotion fraud. "
        "Defence-only: this service scores, explains and escalates. It cannot move money."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100", "http://127.0.0.1:3100"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReviewRequest(BaseModel):
    verdict: str = Field(..., pattern="^(confirm|clear|escalate)$")
    note: str = Field("", max_length=2000)
    reviewer: str = Field("analyst", max_length=120)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "engine_ready": _engine is not None}


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    return get_engine().overview()


@app.get("/api/evaluation")
def evaluation() -> dict[str, Any]:
    """Full backtest report: PR curve, cost curve, per-level recall, importances."""
    return get_engine().replay.report


@app.get("/api/alerts")
def alerts(
    band: str | None = Query(None, pattern="^(act|review)$"),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    engine = get_engine()
    return {"alerts": engine.alerts(band=band, limit=limit), "total": len(engine.decisions)}


@app.get("/api/accounts/{account_id}")
def account_detail(account_id: str, narrate: bool = True) -> dict[str, Any]:
    engine = get_engine()
    if account_id not in engine.scores:
        raise HTTPException(404, f"account {account_id} is not in the scored fold")
    packet = engine.evidence_for(account_id)
    decision = engine.decisions.get(account_id)
    narration = engine.narration_for(account_id) if narrate else None
    return {
        "account_id": account_id,
        "score": engine.scores[account_id],
        "evidence": packet.to_dict(),
        "decision": decision.to_dict() if decision else None,
        "action_effect": ACTION_SPEC[decision.action] if decision else None,
        "narration": (
            {"text": narration.text, "source": narration.source,
             "validation": narration.validation_note}
            if narration else None
        ),
        "ledger": [
            {"index": e.index, "event_type": e.event_type, "timestamp": e.timestamp,
             "payload": e.payload, "entry_hash": e.entry_hash[:16]}
            for e in engine.ledger.for_account(account_id)
        ],
        "ground_truth_is_ring": engine.truth.get(account_id),
    }


@app.get("/api/accounts/{account_id}/graph")
def account_graph(account_id: str, max_nodes: int = Query(40, ge=2, le=120)) -> dict[str, Any]:
    engine = get_engine()
    if account_id not in engine.scores:
        raise HTTPException(404, f"account {account_id} is not in the scored fold")
    return engine.subgraph(account_id, max_nodes=max_nodes)


@app.post("/api/accounts/{account_id}/review")
def submit_review(account_id: str, body: ReviewRequest) -> dict[str, Any]:
    engine = get_engine()
    if account_id not in engine.scores:
        raise HTTPException(404, f"account {account_id} is not in the scored fold")
    return engine.record_review(account_id, body.verdict, body.note, body.reviewer)


@app.get("/api/ledger")
def ledger(limit: int = Query(200, ge=1, le=2000)) -> dict[str, Any]:
    engine = get_engine()
    ok, detail = engine.ledger.verify()
    entries = engine.ledger.entries[-limit:]
    return {
        "verified": ok,
        "detail": detail,
        "head": engine.ledger.head(),
        "total_entries": len(engine.ledger.entries),
        "entries": [
            {"index": e.index, "event_type": e.event_type, "account_id": e.account_id,
             "timestamp": e.timestamp, "payload": e.payload,
             "prev_hash": e.prev_hash[:16], "entry_hash": e.entry_hash[:16]}
            for e in entries
        ],
    }


@app.get("/api/policy")
def policy() -> dict[str, Any]:
    """The action set and the things this system refuses to do automatically."""
    engine = get_engine()
    return {
        "thresholds": {
            "review": round(engine.review_threshold, 4),
            "action": round(engine.action_threshold, 4),
        },
        "actions": {a.value: spec for a, spec in ACTION_SPEC.items()},
        "prohibited_automatic_actions": PROHIBITED_AUTOMATIC_ACTIONS,
        "posture": (
            "Defence only. The system detects, explains and escalates. It has no "
            "capability to move funds, close accounts or contact customers directly."
        ),
    }

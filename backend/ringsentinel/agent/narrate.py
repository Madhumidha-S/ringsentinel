"""Grounded narration of an evidence packet.

An LLM writing free-form fraud accusations is a liability, so this module
constrains it in three ways:

1. The prompt carries **only** the evidence packet. The model never sees the
   dataset, the label, or any account it was not asked about.
2. Every account id and identifier reference in the output is checked against
   the packet's citable set. A narration that invents a reference is rejected
   outright rather than shown with a warning.
3. If the API key is absent, the call fails, or validation rejects the output,
   we fall back to a deterministic template built from the same evidence. The
   product degrades to "less fluent", never to "unavailable" and never to
   "plausible-sounding fiction".

The narration is a rendering of the evidence. It is never itself evidence, and
it has no influence on the decision - the action is chosen before this runs.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from .evidence import EvidencePacket

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 500

SYSTEM_PROMPT = """You are a fraud analyst writing the summary line of a case file.

You will be given a JSON evidence packet about one account suspected of \
refund or promotion abuse. Write 2-4 sentences explaining what the evidence \
shows and what was decided.

Hard rules:
- Use ONLY facts present in the packet. Invent nothing.
- Refer to accounts only by the exact ids given. Never invent an id.
- Do not state that the account IS fraudulent. State what the evidence shows.
  This is a suspicion under review, not a finding.
- If the packet's sufficiency is "weak" or "insufficient", say plainly that the
  evidence does not support an automated conclusion.
- No preamble, no bullet points, no markdown. Plain prose only.
- Mention the single most important linking identifier type and the cluster size.
"""

_ID_PATTERN = re.compile(r"\b(?:acc_[A-Za-z0-9_]+|[0-9a-f]{10})\b")


@dataclass
class Narration:
    text: str
    source: str  # "llm" | "template" | "template_after_rejection"
    validation_note: str = ""


def _template(packet: EvidencePacket) -> str:
    top_link = packet.links[0] if packet.links else None
    parts: list[str] = []

    if top_link:
        n_same = sum(1 for link in packet.links if link.identifier_type == top_link.identifier_type)
        parts.append(
            f"Account {packet.account_id} is linked to {len(packet.peers)} other account(s) "
            f"in a cluster of {packet.community_size}, most strongly via "
            f"{top_link.description} (shared with {n_same} link(s), reference "
            f"{top_link.identifier_ref})."
        )
    else:
        parts.append(
            f"Account {packet.account_id} has no identity links to other accounts on record."
        )

    facts = packet.facts
    parts.append(
        f"It has {facts['orders']} order(s) and {facts['claims']} refund claim(s) "
        f"({facts['claim_rate']:.0%} of orders), with INR "
        f"{facts['granted_refunds_inr']:,.0f} refunded to date."
    )

    if packet.contributing_factors:
        top = packet.contributing_factors[0]
        parts.append(f"Most notably, it {top['statement']}.")

    if packet.sufficiency in ("weak", "insufficient"):
        parts.append(
            f"The evidence is {packet.sufficiency} and does not support an automated "
            f"conclusion: {packet.sufficiency_reason}."
        )
    else:
        parts.append(
            f"Evidence is assessed as {packet.sufficiency}: {packet.sufficiency_reason}."
        )
    return " ".join(parts)


def _validate(text: str, packet: EvidencePacket) -> tuple[bool, str]:
    """Reject any narration citing a reference that is not in the packet."""
    citable = packet.citable_ids()
    cited = set(_ID_PATTERN.findall(text))
    invented = cited - citable
    if invented:
        listed = ", ".join(sorted(invented)[:5])
        return False, (
            f"narration cited {len(invented)} reference(s) not in the packet: {listed}"
        )
    if len(text.strip()) < 40:
        return False, "narration too short to be a useful summary"
    return True, "all cited references present in the evidence packet"


def narrate(packet: EvidencePacket, allow_llm: bool = True) -> Narration:
    """Produce a grounded, human-readable summary of one evidence packet."""
    if not allow_llm or not os.environ.get("ANTHROPIC_API_KEY"):
        return Narration(
            _template(packet),
            "template",
            "LLM narration not attempted (no ANTHROPIC_API_KEY set); "
            "deterministic template used.",
        )

    try:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(packet.to_dict(), indent=2, default=str),
                }
            ],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
    except Exception as exc:
        return Narration(
            _template(packet),
            "template",
            f"LLM narration failed ({type(exc).__name__}); fell back to template.",
        )

    ok, note = _validate(text, packet)
    if not ok:
        return Narration(_template(packet), "template_after_rejection", f"Rejected: {note}")
    return Narration(text, "llm", note)

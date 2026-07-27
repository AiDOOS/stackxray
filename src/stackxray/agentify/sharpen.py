"""Optional LLM sharpening of the top Agentify opportunities.

Upgrades the templated "why" / "what an agent would do" into a specific, code-aware
assessment - but only if the customer set an API key (Claude or OpenAI). With no key, the
opportunities pass through unchanged (the heuristic reasoning still stands). Best-effort:
any failure leaves the heuristic text in place, so the scan never breaks.
"""

from __future__ import annotations

import os

from ..llm_client import ask, available
from ..models import Capability
from . import Opportunity

_SYSTEM = ("You assess software capabilities for 'agentify' potential - whether the work "
           "could be rebuilt as an AI agent. Be specific and concise. No preamble.")

_MAX_CTX = 1800


def _context(repo_path: str, cap: Capability) -> str:
    """A code excerpt for the model to judge - the BIGGEST file in the capability, not just the
    first. A domain unit spans several files (`purchase_order.py`, `mapper.py`, ...), and the
    first happened to be `mapper.py` - a field mapper, pure plumbing - so the model read the
    dullest slice and dropped genuinely strong candidates (purchase order, sales order) on it.
    The largest file is the best single proxy for where the real logic lives."""
    candidates = list(cap.paths)
    for e in cap.evidence:
        if e.source == "extract" and e.locator:
            candidates.append(e.locator)
    best, best_size = "", -1
    for rel in dict.fromkeys(candidates):            # de-dup, keep order
        fp = os.path.join(repo_path, rel)
        try:
            size = os.path.getsize(fp)
        except OSError:
            continue
        if size > best_size:
            best, best_size = fp, size
    if not best:
        return ""
    try:
        with open(best, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()[:_MAX_CTX]
    except OSError:
        return ""


def _apply(opp: Opportunity, reply: str) -> None:
    why = agent = None
    for line in reply.splitlines():
        s = line.strip()
        if s.upper().startswith("WHY:"):
            why = s.split(":", 1)[1].strip()
        elif s.upper().startswith("AGENT:"):
            agent = s.split(":", 1)[1].strip()
    if why:
        opp.reason = why
    if agent:
        opp.agent_summary = agent
    if not (why or agent) and reply.strip():
        opp.reason = reply.strip()


def sharpen(opps: list[Opportunity], repo_path: str, top_n: int = 8) -> list[Opportunity]:
    """Enrich the top-N opportunities' reasoning via the customer's model (if a key is set)."""
    if not available():
        return opps
    for opp in opps[:top_n]:
        ctx = _context(repo_path, opp.capability)
        prompt = (f"Capability: {opp.capability.name}\n\nCode excerpt:\n{ctx or '(unavailable)'}\n\n"
                  "Answer in exactly two lines:\n"
                  "WHY: why this is (or isn't) a strong candidate to rebuild as an AI agent.\n"
                  "AGENT: what an AI agent would concretely do here.")
        reply = ask(_SYSTEM, prompt)
        if reply:
            _apply(opp, reply)
    return opps

"""Verdict engine (SPEC §8) - assign keep/retire/consolidate/agentify/buy + confidence.

Consumes join-enriched capabilities and produces an honest verdict per capability, each
with a confidence level and the evidence behind it (SPEC §4.4). This module is where the
HONESTY FIREWALL lives (SPEC §4.2): it must be free to say keep / buy-a-SaaS / don't-
agentify / don't-hire-AiDOOS, with zero awareness of sales incentive.

All five tiers implemented. Precedence (most decisive first):
  aggregate node -> RETIRE -> CONSOLIDATE -> AGENTIFY -> KEEP -> BUY_REPLACE -> UNDECIDED
Rationale: a dead thing is just killed (RETIRE) even if redundant; a live redundant thing
is consolidated; a live non-AI toil capability is an agentify candidate; otherwise keep;
BUY_REPLACE is a conservative fallback for commodity code we have no runtime signal on;
no evidence -> UNDECIDED, never a forced call.
"""

from __future__ import annotations

from ..models import (
    Capability,
    Confidence,
    Evidence,
    Level,
    Verdict,
    confidence_rank,
)
from .clustering import PortfolioTag, analyze_portfolio, is_agentify_candidate

# A window shorter than this is too small to trust a "0 requests" as "dead" (SPEC §7/§8).
MIN_RETIRE_WINDOW_DAYS = 30


def _is_dead(cap: Capability) -> bool:
    """RETIRE gate: 0 requests over a trustworthy window on a confidently-joined service
    (SPEC §7/§8). Requires RUNTIME evidence - code absence alone never qualifies."""
    u = cap.usage
    return (
        u is not None
        and u.requests == 0
        and (u.window_days or 0) >= MIN_RETIRE_WINDOW_DAYS
        and confidence_rank(cap.join_confidence) >= confidence_rank(Confidence.MEDIUM)
    )


def _verdict_one(cap: Capability, tag: PortfolioTag | None) -> Capability:
    # Roll-up nodes (portfolio/product) aggregate from children (SPEC §5/§8).
    if cap.level != Level.CAPABILITY:
        cap.verdict = Verdict.UNDECIDED
        cap.evidence.append(Evidence("verdict", "aggregate node - verdict rolls up from children"))
        return cap

    # 0) NOT READ - we have no parser for this file type, so we assessed nothing. The honest
    #    state is UNDECIDED. Falling through to KEEP would print "no action indicated from the
    #    code" about code we never parsed - the same overclaim as inventing a finding, and the
    #    reader cannot tell the difference between "we looked and it's fine" and "we couldn't
    #    look at all". That distinction is the whole product.
    if not cap.readable:
        cap.verdict, cap.confidence = Verdict.UNDECIDED, Confidence.LOW
        cap.evidence.append(Evidence(
            "verdict", "UNDECIDED: StackXray has no parser for this file type, so nothing here "
                       "was assessed. This is a gap in our coverage, not a finding about your "
                       "code."))
        return cap

    usage = cap.usage

    # 1) RETIRE - dead with runtime proof beats every other signal.
    if _is_dead(cap):
        cap.verdict, cap.confidence = Verdict.RETIRE, cap.join_confidence
        cap.evidence.append(Evidence(
            "verdict", f"RETIRE: 0 requests over {usage.window_days}d on a confidently-joined service"))
        return cap

    # 2) CONSOLIDATE - part of a redundancy cluster (category or cross-cloud).
    if tag and tag.verdict == Verdict.CONSOLIDATE:
        cap.verdict, cap.confidence = Verdict.CONSOLIDATE, tag.confidence
        cap.redundancy_cluster = tag.cluster_id
        cap.evidence.append(Evidence("verdict", f"CONSOLIDATE: {tag.reason}"))
        return cap

    live = usage is not None and (usage.requests or 0) > 0

    # 3) BUY_REPLACE - commodity code better bought than owned. Ranked ABOVE agentify on
    #    purpose: if it is a commodity, the answer is buy it, not build an agent for it.
    #    Deliberately NOT applied to a capability we can SEE is load-bearing: telling someone
    #    to rip out a working production system on a code smell alone is exactly the kind of
    #    overclaim the honesty firewall exists to prevent. Live commodity -> KEEP.
    if tag and tag.verdict == Verdict.BUY_REPLACE and not live:
        cap.verdict, cap.confidence = Verdict.BUY_REPLACE, tag.confidence
        cap.evidence.append(Evidence("verdict", f"BUY/REPLACE candidate: {tag.reason}"))
        return cap

    # 4) AGENTIFY - non-AI toil worth rebuilding as an agent.
    #    Candidacy comes from the tuned code-only scorer (agentify.score_one), NOT from runtime:
    #    the old gate required observed traffic, so a code-only scan produced ZERO agentify
    #    candidates - the reason a code-only X-ray had nothing to say.
    #    Confidence stays LOW even with traffic: agentify is a CANDIDATE whose value and
    #    feasibility need human/LLM review (SPEC §8). Runtime strengthens the EVIDENCE, not the
    #    claim. `potential` (high/medium) carries the strength of the code signal separately.
    from ..agentify import score_one as _agentify_score
    opp = _agentify_score(cap)
    if opp:
        cap.verdict, cap.confidence = Verdict.AGENTIFY, Confidence.LOW
        proof = (f" - load-bearing ({usage.requests} requests/{usage.window_days}d)" if live
                 else " - code-only signal; runtime evidence would confirm value")
        cap.evidence.append(Evidence("verdict", f"AGENTIFY ({opp.potential}): {opp.reason}{proof}"))
        return cap

    # 5) KEEP - nothing actionable applies. Two DIFFERENT claims, and we must not conflate them:
    #      with runtime  -> "confirmed load-bearing" (strong; N requests over M days)
    #      code only     -> "no action indicated from the code" (honest, weaker: we are saying
    #                       we found nothing to change, NOT that we proved it is used).
    #    KEEP used to require usage, which dumped every healthy capability into UNDECIDED on a
    #    code-only scan - the wall of grey. A code-only scan CAN say "no action indicated".
    if usage is not None and (usage.requests or 0) > 0:
        cap.verdict, cap.confidence = Verdict.KEEP, cap.join_confidence
        cap.evidence.append(Evidence(
            "verdict", f"KEEP: {usage.requests} requests over {usage.window_days}d - load-bearing"))
        return cap

    cap.verdict, cap.confidence = Verdict.KEEP, Confidence.LOW
    cap.evidence.append(Evidence(
        "verdict", "KEEP: no action indicated from the code - not redundant, not agent-suited, "
                   "not commodity. (Whether it is still USED needs runtime evidence.)"))
    return cap


def assign_verdicts(capabilities: list[Capability]) -> list[Capability]:
    """Set verdict + confidence + evidence on each capability (SPEC §8).

    Runs the portfolio pass once (redundancy clusters + commodity candidates), then
    decides each capability with the documented precedence.
    """
    tags = analyze_portfolio(capabilities)
    return [_verdict_one(cap, tags.get(cap.id)) for cap in capabilities]

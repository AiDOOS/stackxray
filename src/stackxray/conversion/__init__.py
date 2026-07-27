"""The conversion button (SPEC §9) - "What would it take to do this?"

Every verdict gets this action. v1 (ledger still thin): generate a draft scope + rough
range, then route to the AiDOOS proposal engine. Later: instant precise time/cost/DUs
from the calibration ledger. The action is an EXPLICIT, consent-gated click in the local
report - nothing leaves until pressed (SPEC §9).

v1 status: IMPLEMENTED - local draft-proposal mode. Fully offline (no egress); the
precise, consented estimate is cloud.request_estimate (M5). Never headlines a hard number
as a promise (SPEC §4.4).
"""

from __future__ import annotations

from ..models import Capability, Verdict

# What acting on each verdict actually means, plus the rough steps a scoping pass expands.
_ACTIONS: dict[Verdict, tuple[str, list[str]]] = {
    Verdict.RETIRE: ("Decommission and remove", [
        "Confirm zero consumers (extend the observation window if needed)",
        "Remove the deploy config / service, then delete the code",
        "Watch for regressions after cut-over",
    ]),
    Verdict.CONSOLIDATE: ("Consolidate into one shared implementation", [
        "Pick the surviving implementation in the redundancy cluster",
        "Migrate callers of the others onto it",
        "Retire the now-unused duplicates",
    ]),
    Verdict.AGENTIFY: ("Rebuild as an AI agent", [
        "Confirm the value/usage justifies the rebuild",
        "Design the agent + guardrails; keep the current path as fallback",
        "Roll out behind a flag, measure, then cut over",
    ]),
    Verdict.BUY_REPLACE: ("Replace with a bought SaaS", [
        "Shortlist SaaS options for this commodity capability",
        "Build the integration; migrate data/traffic",
        "Retire the maintained code",
    ]),
    Verdict.KEEP: ("No action - keep as-is", [
        "Healthy and load-bearing; revisit if usage or cost changes",
    ]),
    Verdict.UNDECIDED: ("Gather evidence before deciding", [
        "Connect observability (or import usage) so a verdict can be earned",
        "Re-scan to upgrade this from 'exists' to a real verdict",
    ]),
}

# Rough order-of-magnitude effort by structural size - a DRAFT, not a quote (SPEC §4.4/§15).
_EFFORT = {"small": ("S", "days"), "medium": ("M", "1-3 weeks"), "large": ("L", "1-2 months")}


def draft_scope(capability: Capability) -> dict:
    """Local draft scope + rough range for acting on this capability's verdict.

    Deterministic and offline. The precise time/cost comes later from the calibration
    ledger via a CONSENTED cloud call (SPEC §9); this is the pre-consent draft.
    """
    action, steps = _ACTIONS.get(capability.verdict, _ACTIONS[Verdict.UNDECIDED])
    tshirt, rough = _EFFORT.get((capability.size_complexity or "").lower(), ("?", "unknown"))
    no_action = capability.verdict in (Verdict.KEEP, Verdict.UNDECIDED)
    return {
        "capability": capability.name,
        "verdict": capability.verdict.value,
        "action": action,
        "steps": steps,
        "effort": None if no_action else tshirt,
        "rough_range": None if no_action else rough,
        "note": ("Draft only - a precise time/cost estimate needs an AiDOOS scoping pass "
                 "(or the consented cross-customer benchmark). No numbers here are a promise."),
    }

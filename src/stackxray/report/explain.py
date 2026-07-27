"""Plain-language explanation for every capability (report layer).

Three deterministic strings per capability - no LLM required (an LLM only makes the
description prettier if a key is present):
  - describe(): what this capability IS.
  - why():      the justification for its verdict (KEEP/RETIRE/CONSOLIDATE/AGENTIFY/BUY/…).
  - resolve_hint(): for UNDECIDED, exactly what to provide to earn a verdict.

The point: no verdict is a bare label. "Agentify" says why it's agentify; "Undecided"
says why, and how to fix it.
"""

from __future__ import annotations

from ..models import AIClass, Capability, Kind, Runtime, Verdict

# role keyword (from a capability's name suffix) -> what that role does
_ROLE_PURPOSE = [
    ("data model", "Defines the data schema and persistence."),
    ("copybook", "Shared data-structure definitions."),
    ("api", "Exposes HTTP endpoints / request handling."),
    ("controller", "Exposes HTTP endpoints / request handling."),
    ("view", "Exposes HTTP endpoints / request handling."),
    ("handler", "Exposes HTTP endpoints / request handling."),
    ("service", "Business-logic / service layer."),
    ("background job", "Asynchronous jobs and workers."),
    ("management command", "Operational / CLI commands."),
    ("program", "Legacy batch/online programs."),
    ("header", "Public interfaces / headers."),
    ("implementation", "Implementation code."),
    ("component", "UI components."),
    ("state", "Client-side state management."),
    ("page", "Pages / routes."),
    ("hook", "Reusable UI hooks."),
    ("storage", "Data access / storage."),
    ("data", "Data access / persistence."),
    ("core", "Core module logic."),
]


def _role(cap: Capability) -> str:
    return cap.name.split(": ", 1)[1] if ": " in cap.name else cap.name


def _role_purpose(cap: Capability) -> str:
    role = _role(cap).lower()
    for kw, sentence in _ROLE_PURPOSE:
        if kw in role:
            return sentence
    return "Module logic."


def _product(cap: Capability) -> str:
    return cap.name.split(": ", 1)[0] if ": " in cap.name else "this app"


def _usage_phrase(cap: Capability) -> str:
    u = cap.usage
    if not u or u.requests is None:
        return "no usage data"
    return f"{u.requests:,} requests over {u.window_days or '?'}d ({u.source})"


def _deployment_phrase(cap: Capability) -> str:
    u = cap.usage
    if u and u.source == "access-log":
        return "Reached via the app's routes."
    if cap.deployed_service and cap.runtime == Runtime.VM:
        return f"Runs as VM service '{cap.deployed_service}'."
    if cap.deployed_service and cap.runtime == Runtime.CONTAINER:
        on = f" on {cap.cloud_environment}" if cap.cloud_environment else ""
        return f"Runs as container service '{cap.deployed_service}'{on}."
    return ""


def describe(cap: Capability) -> str:
    """What this capability is. Uses the LLM's inferred purpose when present, else builds a
    structural description from kind/role/size/deps/deployment."""
    if cap.inferred_purpose:
        return cap.inferred_purpose

    if "(not yet extracted)" in cap.name:
        return (f"{_role(cap).replace(' (not yet extracted)', '')} - present in the repo but "
                "not yet parsed by a native extractor. Add an LLM key to extract it.")

    if cap.kind == Kind.INTEGRATED_SAAS:
        vendor = _role(cap).replace(" integration", "")
        return f"Integration glue to {vendor}. The {vendor} code isn't in the repo; the outbound integration is."

    if cap.kind == Kind.BOUGHT_SAAS:
        vendor = _role(cap)
        cost = f" {cap.est_effort_to_act}." if cap.est_effort_to_act else ""
        return f"Third-party SaaS ({vendor}) with no code footprint.{cost} {_usage_phrase(cap)}.".strip()

    # built code
    bits = [_role_purpose(cap)]
    if cap.size_complexity:
        bits.append(f"~{cap.size_complexity} size.")
    if cap.ai_or_not == AIClass.AI:
        bits.append("AI-based.")
    if cap.dependencies:
        bits.append(f"Integrates {', '.join(cap.dependencies[:4])}.")
    deploy = _deployment_phrase(cap)
    if deploy:
        bits.append(deploy)
    return " ".join(bits)


def _verdict_reason(cap: Capability) -> str:
    """The reason string the verdict engine recorded, minus its label prefix."""
    for e in reversed(cap.evidence):
        if e.source in ("verdict", "monolith"):
            detail = e.detail
            return detail.split(":", 1)[1].strip() if ":" in detail else detail
    return ""


def why(cap: Capability) -> str:
    v = cap.verdict
    if v == Verdict.RETIRE:
        return (f"No traffic - {_usage_phrase(cap)} on {cap.deployed_service or 'its service'}. "
                "Dead in production; safe to decommission.")
    if v == Verdict.KEEP:
        return f"Load-bearing - {_usage_phrase(cap)}. Healthy; no action needed."
    if v == Verdict.CONSOLIDATE:
        return _verdict_reason(cap) or "Overlaps other capabilities in the same category; stitch into fewer."
    if v == Verdict.AGENTIFY:
        return (f"Actively used ({_usage_phrase(cap)}), non-AI {_role(cap)} of "
                f"{cap.size_complexity or 'notable'} size - high-value toil and a strong candidate to "
                "rebuild as an AI agent. Confirm value/feasibility before acting.")
    if v == Verdict.BUY_REPLACE:
        return _verdict_reason(cap) or "Commodity capability - likely cheaper to buy than to maintain."
    if v == Verdict.UNDECIDED:
        u = cap.usage
        if u is not None and u.requests is not None:
            return "Runtime signal present but the observation window is too short to trust a verdict."
        return "No runtime evidence is connected for this capability, so a verdict can't be earned yet."
    return _verdict_reason(cap)


def resolve_hint(cap: Capability) -> str | None:
    """For UNDECIDED: exactly what to provide to earn a verdict (turns the wall into a to-do)."""
    if cap.verdict != Verdict.UNDECIDED:
        return None
    u = cap.usage
    if u is not None and u.requests is not None:
        return "Extend the observation window to at least 30 days and re-scan."
    if cap.kind == Kind.BOUGHT_SAAS:
        return "Add an SSO or egress export to confirm whether this SaaS is actually used."
    return ("Connect a runtime source that covers this - an access-log export (for routes), "
            "or a Prometheus/OTel/Datadog query (for services).")

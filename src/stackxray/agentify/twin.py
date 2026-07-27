"""Digital-twin lens - the companion question to agentify.

Agentify asks: which capabilities are a repetitive process an agent could run (with the
deterministic rules kept as code)? This asks the complement: which capabilities are really a
SYSTEM worth MODELLING - a live digital replica you monitor, simulate, and decide against?

Settled definition (aligned with the research + Beverly/Joseph):
  - An AGENT ACTS: it runs a process and produces an action. Operational.
  - A digital TWIN MODELS: a live replica of a system that informs decisions - and at the top
    ("autonomous") tier, makes the higher-level calls a scarce human (up to the C-suite) makes
    today. It removes the DECISION bottleneck, not the transaction.

Two honest signals, from code alone:
  - a PHYSICAL / operational domain (sensors, equipment, fleet, inventory, production, energy):
    a twin models the real-world asset or process so it can be simulated and optimised.
  - a SYSTEM-MODELLING domain (forecasting, planning, capacity, portfolio, allocation, budgeting,
    consolidation, scenario/what-if): a twin models the business system so the higher-level calls
    are made against live state, not a static report.

A bare human APPROVAL is NOT a twin - it is operational, so it belongs to the agent lens. That was
the loose signal we removed. A capability can still be BOTH an agent and a twin candidate (run the
transactions with an agent; model the system with a twin) - that is a finding, not a conflict.

Never invents value in money or headcount (not in the code); it states the OUTCOME only.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Capability, Kind
from . import _INFRA_DENY, _EFFORT, _domain_hit, _product, _role, _role_base, _text
from ..naming import pretty

# A PHYSICAL asset or operational process - the real-world thing a twin would model. Concrete
# physical nouns, so this does not fire on ordinary back-office software.
_PHYSICAL_DOMAINS = {
    "sensor", "iot", "telemetry", "device", "equipment", "machine", "motor", "pump", "turbine",
    "valve", "compressor", "boiler", "hvac", "robot", "actuator", "plc", "scada",
    "fleet", "vehicle", "truck", "trailer", "container", "cargo", "freight", "shipment",
    "logistics", "warehouse", "inventory", "stock", "pallet", "yard", "dock", "port", "terminal",
    # NOT the bare word "asset": every web app has an `assets/` folder of JS/CSS, and on a real
    # scan (akaunting) that one word turned 20 Vue UI components into "physical twin" rows. The
    # physical meaning survives as the specific phrases below.
    "asset tracking", "asset management", "fixed asset",
    "meter", "plant", "facility", "factory", "production", "assembly", "batch",
    "maintenance", "downtime", "uptime", "throughput", "yield",
    "energy", "grid", "power", "pipeline", "well", "drilling", "refinery", "reactor",
    "elevator", "escalator", "turnstile", "hospital", "bed", "ward",
}
# A BUSINESS SYSTEM worth modelling for the higher-level (up to C-suite) decisions - the thing a
# twin removes the bottleneck on. Planning/forecasting/simulation words, not transaction words.
_SYSTEM_DOMAINS = {
    "forecast", "forecasting", "planning", "planner", "scenario", "simulation", "simulate",
    "optimi", "portfolio", "allocation", "allocat", "budget", "budgeting", "consolidat",
    "projection", "roster", "scheduling", "capacity", "utilization", "utilisation", "balancing",
    "sensitivity", "what-if", "whatif", "demand plan", "s&op", "workforce", "resource plan",
}

_SIZE_BONUS = {"large": 26, "medium": 16, "small": 6}


@dataclass
class TwinOpportunity:
    """A capability better served by a digital twin than by an agent - a system to model, not a
    process to run."""
    capability: Capability
    twin_kind: str      # "physical" | "system"
    summary: str        # what the twin would model
    value: str          # how that helps - never a fabricated number
    score: int
    effort: str         # S | M | L

    @property
    def title(self) -> str:
        cap = self.capability
        if cap.domain_unit:
            # Pretty each side of the colon SEPARATELY - prettifying "hrms: telemetry" whole leaves
            # the colon stuck to "hrms" so the acronym never fires ("Hrms" instead of "HRMS").
            return f"{pretty(_product(cap))}: {pretty(cap.domain_unit)}"
        from ..naming import pretty_capability
        return pretty_capability(cap.name)


def _is_candidate_shape(cap: Capability) -> bool:
    """Real, readable, built work - not a data model, not infra/UI glue.

    The role is checked from `cap.role` FIRST, same as the agentify scorer, and a domain unit
    does NOT bypass it: a Vue component folder is a domain unit too, and on a real scan
    (akaunting) letting units through turned UI components into twin rows. A twin models a
    SYSTEM; a screen is not a system, whatever its folder is called.
    """
    if cap.kind != Kind.BUILT or not getattr(cap, "readable", True):
        return False
    if cap.level.value != "capability":
        return False
    text = _text(cap)
    if _domain_hit(text, _INFRA_DENY):
        return False
    return _role_base(cap.role or _role(cap)) >= 20


def _physical_summary(cap: Capability, hit: str) -> tuple[str, str]:
    subject = cap.domain_unit or _role(cap)
    summary = (f"A digital twin would model your {subject} as a live picture - the state of the "
               f"real {hit} it tracks - so it can be simulated and optimised, not just recorded.")
    value = (f"Gives the people running the {hit} a running model to test decisions against "
             f"before they act, and a feed a physical twin can drive.")
    return summary, value


def _system_summary(cap: Capability, hit: str) -> tuple[str, str]:
    subject = cap.domain_unit or _role(cap)
    summary = (f"A digital twin would model your {subject} as a live picture of the whole system - "
               f"its real-time state - so you can run what-if scenarios and make the higher-level "
               f"calls against it, rather than off a static report after the fact.")
    value = ("Gives the people who own these calls - up to the top of the org - a live model to "
             "simulate and decide against. This is the decision layer, not the transaction.")
    return summary, value


def assess_twins(capabilities: list[Capability], limit: int | None = None) -> list[TwinOpportunity]:
    """Which capabilities suit a DIGITAL TWIN: a system to model, physical or business. Ranked;
    deterministic and code-only (no key needed). A bare human approval does NOT qualify - that is
    the agent lens."""
    out: list[TwinOpportunity] = []
    for cap in capabilities:
        if not _is_candidate_shape(cap):
            continue
        text = _text(cap)
        physical = _domain_hit(text, _PHYSICAL_DOMAINS)
        system = _domain_hit(text, _SYSTEM_DOMAINS)
        if not (physical or system):
            continue

        size = cap.size_complexity or "small"
        if physical:
            summary, value = _physical_summary(cap, physical)
            kind, score = "physical", 62 + _SIZE_BONUS.get(size, 6)
        else:
            summary, value = _system_summary(cap, system)
            kind, score = "system", 60 + _SIZE_BONUS.get(size, 6)
        if physical and system:
            score += 6
        out.append(TwinOpportunity(capability=cap, twin_kind=kind, summary=summary,
                                   value=value, score=min(score, 100), effort=_EFFORT.get(size, "M")))

    out.sort(key=lambda t: (-t.score, t.title))
    return out[:limit] if limit else out

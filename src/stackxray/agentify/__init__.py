"""Agentify assessment (V1 headline) - from code alone, which capabilities are strong
candidates to rebuild as AI agents, ranked and justified.

V1 is intentionally code-only (a path in, no runtime/connectors), so this is a
CANDIDATE-generation judgment: it looks for repetitive, rules-driven, decisioning /
document / workflow toil that agents do well - and is honest about what NOT to agentify
(already-AI, security/auth, money-movement, config/migrations, thin data models).

Deterministic heuristic by default (no key needed); an optional LLM pass (customer's own
model) sharpens the reasoning. Runtime usage (V2) will later re-rank these by real value.
"""

from __future__ import annotations

import os

from dataclasses import dataclass

from ..models import AIClass, Capability, Kind
from ..naming import pretty

# GENERIC toil signals - repetitive, rules/decision/document/workflow work agents do well.
# Deliberately NOT an app's own product names: a signal must indicate the KIND of work,
# not just "this is a module". A capability needs one of these to be a candidate at all.
_AGENT_DOMAINS = {
    "classif", "categor", "extract", "parse", "ocr", "transcri", "match", "recommend",
    "rank", "scor", "review", "approv", "triage", "moderat", "route", "routing", "dispatch",
    "reconcil", "summar", "screen", "verif", "fraud", "risk", "notif", "sentiment", "tag",
    "ingest", "report", "audit", "feedback", "resume", "ticket", "support", "onboard",
    "schedul", "remind", "escalat", "enrich", "invoice", "refund", "kyc", "complian",
    "detect", "predict", "forecast", "digest", "label", "annotat", "dedup",
    "claim", "underwrit", "adjudicat", "dispute", "chargeback", "intake", "eligib",
    "renewal", "collection", "provision", "entitle", "grading", "quote",
    # Business-transaction nouns. Once capabilities are named for the JOB rather than the layer
    # (extract/units.py), these are what the jobs are actually called in an ERP - and the whole
    # list was missing them, so "purchase order" and "sales order" could not score. Each names
    # work that is repetitive and rules-driven: routing it, approving it, matching it, chasing it.
    "order", "requisition", "payment", "receipt", "delivery", "shipment", "dunning",
    "timesheet", "payroll", "leave", "appraisal", "warranty", "lead", "contract",
    "subscription", "inspection", "complaint", "issue", "expense", "reimburse",
}
# The JUDGEMENT layer - work an agent genuinely improves on: exceptions, unstructured input, and
# calls a person makes today. This is the OPPOSITE of pure deterministic rules (which the code
# already does better than any LLM). A candidate with none of these - and no human approval step -
# is mostly a calculator, so we rank it BELOW the ones that carry real judgement. These verbs all
# imply an exception path or a human call: matching leaves un-matched items, triage weighs cases,
# reconciliation surfaces discrepancies, review/approve are human judgement.
_JUDGMENT_DOMAINS = {
    "classif", "categor", "extract", "match", "recommend", "rank", "scor", "review", "approv",
    "triage", "moderat", "route", "routing", "dispatch", "reconcil", "screen", "verif", "fraud",
    "risk", "detect", "flag", "anomaly", "audit", "dispute", "chargeback", "adjudicat", "claim",
    "underwrit", "eligib", "escalat", "exception", "complain", "appeal", "prioriti", "assess",
    "evaluat", "waiver", "override", "dedup", "sentiment", "intake",
}
# leave to humans / don't auto-agentify (security, money movement, plumbing)
_ANTI_DOMAINS = {
    "migration", "config", "setting", "auth", "login", "oauth", "crypt", "secret",
    "admin", "payment", "billing", "wsgi", "asgi", "url",
}
# NOT agent work: glue/plumbing, frontend, ops-orchestration, content-gen, tooling.
# These are excluded from the TOIL-ONLY path (a module can still qualify if its name
# names real agent-domain work). This is what keeps branchy infrastructure - integrations,
# seo pages, the React app, delivery/execution orchestration - out of the list.
_INFRA_DENY = {
    "integration", "seo", "react", "frontend", "dashboard", "manager", "execution",
    "engine", "util", "script", "middleware", "gateway", "proxy", "webpack", "chatgpt",
    "pipeline", "runner", "bootstrap", "scaffold", "codegen",
}


@dataclass
class Opportunity:
    capability: Capability
    potential: str      # "high" | "medium"
    score: int          # 0..100
    reason: str         # why it's a good agent candidate
    agent_summary: str  # what the agent would do
    effort: str         # S | M | L
    caution: str | None = None  # a "handle with care" note (money/security adjacent)
    origin: str = "heuristic"   # "heuristic" | "ai-validated" | "ai-found"
    # Beverly's question - "what does this mean to me / to the people who do it today?" - answered
    # from code alone: the OUTCOME + who holds the decision today. NEVER a headcount or dollar
    # figure; those are not in the code, and inventing them is the drift the whole tool refuses.
    value: str = ""
    # Observed work volume from the tickets/issues join (tickets.attach_demand) - measured from
    # the customer's own export, e.g. "1,240 work items relate to this capability". Empty when no
    # work exhaust was provided. Evidence, never an invented rate.
    demand: str = ""

    @property
    def title(self) -> str:
        """What the reader sees. A business capability is ONE thing even when it is implemented
        in two languages, so the language tag - which exists to keep polyglot CAPABILITIES
        distinct in the map - is dropped here. Nobody wants "purchase order (JS/TS)" on a board
        paper; ERPNext implements purchase orders in Python and JS and it is still one job."""
        cap = self.capability
        if cap.domain_unit:
            # Pretty each side of the colon separately, so "hrms: leave" -> "HRMS: Leave" (not
            # "Hrms: Leave" - the acronym only fires when the colon is not stuck to the word).
            return f"{pretty(_product(cap))}: {pretty(cap.domain_unit)}"
        from ..naming import pretty_capability
        return pretty_capability(cap.name)


# Role -> base score, covering the role labels every language extractor produces
# (Python/JS/Java/C#/Go/C++/COBOL/RPG), so no stack's work-roles are silently dropped.
_ROLE_BASE = {
    "service": 42, "core": 36, "background": 36, "job": 34, "program": 40,
    "command": 30, "implementation": 32, "logic": 34, "worker": 34,
    "api": 22, "controller": 22, "handler": 22, "view": 20, "endpoint": 22,
    "data model": 6, "copybook": 6, "storage": 8, "persistence": 8, "header": 8,
    "interface": 10, "component": 12, "state": 10, "page": 12, "hook": 8,
}
_SIZE_BONUS = {"large": 26, "medium": 16, "small": 6}
_EFFORT = {"large": "L", "medium": "M", "small": "S"}
# A generically-named module (no agent-domain keyword) qualifies on decision-density ALONE
# only if it is VERY branchy, a strong work role, and not infrastructure. Deliberately high:
# the domain-keyword path is the precision signal; this is only a safety-net so heavily
# decisioning domain code under a non-descriptive name (e.g. a Java "OrderProcessor") is
# not missed. On a well-named codebase it should admit almost nothing extra.
_TOIL_ONLY_MIN = 150
_TOIL_ONLY_ROLE_BASE = 30


def _role(cap: Capability) -> str:
    return cap.name.split(": ", 1)[1] if ": " in cap.name else cap.name


def _product(cap: Capability) -> str:
    return cap.name.split(": ", 1)[0] if ": " in cap.name else cap.name


def _text(cap: Capability) -> str:
    """Everything we can match the domain vocabulary against: the name, the deps, and the
    FILE NAMES.

    File names, because the vocabulary is good (reconcil, invoice, approv, triage, quote, claim,
    kyc) but it used to be matched only against the capability's LABEL - and the labels were
    architectural ("core logic", "pages / routes"), so a domain word could never appear in one.

    File NAMES and not full paths, though: the vocabulary contains "report" and "audit", so
    feeding it directory names would give a domain hit to every file Frappe requires you to put
    under `report/` - handing a keyword match to the exact tree that has none of the work.
    """
    stems = [os.path.splitext(os.path.basename(p.replace("\\", "/")))[0] for p in cap.paths]
    parts = [cap.name, " ".join(cap.dependencies), " ".join(stems)]
    return " ".join(parts).replace("_", " ").replace("-", " ").lower()


# A domain unit ("payment reconciliation") is business work by definition - that is what made it
# a unit rather than a layer. It has no architectural role word in its name, so _role_base would
# score it 15 and the work-role gate would throw away the best capabilities we have.
_UNIT_BASE = 36


def _role_base(role: str) -> int:
    r = role.lower()
    for kw, base in _ROLE_BASE.items():
        if kw in r:
            return base
    return 15


def _domain_hit(text: str, domains: set[str]) -> str | None:
    for d in domains:
        if d in text:
            return d
    return None


def score_one(cap: Capability) -> Opportunity | None:
    """Score a single capability. Returns None if it's not an agent candidate."""
    if cap.kind != Kind.BUILT or cap.level.value != "capability":
        return None                              # SaaS integrations aren't agent targets
    if cap.ai_or_not == AIClass.AI:
        return None                              # already AI

    role = _role(cap)
    text = _text(cap)

    # Selectivity gate #1: must be a WORK role (not a data model / UI / page / header).
    #
    # A domain unit is named for its JOB ("payment reconciliation"), so its name no longer
    # carries a role word and _role_base would score it 15 and throw away the best capabilities
    # we have. Hence _UNIT_BASE. But the role is still checked FIRST, from cap.role, which
    # extraction preserves precisely for this: a React feature folder is a domain unit too, and
    # without this check AiDOOS's own front-end (`features/CommandCenter`, `features/Proposal`)
    # got nominated for rebuilding as AI agents. A UI page is not an agent, whatever it is named.
    base = _role_base(cap.role or role)
    if base < 20:
        return None
    if cap.domain_unit:
        base = max(base, _UNIT_BASE)

    # Selectivity gate #2: the name must name agent-friendly work (domain keyword). This is
    # the precision signal. A module WITHOUT a domain keyword qualifies only via the narrow
    # toil-only safety-net: very decision-heavy AND a strong work role AND not infrastructure
    # (glue/frontend/orchestration/tooling). That safety-net is what gives ANY-language
    # coverage for non-descriptive names without turning branchy plumbing into candidates.
    domain = _domain_hit(text, _AGENT_DOMAINS)
    toil = cap.toil_signal
    if not domain:
        # A DOMAIN UNIT is held to the strict bar: we know what this capability is CALLED, and
        # if the name is not agent-suited work, we do not propose an agent for it. The toil-only
        # safety net exists to rescue business logic hiding under a MEANINGLESS name - that
        # rationale evaporates once the name is meaningful. Applying it to units anyway is how
        # ERPNext ended up nominating `accounts: account` (a chart-of-accounts master) and
        # `accounts: party`: big, branchy, and not agent work.
        if cap.domain_unit:
            return None
        if (toil < _TOIL_ONLY_MIN or base < _TOIL_ONLY_ROLE_BASE
                or _domain_hit(text, _INFRA_DENY)):
            return None

    domain_bonus = 22 if domain else 0
    toil_bonus = min(26, toil // 8)              # decision density -> agent-fit
    score = base + _SIZE_BONUS.get((cap.size_complexity or "small"), 6) + domain_bonus + toil_bonus
    anti = _domain_hit(text, _ANTI_DOMAINS)
    caution = None
    if anti:
        score -= 28
        caution = (f"Touches {anti}-adjacent logic - keep a human in the loop; agentify the "
                   "routine parts only.")

    # Down-rank PURE RULES. If the capability carries no judgement layer - no exceptions/matching/
    # review verbs and no human approval step - then the code already does the deterministic part
    # better than an agent would, and an agent adds little. Keep it (there may be some exception
    # work on top) but rank it below the capabilities where a person actually exercises judgement.
    has_judgment = bool(getattr(cap, "human_in_loop", False)) or _domain_hit(text, _JUDGMENT_DOMAINS)
    if not has_judgment:
        score -= 20

    score = max(0, min(100, score))
    if score < 55:
        return None                              # keep only strong candidates
    potential = "high" if score >= 78 else "medium"
    product = _product(cap)
    size = cap.size_complexity or "small"
    layer = " with a judgement layer on top" if has_judgment else ""
    if cap.domain_unit:
        # Name the job, not the layer. "Bank reconciliation in banking" - a sentence a CEO can
        # act on - rather than "the core logic of the banking module", which says nothing.
        unit = cap.domain_unit
        subject = unit
        reason = (f"{unit[:1].upper()}{unit[1:]} in the {product} module: a {size} body of "
                  f"rules-driven, repetitive work{layer}.")
    else:
        subject = f"{role} work"
        dom_phrase = (f"handles {domain}-type work, " if domain else "")
        reason = (f"The {role} of the {product} module {dom_phrase}which is repetitive, "
                  f"rules-driven work{layer} (~{size}).")
    # The card's job is to make the code-vs-agent difference obvious: the deterministic rules
    # STAY as code (an agent would only make them slower and less exact); the agent takes the
    # layer a person handles today. When there is no such layer, say so plainly.
    if has_judgment:
        agent_summary = ("The deterministic checks stay as code. The agent takes the layer on top "
                         "of them - the exceptions those checks flag, the borderline judgement "
                         "calls, and the plain-language cases - and escalates only the genuinely "
                         "hard ones to a person.")
    else:
        agent_summary = ("The rules here are largely deterministic - code already does them well. "
                         "An agent helps only with any exception-handling layered on top; the "
                         "core calculation is not worth rebuilding as an agent.")
    return Opportunity(cap, potential, score, reason, agent_summary,
                       _EFFORT.get(size, "M"), caution, value=_agent_value(cap, product, subject))


def _agent_value(cap: Capability, product: str, subject: str) -> str:
    """Beverly's "what does it mean to me / to the people who do it today?" - answered honestly
    from code: the OUTCOME, plus who holds the decision when the code shows a human step. No
    headcount, no dollar figure - those are not in the code."""
    v = (f"Frees the {pretty(product)} team from the routine {subject} so their time goes to the "
         f"exceptions and the judgement calls.")
    if getattr(cap, "human_in_loop", False):
        v += (" A person signs off on each one today; the agent handles the routine cases and "
              "routes only the genuine exceptions to them.")
    return v


def assess(capabilities: list[Capability], limit: int | None = None) -> list[Opportunity]:
    """Return ranked agent-candidate opportunities (highest potential first).

    DOMAIN UNITS stand on their own: `accounts: payment reconciliation` and
    `accounts: bank reconciliation tool` are two different jobs and the reader wants both. They
    are the whole point of the report.

    LAYER BUCKETS still roll up to one per product. A product's leftover plumbing gets split
    across core logic / service layer / API / background jobs, which is an implementation
    detail; listing the same product four times under four architectural labels is the noise
    that made the old report useless. Keep the best-scoring one as the representative.
    """
    # Which products did we manage to decompose by domain at all?
    decomposed = {_product(c) for c in capabilities if c.domain_unit}

    best_unit: dict[tuple[str, str], Opportunity] = {}
    best_layer: dict[str, Opportunity] = {}
    for o in (score_one(c) for c in capabilities):
        if not o:
            continue
        cap = o.capability
        p = _product(cap)
        if cap.domain_unit:
            # One BUSINESS capability, not one per language. ERPNext implements `work order` in
            # both Python and JS, which is an implementation detail; listing "work order" and
            # "work order (JS/TS)" as two agent opportunities is the same duplicate-rows noise
            # that made the old report unreadable.
            k = (p, cap.domain_unit)
            if k not in best_unit or o.score > best_unit[k].score:
                best_unit[k] = o
            continue
        if p in decomposed:
            # We named this product's real capabilities. Whatever did not fall into one of them
            # is the leftover plumbing - and it is exactly what used to be reported as
            # "manufacturing: core logic, 172,083 LOC, rebuild as an AI agent in 1-2 months".
            continue
        if p not in best_layer or o.score > best_layer[p].score:
            best_layer[p] = o
    opps = sorted(list(best_unit.values()) + list(best_layer.values()),
                  key=lambda o: (-o.score, o.capability.name))
    return opps[:limit] if limit else opps

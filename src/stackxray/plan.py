"""Sequenced transformation plan - the output a chat window cannot produce.

A list of findings is not a plan. Four separate lists (consolidate / agentify / keep / retire)
are still not a plan. What a portfolio view buys you - and what a per-repo prompt structurally
cannot - is the ORDER: which work must happen first because other work stands on top of it.

The load-bearing insight this module encodes:

    An agent is not built in a vacuum. It is built ON the codebase's foundations - the LLM
    client, the datastore client, the payment client. If a foundation is already sprawled
    (the same tool wired up independently in 4 products), then every agent you build on it
    adds a 5th, 6th, 7th copy. Consolidating AFTER you agentify means consolidating more.

So the plan is:

    1. FOUNDATION  consolidate the sprawled tools the agents will stand on   (do first)
    2. BUILD       agentify the capabilities                                  (do next)
    3. LEAVE       the capabilities with nothing to do                        (don't touch)
    4. LOCKED      retire - honestly unavailable without runtime evidence     (needs logs)

Steps 1 and 2 are LINKED, not adjacent: each build step names the foundations it depends on,
and each foundation names the agents it blocks. That linkage is the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .agentify import Opportunity
from .models import Capability, Kind, Level, Verdict

# Which foundation a shared dependency belongs to (for human-readable phrasing).
_CATEGORY = {
    "anthropic": "LLM", "openai": "LLM", "cohere": "LLM", "mistralai": "LLM",
    "pymongo": "datastore", "redis": "datastore", "psycopg2": "datastore",
    "sqlalchemy": "datastore", "elasticsearch": "datastore", "qdrant_client": "datastore",
    "stripe": "payments", "braintree": "payments", "paypal": "payments",
    "twilio": "messaging", "sendgrid": "messaging", "boto3": "cloud",
}

# A tool wired up independently in at least this many products is "sprawled".
MIN_SPRAWL_PRODUCTS = 2


def _product(cap: Capability) -> str:
    return cap.name.split(": ", 1)[0] if ": " in cap.name else cap.name


@dataclass
class Foundation:
    """A shared tool that several products each wired up separately.

    The agents standing on it are split by HOW WE KNOW, because they are not the same kind of
    claim and the report must not present them as if they were:

      detected - the agent's product genuinely imports this tool today (read from the code).
      inferred - it will need it once it becomes an agent (the "an agent needs a model" rule).

    Nothing here is literally BLOCKED: you can build the agents without consolidating. You
    would just end up with more copies than you started with. That is a cost, not a blocker.
    """
    tool: str
    category: str
    products: list[str]                       # who integrated it independently
    detected: list[str] = field(default_factory=list)   # agents whose code already imports it
    inferred: list[str] = field(default_factory=list)   # agents that will need it once built

    @property
    def blocks(self) -> list[str]:
        return self.detected + self.inferred

    @property
    def after(self) -> int:
        """Copies of this client you end up with if you build the agents WITHOUT consolidating."""
        return len(self.products) + len(self.blocks)

    @property
    def urgency(self) -> int:
        """Consolidate the foundations the most agents will land on, first."""
        return (len(self.blocks) * 10) + len(self.products)


@dataclass
class BuildStep:
    """An agent to build, and the foundations it must stand on."""
    opportunity: Opportunity
    prerequisites: list[str] = field(default_factory=list)   # tool names to consolidate first


@dataclass
class RetireCandidate:
    """A capability with ZERO observed traffic over a trustworthy window.

    NEVER call this "retire". Absence of evidence is not evidence of absence: a 34-day window
    cannot see a month-end close, a quarterly reconciliation, or an annual report. We say
    CANDIDATE, we state the window, and we tell the reader to confirm with the owner.
    """
    name: str
    window_days: int
    last_used: str | None = None


@dataclass
class Plan:
    foundation: list[Foundation]
    build: list[BuildStep]
    leave: int                       # capabilities with no action indicated
    retire_locked: bool              # True when we have no runtime evidence
    total: int
    retire: list[RetireCandidate] = field(default_factory=list)
    window_days: int = 0             # the log window the retire call rests on
    merge: list = field(default_factory=list)     # list[duplication.DuplicateCluster]

    @property
    def blocked_agents(self) -> int:
        return sum(1 for b in self.build if b.prerequisites)

    @property
    def llm_foundations(self) -> list[Foundation]:
        return [f for f in self.foundation if f.category == "LLM"]

    @property
    def existing_llm_clients(self) -> int:
        """How many times an LLM client is already wired up independently."""
        return sum(len(f.products) for f in self.llm_foundations)

    @property
    def replaced_by_merges(self) -> int:
        """Existing implementations that the merged agents would retire."""
        return sum(len(c.members) for c in self.merge)

    @property
    def widest_merge(self):
        return self.merge[0] if self.merge else None

    def headline(self) -> str:
        """The one sentence that makes this a plan rather than a list.

        Only sayable from a PORTFOLIO view. Duplication leads when we found it, because it is
        the most surprising thing in the report and the one a per-repo chat prompt structurally
        cannot produce: it is a statement about the RELATIONSHIP between modules, and you only
        see it if you looked at all of them at once.
        """
        n = len(self.build)
        w = self.widest_merge
        # Lead with duplication when the finding is strong: an AI-CONFIRMED duplicate (even a
        # 2-way one - a confirmed pair is a stronger thing to say than an unconfirmed 4-way), or
        # an unconfirmed cluster wide enough (>=3 products) to be worth the headline on its own.
        if w and (w.confirmed or len(w.members) >= 3):
            k = len(w.members)
            allof = "both" if k == 2 else f"all {k}"
            said = (f"You do {w.label} in {k} different places - {', '.join(w.products)} - each "
                    f"built separately: {w.loc:,} lines of code doing the same job {k} times.")
            # The headline carries the same hedge the card does. Unconfirmed, this is a match on
            # NAME and SHAPE - and ERPNext is precisely where that bites: bank reconciliation and
            # *stock* reconciliation share a word and may be different jobs. Asserting "one agent
            # replaces all 3" in the loudest sentence, on a keyword match, is the overclaim this
            # whole module exists to avoid. Confirmed, an engineer read the code and agreed.
            if w.confirmed:
                return (f"{said} One agent replaces {allof} - confirmed by reading the code. It "
                        f"is not on anyone's roadmap, because no single team owns more than one "
                        f"of them.")
            return (f"{said} If they are the same job - worth confirming before you act - one "
                    f"agent replaces {allof}. No single team owns more than one of them, which "
                    f"is why nobody has raised it.")
        if not n:
            return "No capabilities surfaced as agent candidates."
        llm = self.llm_foundations
        if llm:
            have = self.existing_llm_clients
            where = ", ".join(f"{f.tool} in {len(f.products)}" for f in llm)
            return (f"You are about to build {n} AI agents. Every one of them needs an LLM "
                    f"client - and you already wire one up {have} separate times ({where} "
                    f"products). Build first and you finish with {have + n}. Consolidate to a "
                    f"single LLM gateway before you start.")
        if self.blocked_agents:
            f = self.foundation[0]
            return (f"{self.blocked_agents} of your {n} agent targets stand on {f.tool}, which "
                    f"is wired up separately in {len(f.products)} products. Consolidate it "
                    f"before you build on it.")
        return (f"{n} capabilities are worth rebuilding as AI agents, and no shared foundation "
                f"needs consolidating first. Clean base - go straight to build.")


def find_sprawl(capabilities: list[Capability]) -> dict[str, list[str]]:
    """tool -> the products that each integrated it independently (>= MIN_SPRAWL_PRODUCTS).

    Read off the BUILT capabilities' dependencies: if 4 products each import `anthropic`,
    that is 4 separately-wired LLM clients, not one shared one.
    """
    by_tool: dict[str, set[str]] = {}
    for cap in capabilities:
        if cap.level != Level.CAPABILITY or cap.kind != Kind.BUILT:
            continue
        for dep in cap.dependencies:
            by_tool.setdefault(dep.lower(), set()).add(_product(cap))
    return {t: sorted(p) for t, p in by_tool.items() if len(p) >= MIN_SPRAWL_PRODUCTS}


def _product_deps(capabilities: list[Capability]) -> dict[str, set[str]]:
    """product -> every tool ANY of its capabilities depends on.

    Dependencies must be gathered per PRODUCT, not per capability: agentify reports one
    representative role per product (say `web_resume: core logic`), and the tools may be
    imported by a sibling role (`web_resume: service layer` -> openai, pymongo). Reading deps
    off the representative alone loses the link entirely.
    """
    out: dict[str, set[str]] = {}
    for cap in capabilities:
        if cap.level != Level.CAPABILITY:
            continue
        out.setdefault(_product(cap), set()).update(d.lower() for d in cap.dependencies)
    return out


def build_plan(capabilities: list[Capability], opportunities: list[Opportunity],
               merge: list | None = None) -> Plan:
    """Sequence the work: consolidate the foundations, then build the agents on top.

    `merge` carries the duplicate clusters (duplication.find_duplicates). They do NOT become a
    "consolidate these 3" step followed by a "now agentify the survivor" step - that is the
    two-invoice answer no customer accepts. They collapse into ONE agent that does the combined
    job, and they lead Step 2 because they retire the most code per agent built.
    """
    sprawl = find_sprawl(capabilities)
    prod_deps = _product_deps(capabilities)

    # Best merge first: an AI-CONFIRMED duplicate outranks an unconfirmed candidate, and among
    # equals the one that retires more code leads. This runs AFTER adjudication, so a confirmed
    # 2-way pair (bank reconciliation, {banking, accounts}) correctly beats a larger but merely
    # candidate cluster - and becomes the headline.
    merge = sorted((merge or []), key=lambda c: (0 if c.confirmed else 1, -c.loc))

    # An AGENT needs a model. That is what makes it an agent. So every agent we are about to
    # build will stand on the LLM foundation - whether or not the capability it replaces
    # imports an LLM client today. If that foundation is already sprawled, building N agents
    # on it adds N more copies. This is the load-bearing link in the whole plan.
    llm_tools = sorted(t for t in sprawl if _CATEGORY.get(t) == "LLM")

    # A capability the MERGED agent already replaces must not also be listed as its own agent.
    # ERPNext's reconciliation cluster covers `banking: bank reconciliation`,
    # `accounts: bank reconciliation tool` and `stock: stock reconciliation` - showing "one
    # agent replaces these 3" and then billing for the same 3 individually below it is exactly
    # the double-count the merge exists to remove.
    covered: set[str] = set()
    for c in (merge or []):
        for m in c.members:
            covered.add(f"{m.product}|{c.term}")

    def _is_covered(opp: Opportunity) -> bool:
        cap = opp.capability
        if not cap.domain_unit:
            return False
        p = _product(cap)
        return any(f"{p}|{c.term}" in covered and c.term in cap.domain_unit.replace(" ", "")
                   for c in (merge or []))

    steps: list[BuildStep] = []
    for opp in opportunities:
        if _is_covered(opp):
            continue
        product = _product(opp.capability)
        inherited = {d for d in prod_deps.get(product, set()) if d in sprawl}
        prereqs = sorted(inherited | set(llm_tools))     # LLM always; plus what it already uses
        steps.append(BuildStep(opportunity=opp, prerequisites=prereqs))

    foundations: list[Foundation] = []
    for tool, products in sprawl.items():
        detected, inferred = [], []
        for s in steps:
            if tool not in s.prerequisites:
                continue
            product = _product(s.opportunity.capability)
            # Does its code ALREADY import this tool, or will it only need it once it's an agent?
            (detected if tool in prod_deps.get(product, set()) else inferred).append(
                s.opportunity.capability.name)
        foundations.append(Foundation(
            tool=tool, category=_CATEGORY.get(tool, "shared service"),
            products=products, detected=detected, inferred=inferred))
    # Foundations that block agents come first; then the most-duplicated.
    foundations.sort(key=lambda f: -f.urgency)

    leaves = [c for c in capabilities
              if c.level == Level.CAPABILITY and c.verdict == Verdict.KEEP]

    # Retire is LOCKED until runtime evidence exists. The verdict engine already refuses to
    # call anything dead from code alone (_is_dead requires usage + a >=30d window), so all we
    # do here is read off what it decided - we never infer "dead" ourselves.
    windows = [c.usage.window_days for c in capabilities
               if c.usage is not None and (c.usage.window_days or 0) > 0]
    retire_locked = not windows
    retire = [
        RetireCandidate(name=c.name,
                        window_days=(c.usage.window_days if c.usage else 0),
                        last_used=getattr(c, "last_used", None))
        for c in capabilities
        if c.level == Level.CAPABILITY and c.verdict == Verdict.RETIRE
    ]

    return Plan(foundation=foundations, build=steps, leave=len(leaves),
                retire_locked=retire_locked,
                total=sum(1 for c in capabilities if c.level == Level.CAPABILITY),
                retire=retire, window_days=(max(windows) if windows else 0),
                merge=list(merge or []))

"""Optional LLM re-judge pass (V1) - the trust upgrade for codebases we don't know.

The deterministic assess() ranks candidates from capability NAMES + code decision-density.
That is fast and free, but name-dependent: a real agent candidate hidden under a generic
name (a Java "Processor7") can be missed, and a keyword can occasionally over-admit.

When the customer set an API key, this pass reads the ACTUAL CODE and:
  1. VALIDATES each heuristic candidate - drops the ones the model, reading the code,
     judges a poor fit (and promotes the clearly-strong ones);
  2. ENRICHES the survivors' reasoning from what the code actually does;
  3. RECOVERS strong candidates the name-based heuristic missed (the near-miss pool:
     genuine work roles, not infra/security, that lacked a domain keyword).

Best-effort throughout: no key, or any error, leaves the heuristic result untouched. This
is what turns "works because we knew the codebase" into "works on a codebase we don't."
"""

from __future__ import annotations

from ..models import AIClass, Capability, Kind
from . import (
    _AGENT_DOMAINS, _ANTI_DOMAINS, _EFFORT, _INFRA_DENY,
    Opportunity, _domain_hit, _role, _role_base, _text,
)
from .sharpen import _context

_SYSTEM = (
    "You are a pragmatic staff engineer judging whether a business capability contains a "
    "PROCESS an AI agent could own: repetitive, rules- or judgement-driven work like matching, "
    "reconciling, routing, approving, triaging, classifying, extracting, scoring, drafting, or "
    "exception-handling. Almost every business module ALSO contains schema, CRUD, and ORM "
    "plumbing - that is normal and is NOT a reason to reject it; look past it for the process. "
    "DROP only when there is genuinely no such process: a pure data model or master table, a "
    "config/settings holder, UI/rendering, or plain glue. Judge the process, not the plumbing."
)

_ASK = (
    "Answer in exactly three lines, nothing else:\n"
    "VERDICT: STRONG, OK, or DROP  (STRONG = a clear repetitive rules/judgement process an "
    "agent could own; OK = a real but smaller process; DROP = no process, just data/config/UI/glue)\n"
    "WHY: one sentence, grounded in the actual process the code carries out.\n"
    "AGENT: one sentence on what the agent would TAKE OVER *beyond the deterministic rules the "
    "code already runs well* - the exceptions those rules flag, the borderline judgement calls, "
    "unstructured or plain-language input, or the human approvals a person does today. Do NOT "
    "restate the validation or calculation the code already performs (rebuilding that as an agent "
    "would only make it slower and less exact). Use '-' if DROP."
)


def _parse(reply: str) -> tuple[str | None, str | None, str | None]:
    verdict = why = agent = None
    for line in reply.splitlines():
        s = line.strip()
        u = s.upper()
        if u.startswith("VERDICT:"):
            verdict = ("DROP" if "DROP" in u else "STRONG" if "STRONG" in u
                       else "OK" if ("OK" in u or "KEEP" in u) else None)
        elif u.startswith("WHY:"):
            why = s.split(":", 1)[1].strip()
        elif u.startswith("AGENT:"):
            agent = s.split(":", 1)[1].strip()
    return verdict, why, agent


def _judge(cap: Capability, repo_path: str, provider=None, budget=None):
    """Return (verdict, why, agent) from the model reading the code, or (None, None, None)."""
    from ..llm_client import ask
    ctx = _context(repo_path, cap)
    if not ctx:
        return None, None, None
    reply = ask(_SYSTEM, f"Capability: {cap.name}\n\nCode excerpt:\n{ctx}\n\n{_ASK}",
                provider=provider, budget=budget)
    return _parse(reply) if reply else (None, None, None)


def _validate_and_enrich(opps: list[Opportunity], repo_path: str, ensure: int, max_calls: int,
                         provider=None, budget=None) -> tuple[list[Opportunity], int]:
    """Read the code for the highest-ranked candidates: drop the ones the model rejects, enrich
    the survivors' reasoning from what the code actually does.

    The stopping rule is `ensure` SURVIVORS, not a fixed window - and that distinction is the
    whole point. The heuristic over-admits (a domain unit scores high on its name alone), so
    reading the code the model rightly DROPS a lot of plumbing near the top - pos-invoice CRUD,
    a purchase-order field mapper, a controller. A fixed top-N window then stops before the
    displayed cards are all grounded, and un-examined high-score items bubble into view still
    carrying the template reason. Keep going until `ensure` survivors are validated (bounded by
    max_calls and the token budget), so every card the reader sees was actually read."""
    kept: list[Opportunity] = []
    validated = calls = ok_calls = 0
    for opp in opps:
        stop = (validated >= ensure or calls >= max_calls
                or (budget is not None and budget.exhausted))
        if stop:
            kept.append(opp)                     # quota met / budget spent: trust the heuristic
            continue
        calls += 1
        verdict, why, agent = _judge(opp.capability, repo_path, provider, budget)
        if verdict:
            ok_calls += 1                        # the model actually answered (incl. a DROP)
        if verdict == "DROP":
            continue                             # model rejected it after reading the code
        if why:
            opp.reason = why
        if agent and agent != "-":
            opp.agent_summary = agent
        if verdict == "STRONG":
            opp.potential = "high"
            opp.score = max(opp.score, 80)
        if verdict:
            opp.origin = "ai-validated"
            validated += 1                       # a code-read survivor; only these count
        kept.append(opp)
    return kept, ok_calls


def _near_miss_pool(caps: list[Capability], chosen: set[str], limit: int) -> list[Capability]:
    """Genuine work capabilities the NAME-based heuristic never assessed: no domain keyword,
    but also NOT infra/security/glue. The most decision-heavy ones first (cheap proxy)."""
    pool = []
    for c in caps:
        if c.name in chosen:
            continue
        if c.kind != Kind.BUILT or c.level.value != "capability" or c.ai_or_not == AIClass.AI:
            continue
        text = _text(c)
        if _role_base(_role(c)) < 20:            # must be a work role
            continue
        if _domain_hit(text, _AGENT_DOMAINS):    # keyword hits were already assessed
            continue
        if _domain_hit(text, _INFRA_DENY) or _domain_hit(text, _ANTI_DOMAINS):
            continue                             # never recover infra / security / money / config
        pool.append(c)
    pool.sort(key=lambda c: (-c.toil_signal, c.name))
    return pool[:limit]


def _recover(caps: list[Capability], opps: list[Opportunity], repo_path: str,
             limit: int, provider=None, budget=None) -> list[Opportunity]:
    chosen = {o.capability.name for o in opps}
    found: list[Opportunity] = []
    for c in _near_miss_pool(caps, chosen, limit):
        if budget is not None and budget.exhausted:
            break                                # free tier spent; keep what we have
        verdict, why, agent = _judge(c, repo_path, provider, budget)
        if verdict not in ("STRONG", "OK"):
            continue                             # only add what the model actively endorses
        size = c.size_complexity or "small"
        found.append(Opportunity(
            capability=c,
            potential="high" if verdict == "STRONG" else "medium",
            score=80 if verdict == "STRONG" else 70,
            reason=why or "Surfaced by AI review of the code as agent-suitable work.",
            agent_summary=(agent if agent and agent != "-" else ""),
            effort=_EFFORT.get(size, "M"),
            origin="ai-found",
        ))
    return found


def rejudge(opps: list[Opportunity], capabilities: list[Capability], repo_path: str,
            ensure: int = 16, max_calls: int = 40, recover_limit: int = 8, provider=None,
            budget=None) -> tuple[list[Opportunity], bool]:
    """Validate + enrich + recover by reading the code. Returns (opps, ai_ran).

    `ensure` = how many validated survivors to reach before trusting the heuristic for the rest;
    set to comfortably cover the cards the report displays, so every visible card is code-read.
    Bounded cost two ways: at most max_calls + recover_limit cheap-model calls, AND a TokenBudget
    that stops spending at the cap (hosted free tier). No provider or any failure returns the
    heuristic list unchanged with ai_ran=False.
    """
    from ..llm_client import available
    if not available(provider):
        return opps, False
    try:
        kept, ok_calls = _validate_and_enrich(list(opps), repo_path, ensure, max_calls,
                                              provider, budget)
        recovered = _recover(capabilities, kept, repo_path, recover_limit, provider, budget)
        kept.extend(recovered)
        # A key being CONFIGURED is not the same as the model having answered. If every call came
        # back empty (rejected key, network, exhausted budget), the AI did not read anything - and
        # the report must not then claim "read and validated against the actual code". That claim
        # was the honesty firewall failing on itself.
        if not ok_calls and not recovered:
            return opps, False
        # Code-READ opportunities sort ABOVE name-only ones. When a key ran, the whole promise is
        # "we read your code" - so a candidate the model actually examined and endorsed must not
        # sit below one that merely scored high on its name and was never opened. Without this, a
        # heuristic item at score 84 outranks an AI-validated one at 80, and the reader's first
        # cards carry the identical template reason instead of the specific, code-grounded one.
        _rank = {"ai-validated": 0, "ai-found": 0}
        kept.sort(key=lambda o: (_rank.get(o.origin, 1), -o.score, o.capability.name))
        return kept, True
    except Exception:
        return opps, False

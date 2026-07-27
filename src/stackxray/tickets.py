"""The work-exhaust connector: tickets/issues joined onto the code capability map.

A code scan sees what is BUILT. Tickets are where the UNCODED work leaves footprints: named
work items, categories, volumes. Alone, either stream is a half-picture. JOINED, they produce
the one sentence nobody else can: "4,200 'invoice mismatch' tickets closed in 90 days - that is
the exception stream of your reconciliation capability, and the agent seam sits exactly there."

Design rules (settled with Krishna):
  - JOIN-FIRST: this exists to put evidence and volume on the agent seams in the map we already
    build, not to be a stand-alone ticket analyzer.
  - ENRICH, don't re-narrate: matched volume lands on the existing cards (Opportunity.demand);
    unmatched volume is ONE honest line (work happening outside what is built).
  - File/parse only: this module never touches the network. The hosted app fetches public GitHub
    issues server-side and hands the JSON here; a local run points at an export file.
  - Honest numbers only: counts and windows measured from the export. Never an invented rate.

Parsers: GitHub issues (JSON, as the API/`gh` return), Jira (CSV export), generic CSV
(title[,labels][,created][,closed]). All normalize to WorkItem.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field


@dataclass
class WorkItem:
    """One unit of observed work - a ticket, an issue, an incident."""
    title: str
    labels: list[str] = field(default_factory=list)
    created: str = ""          # ISO date if the export carries one
    closed: str = ""


@dataclass
class DemandStats:
    """What the join found - rendered as evidence, never as an invented rate."""
    total: int = 0             # work items read
    matched: int = 0           # items that joined to a built capability
    unmatched: int = 0         # items with NO code home - the uncoded-work signal
    window: str = ""           # e.g. "2025-08-01 to 2026-07-20", measured from the export
    per_capability: dict = field(default_factory=dict)   # cap.id -> count
    source: str = ""           # "github issues" | "jira export" | "ticket export"
    reranked: bool = False     # True when volume actually moved the ranking (never silent)


# Ticket volume -> score boost. Tiered on ABSOLUTE counts so the gate is built in: a 6-row demo
# CSV boosts nothing, a real 30-day export genuinely moves ranks. Krishna's call (2026-07-27):
# where tickets pile up IS the priority - support work is what companies agentify first, and
# Tickets + Tasks + Code ranked together is the input nobody else has.
_BOOST_TIERS = ((50, 16), (20, 12), (10, 8), (5, 4))


def demand_boost(n: int) -> int:
    for at_least, boost in _BOOST_TIERS:
        if n >= at_least:
            return boost
    return 0


# ---- parsers --------------------------------------------------------------------------

def parse_github_issues(text: str) -> list[WorkItem]:
    """GitHub issues JSON: a list of {title, labels:[{name}|str], created_at, closed_at,
    pull_request?}. Pull requests are code review, not work demand - skipped."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):                      # search-API shape: {"items": [...]}
        data = data.get("items", [])
    items: list[WorkItem] = []
    for it in data:
        if not isinstance(it, dict) or not it.get("title"):
            continue
        if it.get("pull_request"):
            continue
        labels = [l.get("name", "") if isinstance(l, dict) else str(l)
                  for l in (it.get("labels") or [])]
        items.append(WorkItem(title=str(it["title"]),
                              labels=[l for l in labels if l],
                              created=str(it.get("created_at") or "")[:10],
                              closed=str(it.get("closed_at") or "")[:10]))
    return items


def parse_jira_csv(text: str) -> list[WorkItem]:
    """Jira CSV export. Column names vary by locale/config; match loosely."""
    return _parse_csv(text, title_keys=("summary", "title"),
                      label_keys=("labels", "components", "component/s", "issue type"),
                      created_keys=("created",), closed_keys=("resolved", "resolutiondate"))


def parse_generic_csv(text: str) -> list[WorkItem]:
    """Any CSV with a title-ish column; ServiceNow incident exports fit here too."""
    return _parse_csv(text, title_keys=("title", "summary", "short_description", "description",
                                        "subject", "name"),
                      label_keys=("labels", "category", "subcategory", "assignment_group",
                                  "component", "type"),
                      created_keys=("created", "opened_at", "created_at", "sys_created_on"),
                      closed_keys=("closed", "closed_at", "resolved_at"))


def _iso_date(raw: str) -> str:
    """Normalize export date formats to ISO. Jira writes `22/Jul/26 08:55` - naively slicing
    ten characters produced windows like '01/Feb/25 to 31/Oct/24' (string min/max on non-ISO
    text is meaningless; found on the real OFBiz export). Unparseable -> '' (no window is
    better than a wrong one)."""
    from datetime import datetime
    s = (raw or "").strip()
    if not s:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    token = s.split()[0]
    for fmt in ("%d/%b/%y", "%d/%b/%Y", "%d-%b-%Y", "%d-%b-%y",
                "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(token, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _parse_csv(text: str, title_keys, label_keys, created_keys, closed_keys) -> list[WorkItem]:
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except csv.Error:
        return []
    if not rows:
        return []

    def pick(row: dict, keys) -> str:
        low = {k.strip().lower(): (v or "") for k, v in row.items() if k}
        for k in keys:
            if low.get(k):
                return str(low[k]).strip()
        return ""

    items = []
    for row in rows:
        title = pick(row, title_keys)
        if not title:
            continue
        labels = [s.strip() for s in re.split(r"[;,|]", pick(row, label_keys)) if s.strip()]
        items.append(WorkItem(title=title, labels=labels,
                              created=_iso_date(pick(row, created_keys)),
                              closed=_iso_date(pick(row, closed_keys))))
    return items


def parse_any(text: str) -> tuple[list[WorkItem], str]:
    """Best-effort: JSON -> GitHub issues; else CSV (Jira columns, else generic)."""
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return parse_github_issues(text), "github issues"
    head = (stripped.splitlines() or [""])[0].lower()
    if "summary" in head or "issue key" in head:
        return parse_jira_csv(text), "jira export"
    return parse_generic_csv(text), "ticket export"


# ---- the join -------------------------------------------------------------------------

_STOP = {
    "the", "a", "an", "and", "or", "for", "with", "when", "not", "error", "issue", "bug",
    "fix", "add", "new", "support", "unable", "cannot", "wrong", "after", "while", "does",
    "doesn", "fails", "failed", "using", "from", "into", "this", "that", "should",
}

# Words that appear in half the capability names of any business system. A ticket sharing ONLY
# one of these with a capability is not about it: "Cafeteria menu request" must not join a
# "shift request" capability just because both say "request" (found live on the HRMS test).
# Distinctive words ("reconciliation", "payroll", "dunning") still match on their own.
_GENERIC = {
    "request", "requests", "report", "reports", "application", "applications", "management",
    "employee", "employees", "record", "records", "master", "status", "update", "updates",
    "detail", "details", "entry", "entries", "item", "items", "data", "form", "forms",
    "type", "types", "user", "users", "list", "lists", "process", "setting", "settings",
    "page", "view", "field", "fields", "system", "template", "config", "configuration",
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 3 and t not in _STOP}


def _cap_tokens(cap) -> set[str]:
    import os
    parts = [cap.name.replace(":", " "), cap.domain_unit or ""]
    parts += [os.path.splitext(os.path.basename(p.replace("\\", "/")))[0] for p in cap.paths]
    return _tokens(" ".join(parts).replace("_", " ").replace("-", " "))


def _product_of(cap) -> str:
    return cap.name.split(": ", 1)[0].lower() if ": " in cap.name else ""


def demand_key(cap) -> str:
    """Tickets are about a BUSINESS unit, not a code location. HRMS implements 'expense claim'
    in the `hr` module (Python), in JS, AND in the `frontend` Vue app - three capabilities, one
    job - and a ticket text-matches whichever variant shares the most words while the card holds
    another. Found live twice: first the JS-vs-Python split, then 28 expense tickets crediting
    'frontend|expense claim' while the card was 'hr|expense claim'. So the key is the UNIT
    ALONE: same unit name = same business job, wherever it is coded. Capabilities without a
    unit fall back to their id."""
    unit = (getattr(cap, "domain_unit", "") or "").strip().lower()
    if unit:
        return f"unit|{unit}"
    return cap.id


def join_demand(capabilities, items: list[WorkItem], source: str = "") -> DemandStats:
    """Attach observed work volume to the capabilities it belongs to.

    A ticket joins a capability when a LABEL names its product/module (strong signal - orgs
    label by module), or when its title shares >= 2 meaningful tokens with the capability's
    name/unit/files. A SINGLE shared token is enough only when it is a DISTINCTIVE domain-unit
    word: 'reconciliation' identifies a capability on its own; 'request' or 'report' appears in
    half the names of any business system and identifies nothing (the precision rule, added
    after 'Cafeteria menu request' joined a 'shift request' capability on the live HRMS test).
    Each ticket lands on its single best match, so counts never double-book. What matches
    nothing is COUNTED, not dropped - that remainder is the honest signal of work with no code
    home.
    """
    stats = DemandStats(total=len(items), source=source)
    caps = [c for c in capabilities
            if getattr(c, "level", None) and c.level.value == "capability"
            and getattr(c, "readable", True)]
    prepared = []
    for c in caps:
        unit_toks = _tokens((c.domain_unit or "").replace("_", " "))
        prepared.append((c, _cap_tokens(c), unit_toks, _product_of(c)))

    # Window only from ISO-shaped dates: string min/max on anything else is meaningless.
    dates = [it.created for it in items
             if it.created and re.match(r"^\d{4}-\d{2}-\d{2}$", it.created)]
    if dates:
        stats.window = f"{min(dates)} to {max(dates)}"

    for it in items:
        it_toks = _tokens(it.title)
        it_labels = {l.lower() for l in it.labels}
        best, best_score = None, 0
        for c, toks, unit_toks, product in prepared:
            score = 0
            if product and product in it_labels:
                score += 3                          # org labelled the ticket with the module
            overlap = it_toks & toks
            score += len(overlap)
            # The single-word path must be DISTINCTIVE: a generic unit word ("request",
            # "report") shared alone says nothing about which work this ticket is.
            if (overlap & unit_toks) - _GENERIC:
                score += 1
            elif len(overlap) == 1 and overlap & _GENERIC and score < 3:
                score = 0                           # one generic word is no evidence at all
            if score > best_score:
                best, best_score = c, score
        if best is not None and best_score >= 2:
            stats.matched += 1
            k = demand_key(best)
            stats.per_capability[k] = stats.per_capability.get(k, 0) + 1
        else:
            stats.unmatched += 1
    return stats


def attach_demand(opps, stats: DemandStats) -> None:
    """Write the observed volume onto the existing opportunity cards (enrich, don't re-narrate).

    The copy scales with the count and says plainly whether this volume moved the ranking
    (rerank_by_demand applies the actual boost): one ticket is a small honest observation;
    5+ is real workload that lifts the candidate. Never a percentage, never a dollar.
    """
    if not stats or not stats.per_capability:
        return
    window = f" ({stats.window})" if stats.window else ""
    src = stats.source or "ticket export"
    for o in opps:
        n = stats.per_capability.get(demand_key(o.capability), 0)
        if not n:
            continue
        if n == 1:
            o.demand = (f"1 ticket in your {src}{window} touches this capability. A single item "
                        f"is a small signal - a fuller export sharpens this number.")
        elif demand_boost(n) == 0:
            o.demand = (f"{n} tickets in your {src}{window} are about this work - real workload "
                        f"from your own tracker. From 5 tickets up, volume lifts a candidate in "
                        f"the ranking.")
        else:
            o.demand = (f"{n:,} tickets in your {src}{window} are about this work. That is the "
                        f"real, current workload this agent would take on - and this volume "
                        f"lifts the candidate in the ranking.")


def rerank_by_demand(opps, stats: DemandStats) -> bool:
    """Fold measured ticket volume into the ranking. Returns True if anything moved.

    Where tickets pile up IS the priority (a medium-potential capability drowning in work
    outranks a high-potential one nobody touches), so volume adds a tiered score boost and can
    lift a candidate into high potential. Self-gating: under 5 tickets per capability nothing
    moves, so a demo CSV cannot reshuffle a ranking. NEVER SILENT - the caller must surface
    stats.reranked in the report ("ranking reflects your ticket volume").
    """
    if not stats or not stats.per_capability:
        return False
    boosted = False
    for o in opps:
        b = demand_boost(stats.per_capability.get(demand_key(o.capability), 0))
        if b:
            o.score = min(100, o.score + b)
            if o.score >= 78:
                o.potential = "high"              # volume can promote, never demote
            boosted = True
    if not boosted:
        return False
    # Re-sort with volume folded in. Score leads; at EQUAL score the ticket count itself breaks
    # the tie (scores saturate at 100, and between two top candidates the one carrying the
    # measured workload comes first - that is the whole point of the rerank). Origin last: a
    # heuristic candidate with the ticket load may legitimately pass an ai-validated one.
    _rank = {"ai-validated": 0, "ai-found": 0}
    opps.sort(key=lambda o: (-o.score, -stats.per_capability.get(demand_key(o.capability), 0),
                             _rank.get(o.origin, 1), o.title))
    stats.reranked = True
    return True

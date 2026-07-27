"""Capability duplication - the "real Combine", and the thing a per-repo prompt cannot say.

The other steps assess capabilities ONE AT A TIME. This one is the only pass that looks
ACROSS products and asks a different question: *are several teams building the same thing?*

ERPNext is the clean example. It reconciles in three separate places - `payment_reconciliation`
in accounts, `stock_reconciliation` in stock, `bank_reconciliation` in banking. Three modules,
three teams, three implementations, one job. Nobody who owns only one of those modules can see
that; it is invisible from inside any single file, and it is invisible to a chat window you
paste one repo into and ask "find me AI opportunities". It falls out only of a portfolio view.

And it changes the ANSWER, not just the report. The naive plan is two steps -

    consolidate the 3 reconcilers into 1, THEN rebuild that 1 as an agent

- which is how a consultant bills twice. No customer accepts it. They say, correctly: *just
build ONE agent that does the combined job.* So a confirmed duplicate cluster does not become
a "consolidate" step followed by a "build" step. It collapses into a SINGLE build step:

    One reconciliation agent, replacing 3 implementations across accounts, stock, banking.

That is the merge. It is why this module hands `plan.py` a cluster, not two lists.

HOW WE DETECT IT (honestly, from code alone)
    We index the JOB VERBS in every file path, per product; a verb implemented substantially in
    >=2 products is a CANDIDATE cluster. Verbs only - see _JOB_TERMS below for why clustering on
    document nouns ("order") invents duplication that is not there.

WHAT WE DO NOT CLAIM
    A shared word is not a shared job. `stock_reconciliation` (counting warehouse inventory) and
    `payment_reconciliation` (matching invoices to payments) are genuinely different work that a
    keyword cannot tell apart. So the heuristic pass produces CANDIDATES, and every claim says
    which products it spans so the reader can check it in one glance. With an API key, an LLM
    reads a real excerpt from each member and either CONFIRMS the merge or rejects it - and a
    rejected cluster is dropped, not downgraded. Same honesty firewall as everywhere else: we
    would rather say nothing than tell someone to merge two things that are not the same thing.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .agentify import _INFRA_DENY
from .extract import _scan
from .models import Capability, Kind, Level

# A term must be implemented in at least this many products before it is worth a look.
MIN_PRODUCTS = 2
# ...and hold at least this much code in EACH of them. A passing mention of "invoice" in a
# comment is not a second implementation of invoicing.
MIN_MEMBER_LOC = 80
# ...and DECIDE something. This is the guard that separates an engine from a lookup table:
# ERPNext's `account_category` and `asset_category` are master-data doctypes - CRUD, no
# branching - and matching them on "categor" would claim two categorisation engines that do
# not exist. `stock_reconciliation` branches constantly. Decision density, not naming, tells
# them apart, and it works in any language.
MIN_MEMBER_TOIL = 25
# Real duplication means COMPARABLE implementations. When one member is 50x another - ERPNext's
# `accounts` holds 20k LOC of invoicing and `regional` holds 400 - that is not two teams solving
# the same problem twice; it is one owner plus a small adapter that calls it. Merging them into
# "one agent" would be nonsense. Costs us the rare lopsided-but-real duplicate; worth it.
MIN_BALANCE = 0.10
# Duplication clusters on JOB VERBS, not on DOCUMENT NOUNS - and that distinction is the whole
# reliability of this module.
#
# agentify's vocabulary answers "is this agent-suited work?", so it rightly includes the nouns
# an ERP names its documents with: order, invoice, receipt, payment, delivery. Reusing that
# vocabulary HERE asks a different question badly. Four modules containing the word "order" are
# not four teams solving one problem four times - they are a work order, a sales order, a
# purchase order and a subcontracting order, which are four different documents with four
# different lifecycles. Clustering them produced "One order agent, replacing 4 implementations
# across manufacturing, selling, subcontracting, buying" and put it in the headline. Nonsense,
# stated confidently, at the top of the page.
#
# A shared VERB is different. Two modules that both reconcile are both doing reconciliation.
# So this list is deliberately its own thing, not a filter over agentify's.
_JOB_TERMS = {
    "reconcil", "match", "approv", "triage", "classif", "categor", "extract", "parse", "ocr",
    "transcri", "recommend", "rank", "scor", "review", "moderat", "route", "routing", "dispatch",
    "screen", "verif", "fraud", "risk", "sentiment", "summar", "escalat", "enrich", "refund",
    "kyc", "complian", "detect", "predict", "forecast", "dedup", "underwrit", "adjudicat",
    "dispute", "chargeback", "intake", "eligib", "renewal", "collection", "provision",
    "entitle", "grading", "schedul", "remind", "onboard", "annotat", "dunning", "inspection",
}

# Path segments that hold framework scaffolding or browser assets. Frappe's `report/` and
# `page/` directories are full of *_summary query scripts; matching them produced a 9-product
# "summarisation" cluster that was really just the framework's reporting convention. Browser
# assets (public/, www/) are UI - duplicated UI is not an agent finding.
_SKIP_SEGMENTS = {
    "report", "page", "dashboard", "dashboard_chart", "dashboard_chart_source",
    "print_format", "print_format_field_template", "web_form", "workspace", "custom",
    "notification", "onboarding", "module_onboarding", "onboarding_step",
    "public", "static", "assets", "www", "templates", "node_modules",
}

_TERMS = sorted(_JOB_TERMS, key=len, reverse=True)

# Human labels for the stemmed terms we cluster on (the stems keep matching loose).
_LABEL = {
    "reconcil": "reconciliation", "approv": "approval", "classif": "classification",
    "categor": "categorisation", "extract": "extraction", "match": "matching",
    "recommend": "recommendation", "schedul": "scheduling", "forecast": "forecasting",
    "predict": "prediction", "underwrit": "underwriting", "adjudicat": "adjudication",
    "eligib": "eligibility", "complian": "compliance", "summar": "summarisation",
    "moderat": "moderation", "escalat": "escalation", "provision": "provisioning",
    "detect": "detection", "dedup": "deduplication", "annotat": "annotation",
    "transcri": "transcription", "verif": "verification", "triage": "triage",
    "routing": "routing", "route": "routing", "dispatch": "dispatch", "scor": "scoring",
    "rank": "ranking", "screen": "screening", "review": "review", "audit": "audit",
    "enrich": "enrichment", "invoice": "invoicing", "refund": "refunds", "claim": "claims",
    "dispute": "disputes", "chargeback": "chargebacks", "intake": "intake",
    "renewal": "renewals", "collection": "collections", "entitle": "entitlement",
    "grading": "grading", "quote": "quoting", "ticket": "ticketing", "support": "support",
    "onboard": "onboarding", "remind": "reminders", "digest": "digests", "kyc": "KYC",
    "fraud": "fraud checks", "risk": "risk assessment", "sentiment": "sentiment analysis",
    "feedback": "feedback handling", "resume": "resume handling", "ocr": "OCR",
    "parse": "parsing", "digest ": "digests",
}

_SPLIT = re.compile(r"[^a-z0-9]+")
# camelCase / PascalCase are word boundaries too. React/TS files name themselves
# `BankReconciliation.tsx`, which without this collapses to the single token
# "bankreconciliation" - and since stems must match the START of a token, the whole
# reconciliation cluster silently lost its banking member.
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def label_for(term: str) -> str:
    return _LABEL.get(term, term)


@dataclass
class Member:
    """One product's own implementation of the shared job."""
    product: str
    loc: int
    toil: int = 0                                    # decision density - engine vs lookup table
    files: list[str] = field(default_factory=list)   # repo-relative, evidence for the claim

    @property
    def locator(self) -> str:
        return self.files[0] if self.files else ""


@dataclass
class DuplicateCluster:
    """The same job, implemented separately in several products."""
    term: str
    label: str
    members: list[Member]
    origin: str = "heuristic"           # "heuristic" | "ai-confirmed"
    reason: str = ""                    # why these are (or are not) the same job
    agent_summary: str = ""             # what the ONE merged agent would do

    @property
    def products(self) -> list[str]:
        return [m.product for m in self.members]

    @property
    def loc(self) -> int:
        return sum(m.loc for m in self.members)

    @property
    def confirmed(self) -> bool:
        return self.origin == "ai-confirmed"

    def headline(self) -> str:
        n = len(self.members)
        return (f"One {self.label} agent, replacing {n} separate implementations "
                f"across {', '.join(self.products)}.")


def _terms_in(rel_path: str) -> set[str]:
    """Work-terms named by a file's path. Read from the PATH, not the contents: a module that
    is *about* reconciliation says so in its name - `payment_reconciliation.py` - while a module
    that merely calls a reconciler does not.

    Terms match a path TOKEN as a stem, never as a substring of the whole path. Substring
    matching claimed `ledger_preview.py` as a "review" capability, because "preview" contains
    "review" - a finding that was pure string coincidence.
    """
    p = _CAMEL.sub("_", rel_path.replace("\\", "/")).lower()
    segments = p.split("/")
    if any(s in _SKIP_SEGMENTS for s in segments[:-1]):
        return set()                      # framework scaffolding or browser assets
    if segments[-1].endswith((".bundle.js", ".min.js")):
        return set()                      # build artifact, not source
    words = [w for w in _SPLIT.split(p) if w]
    if any(w in _INFRA_DENY for w in words):
        return set()                      # glue/plumbing: never a business job
    return {t for t in _TERMS for w in words if w.startswith(t)}


def find_duplicates(repo_path: str,
                    capabilities: list[Capability]) -> list[DuplicateCluster]:
    """Work-terms implemented substantially in 2+ products. Candidates, not verdicts."""
    from .extract import _ALL_CODE_EXTS, _discover_products

    live = {c.name.split(": ", 1)[0] for c in capabilities
            if c.level == Level.CAPABILITY and c.kind == Kind.BUILT}

    # term -> product -> Member
    index: dict[str, dict[str, Member]] = {}
    for product, path, exclude in _discover_products(repo_path):
        if product not in live:
            continue
        for abs_path, rel in _scan.iter_files(path, _ALL_CODE_EXTS, exclude):
            terms = _terms_in(rel)
            if not terms:
                continue
            text = _scan.read_text(abs_path)
            loc = _scan.count_loc(text)
            if not loc:
                continue
            toil = _scan.count_toil(text)
            # Store the path RELATIVE TO THE REPO, not product/rel. For a namespace-promoted
            # product (`assets` lives under `erpnext/`), `product/rel` is `assets/doctype/...`
            # which does not exist from the repo root - so the LLM adjudicator's _excerpt() read
            # nothing, judged the cluster on missing code, and silently left it a candidate.
            repo_rel = os.path.relpath(abs_path, repo_path)
            for t in terms:
                m = index.setdefault(t, {}).setdefault(product, Member(product, 0))
                m.loc += loc
                m.toil += toil
                if len(m.files) < 4:
                    m.files.append(repo_rel)

    clusters: list[DuplicateCluster] = []
    for term, by_product in index.items():
        members = sorted(
            (m for m in by_product.values()
             if m.loc >= MIN_MEMBER_LOC and m.toil >= MIN_MEMBER_TOIL),
            key=lambda m: -m.loc)
        # One owner plus a thin adapter is not duplication (see MIN_BALANCE).
        members = [m for m in members if m.loc >= members[0].loc * MIN_BALANCE] if members else []
        if len(members) < MIN_PRODUCTS:
            continue
        clusters.append(DuplicateCluster(term=term, label=label_for(term), members=members))

    # Rank by the code ONE agent would retire, not by how many products it touches.
    # Member count alone put ERPNext's 4-product `scheduling` cluster (3.7k LOC - and quite
    # possibly a coincidence: an asset depreciation schedule and a maintenance schedule may
    # simply share a word) ahead of its 3-product `reconciliation` cluster (16.8k LOC across
    # three substantial engines, two of which reconcile bank statements). That is exactly
    # backwards: it leads the report with the weakest claim in it. Volume of duplicated logic
    # is the better proxy for both the value of the merge and our confidence in it.
    clusters.sort(key=lambda c: (-c.loc, -len(c.members), c.term))
    return clusters


# --------------------------------------------------------------------------------------
# LLM adjudication - the difference between "these files share a word" and "these are the
# same job". This is the one claim in the whole report we should be most afraid of getting
# wrong: telling someone to replace three working systems with one agent, when they are
# actually three different jobs that happen to share a noun, is real damage.
#
# So the model is asked to REJECT by default, and a cluster it does not actively confirm is
# DROPPED - not shown with a lower confidence. `stock_reconciliation` (counting warehouse
# inventory against a physical count) and `payment_reconciliation` (matching invoices to
# incoming payments) share a word and are not the same job; only reading the code can tell.
# --------------------------------------------------------------------------------------

_SYSTEM = (
    "You are a skeptical staff engineer. Several modules in one codebase appear to implement "
    "the same job. Your task is to find the LARGEST SUBSET of them that genuinely do the same "
    "work - same kind of inputs, same kind of decision, same kind of output - such that ONE AI "
    "agent could own all of that subset. Modules that merely share a word are NOT the same job: "
    "bank reconciliation (matching bank payments to a statement) and stock reconciliation "
    "(counting warehouse inventory against a physical count) share the word 'reconciliation' and "
    "are different work. Be strict: it is better to return a smaller subset you are sure about, "
    "or none at all, than to lump in a module that is really doing something else."
)

# We ask for the SUBSET that belongs together, not a yes/no on the whole cluster. The heuristic
# groups by a shared word, so a cluster of 3 is often really a true pair plus one impostor -
# `{banking, accounts, stock}` reconciliation is bank+bank+inventory. A whole-cluster MERGE/
# SEPARATE verdict then throws the true `{banking, accounts}` duplicate out with the `stock`
# impostor. Naming the subset keeps the real finding.
_ASK = (
    "The candidate modules are listed above, each with a PRODUCT name. Find the LARGEST GROUP "
    "of two or more that do the same job. IMPORTANT: if two of them clearly do the same job and "
    "a third does something different, the answer is those TWO - not NONE. Return NONE only when "
    "no two of them genuinely share a job. Answer in exactly three lines, nothing else:\n"
    "SAME: a comma-separated list of the PRODUCT names (exactly as written above) that do the "
    "same job - at least two - or the single word NONE.\n"
    "WHY: one sentence, grounded in what the code actually does, on why those belong together "
    "(or why none do).\n"
    "AGENT: one sentence on what the single combined agent would do (or - if NONE)."
)

_EXCERPT = 900


def _excerpt(repo_path: str, member: Member) -> str:
    """A real slice of this member's biggest file - the model must judge code, not names."""
    for rel in member.files:
        try:
            with open(os.path.join(repo_path, rel), "r", encoding="utf-8",
                      errors="replace") as fh:
                text = fh.read(_EXCERPT)
            if text.strip():
                return f"--- {rel} ---\n{text}"
        except OSError:
            continue
    return ""


def adjudicate(clusters: list[DuplicateCluster], repo_path: str, provider=None,
               budget=None, limit: int = 6) -> tuple[list[DuplicateCluster], bool]:
    """Confirm or kill each candidate by reading code. Returns (clusters, ai_ran).

    With no key (or on any failure) the heuristic candidates pass through untouched and the
    report says so - they stay labelled as candidates, which is what they are.
    """
    from .llm_client import ask, available
    if not available(provider):
        return clusters, False

    kept: list[DuplicateCluster] = []
    try:
        for i, c in enumerate(clusters):
            if i >= limit or (budget is not None and budget.exhausted):
                kept.append(c)                    # past the budget: keep the honest candidate
                continue
            excerpts = "\n\n".join(
                e for e in (_excerpt(repo_path, m) for m in c.members) if e)
            if not excerpts:
                kept.append(c)
                continue
            where = "\n".join(f"- {m.product}: {m.loc} LOC ({m.locator})" for m in c.members)
            reply = ask(_SYSTEM,
                        f"Candidate shared job: {c.label}\n\nImplemented separately in:\n{where}\n\n"
                        f"Code from each:\n{excerpts}\n\n{_ASK}",
                        provider=provider, budget=budget)
            if not reply:
                kept.append(c)
                continue
            same, why, agent = _parse(reply, {m.product for m in c.members})
            if len(same) < MIN_PRODUCTS:
                continue                          # the model found no real duplicate here. Drop it.
            # Re-form the cluster around exactly the members the model endorsed. A 3-way
            # candidate can survive as the true 2-way pair inside it, with the impostor removed.
            c.members = [m for m in c.members if m.product in same]
            c.origin = "ai-confirmed"
            c.reason = why or c.reason
            if agent and agent != "-":
                c.agent_summary = agent
            kept.append(c)
        return kept, True
    except Exception:
        return clusters, False


def _parse(reply: str, valid: set[str]) -> tuple[set[str], str | None, str | None]:
    """Return (products-that-share-a-job, why, agent). Only product names actually in the
    cluster are honoured - the model cannot invent a member."""
    same: set[str] = set()
    why = agent = None
    lower = {v.lower(): v for v in valid}
    for line in reply.splitlines():
        s = line.strip()
        u = s.upper()
        if u.startswith("SAME:"):
            body = s.split(":", 1)[1]
            if "NONE" in body.upper():
                continue
            for tok in re.split(r"[,\s]+", body.lower()):
                if tok in lower:
                    same.add(lower[tok])
        elif u.startswith("WHY:"):
            why = s.split(":", 1)[1].strip()
        elif u.startswith("AGENT:"):
            agent = s.split(":", 1)[1].strip()
    return same, why, agent

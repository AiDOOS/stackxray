"""Language-extractor interface (Milestone 7).

Each language provides a LanguageExtractor that turns its files into CapabilityDrafts.
The orchestrator (extract/__init__.py) owns product discovery, id/name/parent assignment,
and roll-up - so extractors stay small and only encode language-specific conventions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

from ..models import AIClass, Evidence, Kind
from . import _scan, saas
from . import units as units_mod


@dataclass
class CapabilityDraft:
    """A capability found by an extractor, before the orchestrator gives it an id/parent.

    `suffix` is the human role/vendor label appended to the product name (e.g. "API /
    views" -> "billing: API / views"). `id_hint` is a stable id fragment (e.g. "api" or
    "saas:Stripe") so ids are deterministic across runs.
    """
    suffix: str
    id_hint: str
    kind: Kind = Kind.BUILT
    ai: AIClass = AIClass.NON_AI
    size_complexity: str | None = None
    dependencies: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    toil: int = 0                        # decision/rule constructs (agent-fit signal)
    readable: bool = True                # False = we could NOT parse it (a coverage gap)
    domain_unit: str = ""                # business unit, when the code is organised by domain
    role: str = ""                       # the ARCHITECTURAL role of its files (core/api/components)
    paths: list[str] = field(default_factory=list)   # representative files, for the scorer
    human_in_loop: bool = False          # process stops for a person (screen/approval) -> twin seam


@dataclass
class ProductContext:
    """What an extractor gets: the product's name/path and the subset of files (abs, rel)
    that match this extractor's extensions."""
    name: str
    path: str
    files: list[tuple[str, str]]


@runtime_checkable
class LanguageExtractor(Protocol):
    name: str
    extensions: tuple[str, ...]          # e.g. (".py",) or (".ts", ".tsx")
    product_markers: tuple[str, ...]     # files that mark a product of this language

    def extract_product(self, ctx: ProductContext) -> list[CapabilityDraft]:
        ...


def bucket_and_draft(
    ctx: ProductContext,
    *,
    role_of: Callable[[str], str | None],
    role_labels: dict[str, str],
    imports_of: Callable[[str], set[str]],
    id_prefix: str,
    lang_tag: str = "",
) -> list[CapabilityDraft]:
    """Shared logic for import-based languages (Python, JS, Java, C#, Go, C/C++).

    Buckets a product's files, sums LOC, unions imports, detects integrated-SaaS, and emits one
    built CapabilityDraft per bucket + one per SaaS vendor. Each language only supplies its own
    `role_of`, labels, and `imports_of` - everything else is common.

    A file is bucketed by its BUSINESS UNIT when it has one (`payment_reconciliation`,
    `BankReconciliation`), and by its architectural ROLE only when it does not (`utils.py`,
    `hooks/use-mobile.ts`). Bucketing everything by role is what produced ERPNext capabilities
    called "core logic" and "pages / routes" - names that cannot contain a domain word, so the
    agentify scorer could never fire on them and fell back to "big and non-AI, so agentify".
    See extract/units.py.
    """
    units: dict[str, dict] = {}
    roles: dict[str, dict] = {}
    saas_evidence: dict[str, str] = {}
    parsed: list[tuple[str, str, dict]] = []      # (rel, role, stats)

    def _bucket(store: dict, key: str) -> dict:
        return store.setdefault(key, {"loc": 0, "imps": set(), "files": [], "toil": 0,
                                      "roles": {}})

    def _add(b: dict, rel: str, st: dict, role: str = "") -> None:
        b["loc"] += st["loc"]
        b["toil"] += st["toil"]
        b["imps"] |= st["imps"]
        b["files"].append(rel)
        if role:
            b["roles"][role] = b["roles"].get(role, 0) + st["loc"]

    for abs_path, rel in ctx.files:
        role = role_of(rel)
        if role is None:
            continue
        text = _scan.read_text(abs_path)
        imps = imports_of(text)
        for vendor, _tok in saas.detect_saas(imps).items():
            saas_evidence.setdefault(vendor, rel)
        st = {"loc": _scan.count_loc(text), "toil": _scan.count_toil(text), "imps": imps}
        parsed.append((rel, role, st))
        unit = units_mod.unit_key(rel)
        if unit:
            _add(_bucket(units, unit), rel, st, role)

    # A unit only earns its own capability if it holds real code. ERPNext has ~1000 doctypes and
    # most are small CRUD masters; naming every one of them would bury the twenty that matter.
    # Everything below the bar falls back to its layer bucket - so no file is ever dropped.
    kept = {u for u, d in units.items() if d["loc"] >= units_mod.MIN_UNIT_LOC}
    units = {u: d for u, d in units.items() if u in kept}
    for d in units.values():
        # the role that owns the most code in this unit
        d["role"] = max(d["roles"], key=lambda r: d["roles"][r]) if d["roles"] else ""
    for rel, role, st in parsed:
        unit = units_mod.unit_key(rel)
        if unit not in kept:
            _add(_bucket(roles, role), rel, st, role)

    tag = f" ({lang_tag})" if lang_tag else ""
    drafts: list[CapabilityDraft] = []

    def _draft(suffix: str, id_hint: str, data: dict, unit: str = "",
               role: str = "") -> CapabilityDraft:
        return CapabilityDraft(
            # The language belongs in the NAME, not just the evidence. A polyglot product
            # (ERPNext is Python + JS) otherwise emits two capabilities both called
            # "erpnext: core logic" - indistinguishable in the report, unmergeable downstream.
            suffix=f"{suffix}{tag}",
            id_hint=id_hint if not id_prefix else f"{id_prefix}:{id_hint}",
            kind=Kind.BUILT,
            ai=AIClass.AI if saas.looks_ai(data["imps"]) else AIClass.NON_AI,
            size_complexity=_scan.size_bucket(data["loc"]),
            dependencies=sorted(saas.detect_saas(data["imps"]).values()),
            toil=data["toil"],
            domain_unit=unit,
            role=role,
            paths=data["files"][:12],
            evidence=[Evidence("extract",
                               f"{len(data['files'])} module(s), ~{data['loc']} LOC{tag}",
                               locator=data["files"][0])],
        )

    for unit, data in units.items():
        # A unit inherits the role of the files in it. Without this, a React feature folder
        # (`features/CommandCenter/*.tsx`) looked exactly like a Python doctype to the scorer,
        # and AiDOOS's own front-end got nominated for rebuilding as AI agents.
        drafts.append(_draft(unit, f"unit:{unit.replace(' ', '-')}", data, unit=unit,
                             role=data["role"]))
    for role, data in roles.items():
        if data["loc"] == 0:
            continue
        drafts.append(_draft(role_labels[role], role, data, role=role))
    for vendor, locator in sorted(saas_evidence.items()):
        drafts.append(CapabilityDraft(
            suffix=f"{vendor} integration", id_hint=f"saas:{vendor}",
            kind=Kind.INTEGRATED_SAAS,
            ai=AIClass.AI if saas.vendor_is_ai(vendor) else AIClass.NON_AI,
            size_complexity="small",
            evidence=[Evidence("extract", f"integration glue to {vendor}{tag}", locator=locator)],
        ))
    return drafts

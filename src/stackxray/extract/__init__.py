"""Capability extraction (SPEC §5, §6; Milestone 7 - polyglot).

Orchestrates a registry of language extractors over a repo:
  discover products -> route each product's files to the matching native extractor(s)
  -> for code in languages with no native extractor, use the LLM universal track (with a
     key) or emit a VISIBLE gap capability (without one) -> assemble the multi-level map.

The spine downstream (join/verdict/report/consent) is language-neutral; only this
front-end knows about languages. Adding a language = adding one module under langs/.
"""

from __future__ import annotations

import os
import re

from ..config import ScanConfig
from ..models import AIClass, Capability, CapabilityMap, Evidence, Kind, Level
from . import _scan
from .base import CapabilityDraft, ProductContext
from .langs import EXTRACTORS
from .llm import get_enricher, universal_extract

# Languages with NO native extractor -> shown as gaps (or handed to the LLM track).
# (Java/C#/Go/C/C++/COBOL/RPG are now native, so they are NOT here.)
#
# ⚠️ EVERY unreadable language MUST be listed here. A file type that is neither extracted nor
# listed is SILENTLY DROPPED - and the report then says "0 opportunities", which a reader takes
# to mean "nothing to automate" when the truth is "we could not read your stack". That is a
# FALSE NEGATIVE dressed as a clean result, and it breaks the one promise the tool makes: it
# says so when it does not know. Salesforce Apex (.cls/.trigger) was exactly this bug - a real
# scan of a Salesforce app returned 0 opportunities while silently ignoring 9 Apex classes of
# business logic.
_LANG_BY_EXT = {
    ".kt": "Kotlin", ".kts": "Kotlin", ".groovy": "Groovy", ".vb": "VB.NET",
    ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".scala": "Scala", ".swift": "Swift",
    ".jcl": "JCL", ".pli": "PL/I", ".pl1": "PL/I", ".f": "Fortran", ".f90": "Fortran",
    ".ex": "Elixir", ".exs": "Elixir", ".dart": "Dart", ".pl": "Perl", ".pm": "Perl",
    ".lua": "Lua", ".r": "R", ".m": "Objective-C/MATLAB", ".erl": "Erlang",
    # Packaged-ERP business logic. These carry the core of an SAP/Oracle estate, and with a
    # key the LLM universal track now READS them (it needs no native parser). ABAP and PL/SQL
    # packages are specific enough not to collide with ordinary .sql migrations, which stay out.
    ".abap": "ABAP", ".pks": "PL/SQL", ".pkb": "PL/SQL", ".pls": "PL/SQL",
    ".plb": "PL/SQL", ".plsql": "PL/SQL",
    ".al": "AL (Dynamics 365 BC)", ".xpp": "X++ (Dynamics 365 F&O)",
    # Mainstream languages with no native parser - flagged before, read now (with a key).
    ".fs": "F#", ".fsx": "F#", ".clj": "Clojure", ".cljs": "Clojure", ".hs": "Haskell",
    ".jl": "Julia", ".nim": "Nim", ".cr": "Crystal", ".ml": "OCaml", ".tcl": "Tcl",
    ".zig": "Zig", ".hack": "Hack",
}

_EXACT_MARKERS = {m for ex in EXTRACTORS for m in ex.product_markers} | {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "package.json",
    "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile",
    "composer.json", "Cargo.toml", "CMakeLists.txt", "Makefile",
}
_SUFFIX_MARKERS = (".csproj", ".sln", ".vcxproj")
_HANDLED_EXTS = tuple(e for ex in EXTRACTORS for e in ex.extensions)
_ALL_CODE_EXTS = tuple(set(_HANDLED_EXTS) | set(_LANG_BY_EXT))
# discovery-only: a repo that is entirely ServiceNow/Salesforce XML holds no .py/.js,
# so without this its dirs would never be seen as products at all.
_DISCOVERY_EXTS = tuple(set(_ALL_CODE_EXTS) | {'.xml'})


_GAP_EXTS = tuple(_LANG_BY_EXT)  # none overlap _HANDLED_EXTS by construction


def _is_product_dir(path: str) -> bool:
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    if any(e in _EXACT_MARKERS for e in entries) or any(e.endswith(_SUFFIX_MARKERS) for e in entries):
        return True
    # A top-level dir that directly holds code of ANY known language is a product - this is
    # what lets manifest-less legacy estates (COBOL/RPG) be seen instead of skipped.
    return next(_scan.iter_files(path, _DISCOVERY_EXTS), None) is not None


# --------------------------------------------------------------------------------------
# Product discovery - unwrapping namespace packages (the "erpnext/ problem")
#
# Taking every top-level directory as a product is wrong for the most common real layout
# there is: one namespace package (or one `src/`, `apps/`, `packages/`, `services/`) that
# holds the actual business modules a level down. Scanned naively, ERPNext is TWO products
# ("erpnext", "banking") and its 30 business domains - accounts, stock, selling, buying,
# manufacturing - are invisible, melted into one bucket. Nothing downstream can find
# duplicated work across modules it cannot see.
#
# So we UNWRAP a directory into its children, under two rules that keep it honest:
#
#   1. NEVER DROP CODE. We only unwrap when the children we promote hold essentially all
#      of the directory's code (COVERAGE). Whatever code the wrapper itself still holds
#      (erpnext/hooks.py) stays scanned, as the wrapper's own product, via `exclude`.
#
#   2. A NAME THAT REPEATS ACROSS SIBLINGS IS STRUCTURE, NOT A DOMAIN. Every ERPNext module
#      contains `doctype/`, `report/`, `page/`; every Django app contains `migrations/`,
#      `templates/`. That repetition is the giveaway: these are framework scaffolding, not
#      business capabilities. Promoting them would produce 191 "products" called `doctype`.
#      Rule 2 is what makes rule 1 bite: with doctype/report/page ineligible, `accounts`
#      fails COVERAGE (they hold ~95% of its code) and correctly stays one product - while
#      `erpnext`, whose children ARE the domains, passes and unwraps.
#
# Framework-agnostic by construction: it reads the shape of the tree, not a list of known
# frameworks. Frappe, Django, Rails, Nx, Maven multi-module all fall out of the same test.
# --------------------------------------------------------------------------------------

MAX_PRODUCT_DEPTH = 3      # stop descending; guards pathological trees
MIN_PROMOTABLE = 3         # fewer children than this and it is a module, not a namespace
COVERAGE = 0.75            # promotable children must hold most of the code, or this is a module
MIN_OWN_LOC = 100          # below this, a wrapper's leftover code is not worth its own product
MAX_PRODUCTS = 80          # a split this wide is noise, not insight

# Never a business domain, in any framework: framework plumbing, static assets, i18n, test and
# patch archives. These are NOT promoted to products - but their code is still scanned, as part
# of the parent's own product. Nothing is hidden; it just does not get called a business domain.
_NOT_A_DOMAIN = {
    "patches", "www", "public", "static", "templates", "tests", "test", "spec", "specs",
    "docs", "doc", "examples", "example", "demo", "locale", "locales", "i18n", "translations",
    "gettext", "fixtures", "scripts", "tools", "config", "conf", "settings", "includes",
    "startup", "commands", "typings", "types", "stubs", "assets_src",
    "records", "update", "update_set",   # ServiceNow scoped-app dirs
}
# `v14_0`, `v2_1_3`, `20240115_add_x` - a patch/migration archive, not a capability. Frappe
# names them v<major>_<minor>; Django/Rails/Flyway use dates. Either way: not a domain.
_VERSIONED = re.compile(r"^(v\d+([._-]\d+)*|\d{6,}.*|\d+([._-]\d+)+)$", re.IGNORECASE)


def _is_domain_name(name: str) -> bool:
    return name.lower() not in _NOT_A_DOMAIN and not _VERSIONED.match(name)


def _code_children(path: str) -> list[str]:
    """Immediate subdirectories that contain code of any language we know."""
    out = []
    try:
        entries = sorted(os.listdir(path))
    except OSError:
        return out
    for e in entries:
        p = os.path.join(path, e)
        if not os.path.isdir(p) or e in _scan.IGNORE_DIRS or e.startswith("."):
            continue
        if next(_scan.iter_files(p, _ALL_CODE_EXTS), None) is not None:
            out.append(e)
    return out


def _tree_loc(path: str, exclude_top: frozenset[str] = frozenset()) -> int:
    return sum(_scan.count_loc(_scan.read_text(a))
               for a, _ in _scan.iter_files(path, _ALL_CODE_EXTS, exclude_top))


def _structural_names(paths: list[str]) -> set[str]:
    """Child-directory names that recur across siblings - framework scaffolding, not domains."""
    seen: dict[str, int] = {}
    for p in paths:
        for name in set(_code_children(p)):
            seen[name] = seen.get(name, 0) + 1
    return {n for n, c in seen.items() if c >= 2}


def _discover_products(repo_path: str) -> list[tuple[str, str, frozenset[str]]]:
    """Return (name, path, exclude_top) per product, unwrapping namespace packages."""
    frontier = [(e, os.path.join(repo_path, e))
                for e in sorted(os.listdir(repo_path))
                if os.path.isdir(os.path.join(repo_path, e))
                and e not in _scan.IGNORE_DIRS and not e.startswith(".")
                and _is_product_dir(os.path.join(repo_path, e))]

    settled: list[tuple[str, str, frozenset[str]]] = []
    for _ in range(MAX_PRODUCT_DEPTH):
        if not frontier:
            break
        structural = _structural_names([p for _, p in frontier])
        nxt: list[tuple[str, str]] = []
        for name, path in frontier:
            promotable = [c for c in _code_children(path)
                          if c not in structural and _is_domain_name(c)]
            total = _tree_loc(path)
            kept = sum(_tree_loc(os.path.join(path, c)) for c in promotable)
            unwrap = (len(promotable) >= MIN_PROMOTABLE and total > 0
                      and kept / total >= COVERAGE
                      and len(settled) + len(nxt) + len(promotable) <= MAX_PRODUCTS)
            if not unwrap:
                settled.append((name, path, frozenset()))
                continue
            excl = frozenset(promotable)
            # Rule 1: the wrapper's own leftover code is still scanned - never dropped.
            if _tree_loc(path, excl) >= MIN_OWN_LOC:
                settled.append((name, path, excl))
            nxt.extend((c, os.path.join(path, c)) for c in promotable)
        frontier = nxt
    settled.extend((n, p, frozenset()) for n, p in frontier)

    # Promoted children are named by their own directory (`accounts`, not `erpnext/accounts`).
    # Qualify only on a real collision, so names stay readable.
    counts: dict[str, int] = {}
    for n, _, _ in settled:
        counts[n] = counts.get(n, 0) + 1
    out = []
    for n, p, x in settled:
        label = n if counts[n] == 1 else os.path.join(os.path.basename(os.path.dirname(p)), n)
        out.append((label, p, x))
    return sorted(out)


def _gap_drafts(product_path: str,
                exclude: frozenset[str] = frozenset()) -> list[CapabilityDraft]:
    """One VISIBLE capability per unsupported language present (SPEC §4.4 honesty)."""
    langs: dict[str, dict] = {}
    for ext, lang in _LANG_BY_EXT.items():
        if ext in _HANDLED_EXTS:
            continue
        for abs_path, rel in _scan.iter_files(product_path, (ext,), exclude):
            b = langs.setdefault(lang, {"loc": 0, "files": []})
            b["loc"] += _scan.count_loc(_scan.read_text(abs_path))
            b["files"].append(rel)
    drafts = []
    for lang, data in langs.items():
        drafts.append(CapabilityDraft(
            suffix=f"{lang} code (not yet extracted)", id_hint=f"lang:{lang}",
            kind=Kind.BUILT, ai=AIClass.UNKNOWN, readable=False,
            size_complexity=_scan.size_bucket(data["loc"]),
            evidence=[Evidence("extract",
                               f"{len(data['files'])} {lang} file(s), ~{data['loc']} LOC - "
                               f"needs a native parser or the LLM track",
                               locator=data["files"][0])],
        ))
    return drafts


def _repo_rel(prefix: str, p: str | None) -> str | None:
    """A product-relative path, made relative to the REPO ROOT by prefixing the product's own
    location. This is what lets anything DOWNSTREAM actually open the file: an extractor yields
    paths relative to the product it scanned (`doctype/x/x.py`), but the product may sit under a
    namespace wrapper (`erpnext/accounts/`), so `repo_path + product_rel` misses the file
    entirely - which is exactly why the LLM re-judge pass read nothing and every reason fell
    back to the template."""
    if not p:
        return p
    return os.path.join(prefix, p).replace("\\", "/") if prefix and prefix != "." else p.replace("\\", "/")


# Files that are legitimately not business logic - never report these as an unread gap.
# Everything NOT here and NOT handled by an extractor gets surfaced (see _unrecognized_drafts).
_NOT_CODE = {
    # prose / docs
    ".md", ".txt", ".rst", ".adoc", ".pdf", ".license",
    # config / data / lockfiles
    ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".env", ".properties",
    ".lock", ".csv", ".tsv", ".xsd", ".dtd", ".plist", ".gradle", ".bazel",
    ".sqlite3", ".sqlite", ".db", ".mdx", ".ipynb", ".log",
    # Generic XML is config (pom.xml, web.xml, spring). Salesforce metadata is claimed
    # precisely by `-meta.xml` in salesforce.py. ⚠️ KNOWN GAP: a ServiceNow update set
    # is ALSO .xml and IS business logic - we cannot read it and do not yet flag it.
    ".xml",
    # markup / styling - UI, not business logic
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".styl", ".vue.css",
    # assets
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".bmp", ".mp4", ".mov",
    ".mp3", ".wav", ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # build output / binaries
    ".map", ".class", ".jar", ".war", ".exe", ".dll", ".so", ".dylib", ".wasm", ".o", ".a",
    ".zip", ".gz", ".tar", ".rar", ".7z", ".pyc", ".pyo",
    # vcs / tooling dotfiles
    ".gitignore", ".gitattributes", ".gitkeep", ".editorconfig", ".dockerignore",
    ".npmignore", ".eslintrc", ".prettierrc", ".babelrc", ".nvmrc", ".sample",
}

# Below this we do not bother reporting - a couple of stray files is noise, a body of code is
# a coverage gap the reader deserves to know about.
MIN_UNREAD_LOC = 200


def _unrecognized_drafts(product_path: str,
                         exclude: frozenset[str] = frozenset()) -> list[CapabilityDraft]:
    """Report code we walked past and could NOT read.

    This is the honesty firewall applied to COVERAGE rather than to verdicts, and it is
    self-defending: `_LANG_BY_EXT` only protects against stacks we thought of, but any file
    type that is neither extracted nor listed there is silently dropped - and the report then
    says "0 opportunities", which reads as "nothing to automate" when the truth is "we could
    not read your stack". Salesforce Apex was exactly that bug. This catches the NEXT one
    without anyone having to predict it.
    """
    seen: dict[str, dict] = {}
    for abs_path, rel in _scan.iter_files(product_path, ("",), exclude):
        ext = os.path.splitext(rel)[1].lower()
        if not ext or ext in _NOT_CODE or ext in _HANDLED_EXTS or ext in _GAP_EXTS:
            continue
        b = seen.setdefault(ext, {"loc": 0, "files": []})
        b["loc"] += _scan.count_loc(_scan.read_text(abs_path))
        b["files"].append(rel)

    drafts = []
    for ext, data in sorted(seen.items(), key=lambda kv: -kv[1]["loc"]):
        if data["loc"] < MIN_UNREAD_LOC:
            continue
        drafts.append(CapabilityDraft(
            suffix=f"{ext} files (not read)", id_hint=f"unread:{ext.lstrip('.')}",
            kind=Kind.BUILT, ai=AIClass.UNKNOWN, readable=False,
            size_complexity=_scan.size_bucket(data["loc"]),
            evidence=[Evidence("extract",
                               f"{len(data['files'])} {ext} file(s), ~{data['loc']} LOC - "
                               f"StackXray has no parser for this file type, so nothing here "
                               f"was assessed. This is a coverage gap, not a finding of 'no "
                               f"opportunities'.",
                               locator=data["files"][0])],
        ))
    return drafts


def _to_capability(draft: CapabilityDraft, product_name: str, product_id: str,
                   prefix: str = "") -> Capability:
    evidence = [Evidence(e.source, e.detail, _repo_rel(prefix, e.locator)) for e in draft.evidence]
    return Capability(
        id=f"cap:{product_name}:{draft.id_hint}",
        name=f"{product_name}: {draft.suffix}",
        level=Level.CAPABILITY, parent_id=product_id, kind=draft.kind,
        ai_or_not=draft.ai, size_complexity=draft.size_complexity,
        dependencies=list(draft.dependencies), evidence=evidence,
        toil_signal=draft.toil,
        domain_unit=draft.domain_unit, role=draft.role, readable=draft.readable,
        paths=[_repo_rel(prefix, p) for p in draft.paths],
        human_in_loop=draft.human_in_loop,
    )


def _extract_product(product_name: str, product_path: str, portfolio_id: str,
                     config: ScanConfig, exclude: frozenset[str] = frozenset(),
                     repo_path: str = "", provider=None, budget=None) -> list[Capability]:
    product_id = f"prod:{product_name}"
    caps: list[Capability] = [Capability(
        id=product_id, name=product_name, level=Level.PRODUCT,
        parent_id=portfolio_id, kind=Kind.BUILT)]

    drafts: list[CapabilityDraft] = []
    for extractor in EXTRACTORS:
        files = list(_scan.iter_files(product_path, extractor.extensions, exclude))
        if files:
            drafts += extractor.extract_product(ProductContext(product_name, product_path, files))

    # languages with no native extractor: LLM universal track (with key), else visible gap.
    gap_files = list(_scan.iter_files(product_path, _GAP_EXTS, exclude))
    if gap_files:
        llm_drafts = universal_extract(product_name, gap_files, provider=provider, budget=budget)
        drafts += llm_drafts if llm_drafts is not None else _gap_drafts(product_path, exclude)


    # Where this product sits relative to the repo root, so downstream can resolve its files.
    prefix = os.path.relpath(product_path, repo_path) if repo_path else ""
    if not drafts:
        return []                     # nothing extractable here - do not emit a hollow product
    caps.extend(_to_capability(d, product_name, product_id, prefix) for d in drafts)
    return caps


def extract_capabilities(config: ScanConfig, provider=None, budget=None) -> CapabilityMap:
    """Parse the repo into a multi-level map (portfolio/product/capability), then enrich.

    Structural passes are deterministic and network-free. `provider` (the same one the agentify
    pass uses) drives the LLM universal track: languages with no native parser get READ instead of
    flagged as a coverage gap. No provider -> those stacks stay honestly labelled "not read".
    """
    repo_path = os.path.abspath(config.repo_path)
    portfolio_id = "portfolio:root"
    portfolio = Capability(
        id=portfolio_id, name=os.path.basename(repo_path.rstrip(os.sep)) or "portfolio",
        level=Level.PORTFOLIO, kind=Kind.BUILT)
    capabilities: list[Capability] = [portfolio]
    for product_name, product_path, exclude in _discover_products(repo_path):
        capabilities.extend(
            _extract_product(product_name, product_path, portfolio_id, config, exclude,
                             repo_path=repo_path, provider=provider, budget=budget))

    # Coverage gaps are reported REPO-WIDE, not per product - because the failure is worse one
    # level up: `_is_product_dir` only recognises a directory as a product if it holds a
    # language we know, so a whole SAP/ABAP estate is not merely unread, it is never DISCOVERED.
    # That returns 0 products / 0 capabilities / "0 opportunities" on a repo full of business
    # logic, and says it as if it were a clean result. Reporting at the repo level catches both
    # cases: code we cannot read inside a product, and code in a directory that never became one.
    unread = _unrecognized_drafts(repo_path)
    if unread:
        gap_id = "prod:not-read"
        capabilities.append(Capability(id=gap_id, name="Not read", level=Level.PRODUCT,
                                       parent_id=portfolio_id, kind=Kind.BUILT))
        capabilities.extend(_to_capability(d, "Not read", gap_id) for d in unread)

    enricher = get_enricher(config.llm)
    capabilities = [enricher.enrich(c, code_context="") for c in capabilities]
    return CapabilityMap(capabilities=capabilities, scan_id=f"scan:{os.path.basename(repo_path)}")

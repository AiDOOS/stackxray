"""COBOL extractor (Milestone 7d) - the legacy/mainframe wedge, keyless & structural.

COBOL has no imports, so this is bespoke: it inventories PROGRAMS, their external CALL
graph (what calls what), and COPY/copybook usage - the structural skeleton an enterprise
can no longer read. This runs offline with no key; the LLM universal track (llm.py) adds
semantic purpose on top when a key is supplied. This is the "Core Knowledge Capture" play.
"""

from __future__ import annotations

import re

from ...models import AIClass, Evidence, Kind
from .. import _scan
from ..base import CapabilityDraft, ProductContext

_CALL_RE = re.compile(r"""\bCALL\s+['"]([A-Z0-9_$-]+)['"]""", re.IGNORECASE)
_COPY_RE = re.compile(r"""\bCOPY\s+([A-Z0-9_$-]+)""", re.IGNORECASE)
_PROGID_RE = re.compile(r"""\bPROGRAM-ID\.\s+([A-Z0-9_$-]+)""", re.IGNORECASE)

_PROGRAM_EXTS = (".cbl", ".cob", ".pco")
_COPYBOOK_EXTS = (".cpy",)


class CobolExtractor:
    name = "cobol"
    extensions = (".cbl", ".cob", ".pco", ".cpy")
    product_markers = ()  # legacy dirs rarely have manifests; detected via code presence

    def extract_product(self, ctx: ProductContext) -> list[CapabilityDraft]:
        prog_loc = copy_loc = prog_toil = 0
        programs: set[str] = set()
        calls: set[str] = set()
        copybooks: set[str] = set()
        prog_files: list[str] = []
        copy_files: list[str] = []

        for abs_path, rel in ctx.files:
            text = _scan.read_text(abs_path)
            loc = _scan.count_loc(text)
            if rel.lower().endswith(_COPYBOOK_EXTS):
                copy_loc += loc
                copy_files.append(rel)
                continue
            prog_loc += loc
            prog_toil += _scan.count_toil(text)
            prog_files.append(rel)
            programs.update(_PROGID_RE.findall(text))
            calls.update(c.upper() for c in _CALL_RE.findall(text))
            copybooks.update(c.upper() for c in _COPY_RE.findall(text))

        drafts: list[CapabilityDraft] = []
        if prog_files:
            # external calls = programs called but not defined in this product = integration edges
            external = sorted(calls - {p.upper() for p in programs})
            detail = (f"{len(prog_files)} COBOL program(s), ~{prog_loc} LOC; "
                      f"{len(programs)} PROGRAM-ID(s), {len(external)} external CALL target(s)")
            drafts.append(CapabilityDraft(
                suffix="COBOL programs", id_hint="cobol:programs", kind=Kind.BUILT,
                ai=AIClass.NON_AI, size_complexity=_scan.size_bucket(prog_loc),
                dependencies=external[:20], toil=prog_toil,
                evidence=[Evidence("extract", detail, locator=prog_files[0])],
            ))
        if copy_files:
            drafts.append(CapabilityDraft(
                suffix="COBOL copybooks (data structures)", id_hint="cobol:copybooks",
                kind=Kind.BUILT, ai=AIClass.NON_AI, size_complexity=_scan.size_bucket(copy_loc),
                evidence=[Evidence("extract", f"{len(copy_files)} copybook(s), ~{copy_loc} LOC",
                                   locator=copy_files[0])],
            ))
        return drafts

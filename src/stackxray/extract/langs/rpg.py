"""RPG extractor (Milestone 7d) - IBM i / AS400 legacy, keyless & structural.

Like COBOL: inventories RPG programs, their CALL/CALLP graph, /COPY usage, and flags
embedded SQL. Offline, no key; the LLM track adds semantics on top."""

from __future__ import annotations

import re

from ...models import AIClass, Evidence, Kind
from .. import _scan
from ..base import CapabilityDraft, ProductContext

_CALL_RE = re.compile(r"""\bCALL[BP]?\s*\(?\s*['"]?([A-Z0-9_$#@-]+)""", re.IGNORECASE)
_COPY_RE = re.compile(r"""/COPY\s+([A-Z0-9_$#@,.-]+)""", re.IGNORECASE)
_SQL_RE = re.compile(r"""\bEXEC\s+SQL\b""", re.IGNORECASE)


class RpgExtractor:
    name = "rpg"
    extensions = (".rpg", ".rpgle", ".sqlrpgle")
    product_markers = ()

    def extract_product(self, ctx: ProductContext) -> list[CapabilityDraft]:
        loc = toil = 0
        files: list[str] = []
        calls: set[str] = set()
        uses_sql = False

        for abs_path, rel in ctx.files:
            text = _scan.read_text(abs_path)
            loc += _scan.count_loc(text)
            toil += _scan.count_toil(text)
            files.append(rel)
            calls.update(c.upper() for c in _CALL_RE.findall(text))
            uses_sql = uses_sql or bool(_SQL_RE.search(text))

        if not files:
            return []
        detail = (f"{len(files)} RPG program(s), ~{loc} LOC; {len(calls)} CALL target(s)"
                  + ("; uses embedded SQL" if uses_sql else ""))
        return [CapabilityDraft(
            suffix="RPG programs", id_hint="rpg:programs", kind=Kind.BUILT,
            ai=AIClass.NON_AI, size_complexity=_scan.size_bucket(loc),
            dependencies=sorted(calls)[:20], toil=toil,
            evidence=[Evidence("extract", detail, locator=files[0])],
        )]

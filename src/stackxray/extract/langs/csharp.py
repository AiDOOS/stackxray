"""C# / .NET extractor (Milestone 7b) - ASP.NET / EF conventions.

Products are detected by the global .csproj/.sln suffix markers, so product_markers here
is empty (the orchestrator's suffix rule covers it)."""

from __future__ import annotations

import os
import re

from ..base import ProductContext, bucket_and_draft

_USING_RE = re.compile(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;", re.MULTILINE)

_ROLE_LABEL = {
    "api": "API / controllers",
    "services": "service layer",
    "data-model": "data model / persistence",
    "core": "core logic",
}


def _imports_of(text: str) -> set[str]:
    return set(_USING_RE.findall(text))


def _role_of(rel_path: str) -> str | None:
    p = rel_path.replace("\\", "/").lower()
    name = os.path.basename(p)[:-3]  # strip .cs
    if name.endswith(("test", "tests")) or name in ("program", "startup") or ".designer" in name:
        return None
    if name.endswith("controller") or "/controllers" in f"/{p}":
        return "api"
    if name.endswith(("service", "manager", "handler")) or "/services" in f"/{p}":
        return "services"
    if (name.endswith(("repository", "dbcontext", "entity", "model")) or "/models" in f"/{p}"
            or "/entities" in f"/{p}" or "/data" in f"/{p}"):
        return "data-model"
    return "core"


class CSharpExtractor:
    name = "csharp"
    extensions = (".cs",)
    product_markers = ()  # detected via global .csproj/.sln suffix markers

    def extract_product(self, ctx: ProductContext):
        return bucket_and_draft(ctx, role_of=_role_of, role_labels=_ROLE_LABEL,
                                imports_of=_imports_of, id_prefix="cs", lang_tag="C#")

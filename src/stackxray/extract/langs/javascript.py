"""JavaScript / TypeScript extractor (Milestone 7) - JS/TS/React conventions."""

from __future__ import annotations

import os
import re

from ..base import ProductContext, bucket_and_draft

# module specifiers from: `from 'x'`, `require('x')`, `import('x')`, side-effect `import 'x'`
_SPEC_RE = re.compile(r"""(?:\bfrom\s*|\brequire\(\s*|\bimport\(\s*|\bimport\s+)['"]([^'"]+)['"]""")

_ROLE_LABEL = {
    "state": "state management",
    "pages": "pages / routes",
    "hooks": "hooks",
    "services": "service layer",
    "components": "UI components",
    "core": "core logic",
}


def _package_of(spec: str) -> str | None:
    if not spec or spec.startswith(".") or spec.startswith("/"):
        return None
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def _imports_of(text: str) -> set[str]:
    return {p for m in _SPEC_RE.findall(text) if (p := _package_of(m))}


def _role_of(rel_path: str) -> str | None:
    p = rel_path.replace("\\", "/").lower()
    name = os.path.basename(p)
    if (name.endswith(".d.ts") or ".test." in name or ".spec." in name
            or ".stories." in name or "/__tests__/" in f"/{p}" or "/__mocks__/" in f"/{p}"):
        return None
    # Browser-delivered assets (`public/`, `static/`, `assets/`, `www/`) are UI, whatever they
    # contain. ERPNext ships 16K LOC of client-side form scripts under public/js; falling through
    # to "core logic" made them look like server-side business logic and nominated them for an
    # AI agent. They are form behaviour running in someone's browser.
    if any(seg in f"/{p}" for seg in ("/public/", "/static/", "/assets/", "/www/")):
        return "components"
    # A single-file component (Vue/Svelte) is a UI unit - a <template> + <script> + <style> in
    # one file. We read it (so it is not a "not read" coverage gap), but it is frontend, not
    # server logic, so it is classified as UI here and never nominated as an agent.
    if name.endswith((".vue", ".svelte")):
        return "components"
    if "/store/" in f"/{p}" or "redux" in p or name.endswith(("slice.ts", "slice.js", "reducer.ts", "reducer.js")):
        return "state"
    if "/pages/" in f"/{p}" or "/routes/" in f"/{p}" or name.endswith(("route.ts", "routes.ts", "routes.tsx")):
        return "pages"
    if "/hooks/" in f"/{p}" or name.startswith("use"):
        return "hooks"
    if "/services/" in f"/{p}" or "/api/" in f"/{p}" or "api" in name or "client" in name:
        return "services"
    if "/components/" in f"/{p}" or name.endswith((".jsx", ".tsx")):
        return "components"
    return "core"


class JavaScriptExtractor:
    name = "javascript"
    extensions = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte")
    product_markers = ("package.json",)

    def extract_product(self, ctx: ProductContext):
        return bucket_and_draft(ctx, role_of=_role_of, role_labels=_ROLE_LABEL,
                                imports_of=_imports_of, id_prefix="js", lang_tag="JS/TS")

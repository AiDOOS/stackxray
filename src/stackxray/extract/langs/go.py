"""Go extractor (Milestone 7b) - Go package conventions."""

from __future__ import annotations

import os
import re

from ..base import ProductContext, bucket_and_draft

_SINGLE_IMPORT = re.compile(r'^\s*import\s+"([^"]+)"', re.MULTILINE)
_IMPORT_BLOCK = re.compile(r"import\s*\((.*?)\)", re.DOTALL)
_QUOTED = re.compile(r'"([^"]+)"')

_ROLE_LABEL = {
    "api": "API / handlers",
    "services": "service layer",
    "data-model": "data / storage",
    "background-jobs": "background jobs",
    "core": "core logic",
}


def _imports_of(text: str) -> set[str]:
    paths = set(_SINGLE_IMPORT.findall(text))
    for block in _IMPORT_BLOCK.findall(text):
        paths |= set(_QUOTED.findall(block))
    # keep full module path so 'github.com/stripe/stripe-go' matches the 'stripe' signature
    return paths


def _role_of(rel_path: str) -> str | None:
    p = rel_path.replace("\\", "/").lower()
    name = os.path.basename(p)[:-3]  # strip .go
    if name.endswith("_test") or name == "main":
        return None
    if "handler" in name or "http" in name or "router" in name or "api" in name or "/handlers" in f"/{p}":
        return "api"
    if "service" in name or "/service" in f"/{p}":
        return "services"
    if ("repo" in name or "store" in name or "dao" in name or "model" in name or "db" in name
            or "/store" in f"/{p}" or "/repository" in f"/{p}"):
        return "data-model"
    if "worker" in name or "job" in name or "cron" in name or "consumer" in name:
        return "background-jobs"
    return "core"


class GoExtractor:
    name = "go"
    extensions = (".go",)
    product_markers = ("go.mod",)

    def extract_product(self, ctx: ProductContext):
        return bucket_and_draft(ctx, role_of=_role_of, role_labels=_ROLE_LABEL,
                                imports_of=_imports_of, id_prefix="go", lang_tag="Go")

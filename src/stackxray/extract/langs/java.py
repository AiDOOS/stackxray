"""Java extractor (Milestone 7b) - Java / Spring conventions."""

from __future__ import annotations

import os
import re

from ..base import ProductContext, bucket_and_draft

_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.MULTILINE)

_ROLE_LABEL = {
    "api": "API / controllers",
    "services": "service layer",
    "data-model": "data model / persistence",
    "core": "core logic",
}


def _imports_of(text: str) -> set[str]:
    # keep the full dotted path so substring SaaS matching sees 'com.stripe...' etc.
    return set(_IMPORT_RE.findall(text))


def _role_of(rel_path: str) -> str | None:
    p = rel_path.replace("\\", "/").lower()
    name = os.path.basename(p)[:-5]  # strip .java
    if name.endswith(("test", "tests", "application", "config", "configuration")):
        return None
    if name.endswith(("controller", "resource", "endpoint")) or "/controller" in f"/{p}":
        return "api"
    if name.endswith(("service", "serviceimpl", "manager")) or "/service" in f"/{p}":
        return "services"
    if (name.endswith(("repository", "dao", "entity", "model")) or "/entity" in f"/{p}"
            or "/domain" in f"/{p}" or "/repository" in f"/{p}" or "/model" in f"/{p}"):
        return "data-model"
    return "core"


class JavaExtractor:
    name = "java"
    extensions = (".java",)
    product_markers = ("pom.xml", "build.gradle", "build.gradle.kts")

    def extract_product(self, ctx: ProductContext):
        return bucket_and_draft(ctx, role_of=_role_of, role_labels=_ROLE_LABEL,
                                imports_of=_imports_of, id_prefix="java", lang_tag="Java")

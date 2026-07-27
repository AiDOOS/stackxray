"""Python extractor (Milestone 7) - Django/Python conventions.

Reference extractor: maps .py files to capabilities by role and detects integrated-SaaS
from imports. Other import-based languages follow this exact shape via bucket_and_draft.
"""

from __future__ import annotations

import os
import re

from ..base import ProductContext, bucket_and_draft

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z0-9_.]+)", re.MULTILINE)

_SKIP_FILES = {
    "__init__.py", "urls.py", "admin.py", "apps.py", "conftest.py", "setup.py",
    "manage.py", "wsgi.py", "asgi.py", "tests.py",
}

_ROLE_LABEL = {
    "data-model": "data model",
    "api": "API / views",
    "services": "service layer",
    "background-jobs": "background jobs",
    "management-commands": "management commands",
    "core": "core logic",
}


def _imports_of(text: str) -> set[str]:
    return {m.split(".", 1)[0] for m in _IMPORT_RE.findall(text) if m and not m.startswith(".")}


def _role_of(rel_path: str) -> str | None:
    p = rel_path.replace("\\", "/").lower()
    name = os.path.basename(p)
    if name in _SKIP_FILES or name.startswith("test_") or "/tests/" in f"/{p}":
        return None
    if "management/commands/" in p:
        return "management-commands"
    if name == "models.py" or "/models/" in f"/{p}":
        return "data-model"
    if name in ("views.py", "api.py", "viewsets.py") or name.endswith("_views.py") \
            or "/views/" in f"/{p}" or name == "serializers.py":
        return "api"
    if "/services/" in f"/{p}" or name.startswith("service") or name.endswith("_service.py"):
        return "services"
    if name == "tasks.py" or "/tasks/" in f"/{p}" or "worker" in name or "celery" in name:
        return "background-jobs"
    return "core"


class PythonExtractor:
    name = "python"
    extensions = (".py",)
    product_markers = ("apps.py", "models.py", "pyproject.toml", "setup.py", "requirements.txt")

    def extract_product(self, ctx: ProductContext):
        return bucket_and_draft(ctx, role_of=_role_of, role_labels=_ROLE_LABEL,
                                imports_of=_imports_of, id_prefix="")

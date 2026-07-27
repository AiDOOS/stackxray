"""C / C++ extractor (Milestone 7c) - #include based, coarse roles.

C/C++ has no standard package/role convention, so extraction is deliberately coarse:
headers (interfaces) vs implementation, sized by LOC, with library includes surfaced.
The LLM universal track (llm.py) refines this when a key is present."""

from __future__ import annotations

import os
import re

from ..base import ProductContext, bucket_and_draft

_INCLUDE_RE = re.compile(r'#\s*include\s*[<"]([^>"]+)[>"]')

_ROLE_LABEL = {
    "headers": "headers / interfaces",
    "impl": "implementation",
}


def _imports_of(text: str) -> set[str]:
    return set(_INCLUDE_RE.findall(text))  # e.g. 'aws/core.h', 'stdio.h'


def _role_of(rel_path: str) -> str | None:
    name = os.path.basename(rel_path).lower()
    if "test" in name or "mock" in name:
        return None
    if name.endswith((".h", ".hpp", ".hh", ".hxx")):
        return "headers"
    return "impl"


class CppExtractor:
    name = "cpp"
    extensions = (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx")
    product_markers = ("CMakeLists.txt", "Makefile", "configure", "conanfile.txt", "meson.build")

    def extract_product(self, ctx: ProductContext):
        return bucket_and_draft(ctx, role_of=_role_of, role_labels=_ROLE_LABEL,
                                imports_of=_imports_of, id_prefix="cpp", lang_tag="C/C++")

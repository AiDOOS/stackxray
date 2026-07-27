"""Low-level, network-free, language-agnostic repo scanning primitives (Milestone 7).

Deliberately dumb and deterministic: walk files by extension, count lines. Language-
specific parsing (imports, roles) lives in each langs/*.py module, not here.
"""

from __future__ import annotations

import os
import re

# Decision / rule / loop constructs - a language-agnostic proxy for "repetitive, rules-driven
# toil" (the kind of work agents do well). Universal across Java/.NET/C/C++/Go/JS/COBOL/RPG.
_TOIL_RE = re.compile(
    r"\b(if|elif|elsif|else|switch|case|when|for|while|foreach|match|select|"
    r"evaluate|perform|dow|dou|iterate)\b", re.IGNORECASE)

# Directories that are never capabilities - dependencies, build output, VCS, data blobs,
# schema-history archives, and test code. `migrations` and `static` were always here; the rest
# are their peers under other frameworks (Frappe calls migrations `patches`), plus test and
# translation trees. Counting these as business capabilities is how a scan ends up proposing an
# AI agent for a folder of database patches.
IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__",
    ".pytest_cache", ".mypy_cache", "dist", "build", ".next", ".turbo", "coverage",
    "static", "staticfiles", "media", "logs", "json_data", "keys", "migrations",
    "target", "bin", "obj", "vendor", "Pods",  # java/.net/go/ios build+dep dirs
    "patches",                                  # frappe's migrations
    "tests", "test", "spec", "specs", "__tests__", "testdata",   # test code, not capability
    "locale", "locales", "i18n", "translations", "gettext",      # translation catalogs
    "fixtures", "docs", "doc",
}


def iter_files(root: str, extensions: tuple[str, ...],
               exclude_top: frozenset[str] = frozenset()):
    """Yield (abs_path, path_relative_to_root) for files with the given extensions,
    ignoring dependency/build/data dirs (IGNORE_DIRS).

    `exclude_top` skips immediate child directories of `root` only. It is how a wrapper
    package (e.g. `erpnext/`) is scanned for its OWN code once its sub-packages have been
    promoted to products of their own - without counting their files twice.
    """
    exts = tuple(e.lower() for e in extensions)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS
                       and not (dirpath == root and d in exclude_top)]
        for fname in filenames:
            if fname.lower().endswith(exts):
                abs_path = os.path.join(dirpath, fname)
                yield abs_path, os.path.relpath(abs_path, root)


def read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def count_loc(text: str) -> int:
    """Non-blank source lines. Coarse size signal; the LLM refines complexity later."""
    return sum(1 for line in text.splitlines() if line.strip())


def count_toil(text: str) -> int:
    """Count decision/rule/loop constructs - a code-content signal of agent-friendly toil,
    independent of how the module is named or which language it's in."""
    return len(_TOIL_RE.findall(text))


def size_bucket(loc: int) -> str:
    if loc < 150:
        return "small"
    if loc < 800:
        return "medium"
    return "large"

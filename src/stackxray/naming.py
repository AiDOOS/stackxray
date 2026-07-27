"""Display naming - turn a code identifier into something a board can read.

The engine lowercases everything (`extract/units.humanize`) so that matching works: a stem has
to compare cleanly whether the folder said `PurchaseOrder`, `purchase_order` or `PURCHASE_ORDER`.
That is right for matching and wrong for READING - it leaves a CEO looking at `hr: leave` and
`accounts: pos invoice`.

So the lowercase form stays the identity, and this is applied at the last moment, for display
only. Two rules:

  1. Title-case each word.
  2. EXCEPT known acronyms, which go upper: `pos invoice` -> `POS Invoice`, `hr` -> `HR`.

WHY THE ACRONYM LIST IS CONSERVATIVE. Uppercasing on a guess is worse than not uppercasing at
all: `it` is an acronym AND an ordinary English word, so a naive list turns "leave it" into
"Leave IT". Every entry below is a term that is essentially never a normal word in a business
system. When in doubt, leave it out - Title Case is always safe, a wrong acronym is not.
"""

from __future__ import annotations

import re

# Business/technical acronyms that are not ordinary English words. Deliberately excludes
# it / is / at / in / on / to / of / or / as / by / do / go / no / us / we / an / am.
ACRONYMS = {
    # org / function
    "hr", "hrms", "crm", "erp", "mrp", "wms", "tms", "scm", "ats", "lms", "cms", "pim",
    # finance / accounting
    "gl", "ar", "ap", "po", "so", "vat", "gst", "tds", "emi", "cogs", "fifo", "lifo",
    "pos", "rfq", "grn", "wip", "bom", "uom", "sku", "iban", "swift", "ach", "sepa",
    "cif", "fob", "coa", "pnl", "ebitda", "kpi", "roi", "sla", "sop", "eta",
    # quality / ops
    "qc", "qa", "oee", "mtbf", "mttr", "rma",
    # tech
    "api", "ui", "ux", "sql", "http", "https", "rest", "soap", "edi", "xml", "json",
    "csv", "pdf", "url", "uri", "sso", "otp", "mfa", "rbac", "acl", "ocr", "etl",
    "llm", "ai", "ml", "nlp", "sms", "smtp", "imap", "ftp", "sftp", "cdn", "dns",
    "seo", "kyc", "aml", "pii", "gdpr", "hipaa", "b2b", "b2c", "saas", "vpc", "iam",
}

# Words that stay lowercase inside a title (unless first).
_MINOR = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or",
          "the", "to", "vs", "with"}

_SPLIT = re.compile(r"(\s+|[/\-_])")


def pretty(text: str | None) -> str:
    """`pos invoice` -> `POS Invoice`; `hr` -> `HR`; `service level agreement` -> `Service
    Level Agreement`. Idempotent-ish and never destructive: a token that already has internal
    capitals (a product name like `ERPNext`) is left exactly as its author wrote it."""
    if not text:
        return ""
    out, first = [], True
    for tok in _SPLIT.split(text):
        if not tok or _SPLIT.fullmatch(tok):
            out.append(tok)
            continue
        low = tok.lower()
        if low in ACRONYMS:
            out.append(low.upper())
        elif tok != low and tok != tok.upper():
            out.append(tok)                      # author already cased it (ERPNext, iPhone)
        elif not first and low in _MINOR:
            out.append(low)
        else:
            out.append(low[:1].upper() + low[1:])
        first = False
    return "".join(out)


def pretty_capability(name: str | None) -> str:
    """`accounts: pos invoice (Apex)` -> `Accounts: POS Invoice (Apex)`.

    The trailing language/kind tag is the tool's own word, not the customer's - it is left
    exactly as written so `(JS/TS)` does not become `(Js/Ts)`.
    """
    if not name:
        return ""
    tag = ""
    m = re.search(r"\s+\([^)]+\)$", name)
    if m:
        tag, name = m.group(0), name[: m.start()]
    if ": " in name:
        product, rest = name.split(": ", 1)
        return f"{pretty(product)}: {pretty(rest)}{tag}"
    return f"{pretty(name)}{tag}"

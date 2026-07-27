"""Domain units - naming a capability after the BUSINESS THING, not the layer it lives in.

This is the difference between a report that says

    accounts: service layer          172,083 LOC   "repetitive, rules-driven work"   <- useless
    banking: pages / routes          KEEP, nothing to do                              <- WRONG

and one that says

    accounts: payment reconciliation      HIGH
    buying: purchase order                HIGH
    support: issue                        HIGH
    banking: bank reconciliation          HIGH

Both reports are describing the same code. The first one decomposed ERPNext by LAYER, so every
capability came out named `core logic` / `service layer` / `pages / routes` / `hooks`. Those are
architectural strata. They are not things a business does. And because the agentify scorer looks
for domain words (reconcil, invoice, approv, triage, quote, claim) in the capability's NAME, a
layer name can never contain one - so the scorer never fires on the merits and falls back to
"big and non-AI, therefore agentify", which is how you end up telling a CEO to rebuild 172,000
lines of ERP core as an agent in one to two months.

The signal was in the filesystem the whole time. ERPNext literally names its business
capabilities on disk:

    erpnext/accounts/doctype/payment_reconciliation/payment_reconciliation.py
    erpnext/buying/doctype/purchase_order/purchase_order.py
    erpnext/support/doctype/issue/issue.py
    banking/src/pages/BankReconciliation.tsx

We just never looked. This module looks.

THE RULE
    Walk a file's path inside its product and take the first segment that is not STRUCTURAL.
    `doctype/`, `src/`, `components/`, `features/`, `pages/`, `services/`, `views/` are places
    a framework makes you put code; they say nothing about what the code DOES. The first name
    that is not one of those is the business unit. If every directory is structural, fall back
    to the file's own stem - which is exactly what rescues `pages/BankReconciliation.tsx`.

    Files whose whole path is structural (`utils.py`, `views.py`, `hooks/use-mobile.ts`) have no
    domain unit, and keep the old layer bucketing. That is honest: they really are plumbing.

Framework-agnostic by construction: Frappe's doctype/, React's features/, Django's services/,
Rails' models/ all fall out of the same test, because the test is "is this name structural",
not "which framework is this".
"""

from __future__ import annotations

import os
import re

# Directory and file names that describe WHERE code sits, not WHAT it does. A capability named
# after one of these tells the reader nothing. Kept deliberately broad: a false "structural"
# call costs us a layer bucket (the old behaviour), while a false "domain" call puts a word like
# `utils` on the CEO's page as if it were a business capability.
STRUCTURAL = {
    # framework containers
    "doctype", "doctypes", "report", "reports", "page", "pages", "dashboard", "dashboards",
    "print_format", "print_format_field_template", "web_form", "workspace", "workspaces",
    "custom", "notification", "onboarding_step", "module_onboarding", "dashboard_chart",
    "dashboard_chart_source", "chart", "charts", "widget", "widgets",
    # source roots / packaging
    "src", "lib", "libs", "app", "apps", "pkg", "internal", "main", "source", "sources",
    "modules", "packages", "projects", "code",
    # Salesforce DX layout: `force-app/main/default/classes/PropertyController.cls`. None of
    # these say anything about the business - without them, "default" became the capability
    # name and a real Salesforce app scanned as "force-app: default". The domain lives in the
    # object name (`objects/Property__c`) and the class/flow name, one level further down.
    "force-app", "default", "classes", "triggers", "lwc", "aura", "staticresources",
    "objects", "flows", "permissionsets", "profiles", "tabs", "applications",
    "flexipages", "layouts", "quickactions", "contenttypes", "labels", "messagechannels",
    # ServiceNow scoped-app layout
    "records", "update", "sys_app", "update_set",
    # layers
    "components", "component", "features", "feature", "containers", "screens", "views", "view",
    "controllers", "controller", "handlers", "handler", "routes", "router", "routing",
    "services", "service", "api", "apis", "endpoints", "resources", "models", "model",
    "entities", "entity", "domain", "domains", "schemas", "schema", "serializers", "forms",
    "repositories", "repository", "dao", "dto", "mappers", "adapters", "providers", "provider",
    "middleware", "interceptors", "filters", "guards", "decorators", "mixins",
    "hooks", "store", "stores", "state", "redux", "context", "contexts", "layouts", "layout",
    "ui", "styles", "css", "assets", "img", "images", "icons", "fonts",
    "tasks", "jobs", "workers", "queues", "commands", "management", "cli", "bin", "scripts",
    "utils", "util", "utilities", "helpers", "helper", "common", "core", "shared", "base",
    "constants", "config", "conf", "settings", "types", "typings", "interfaces", "enums",
    "exceptions", "errors", "validators", "validation",
    # non-capability trees
    "tests", "test", "spec", "specs", "fixtures", "mocks", "stubs", "docs", "doc",
    "migrations", "patches", "locale", "locales", "i18n", "translations", "static", "public",
    "www", "templates", "template", "build", "dist", "vendor", "node_modules",
    # language/dir noise
    "js", "ts", "jsx", "tsx", "py", "java", "go", "cs", "cpp",
    "index", "init", "__init__", "main", "app",
}

# A unit must hold at least this much code to be worth naming on its own. Below it, the file
# stays in its layer bucket. Without this, ERPNext's ~1000 doctypes - most of them small CRUD
# masters - would each become a "capability" and bury the twenty that matter.
MIN_UNIT_LOC = 120

# Trees that are NOT business capabilities, however they are named inside. Frappe's
# `report/gross_profit/` is a query report; `print_format/`, `dashboard/` are presentation.
# These differ from STRUCTURAL above: a structural directory is skipped and we keep looking
# for the business name BELOW it (doctype/payment_reconciliation -> a capability), whereas
# anything under one of these has NO business unit at all and falls back to its layer bucket.
# Without this, ERPNext proposed AI agents for "stock ageing" and "gross profit" - reports.
NOT_A_CAPABILITY = {
    "report", "reports", "print_format", "print_format_field_template",
    "dashboard", "dashboards", "dashboard_chart", "dashboard_chart_source",
    # A React hook is plumbing, not a business capability. Descending into hooks/ named
    # `use-mobile.ts` a capability called "use mobile".
    "hooks", "hook",
    "tests", "test", "spec", "specs", "__tests__", "fixtures", "mocks",
    "migrations", "patches", "locale", "locales", "i18n", "translations", "docs", "doc",
    "static", "public", "www", "templates", "node_modules", "vendor", "build", "dist",
}

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_VERSIONED = re.compile(r"^(v\d+([._-]\d+)*|\d+([._-]\d+)*)$", re.IGNORECASE)

# Reversed-domain package roots (Java/Kotlin/Scala convention). In `org/apache/ofbiz/
# manufacturing/mrp/MrpServices.java` the FIRST non-structural segment is `org` - which named
# every OFBiz capability "org" on a real scan, so no ticket could ever match one. Inside such a
# package tree the convention INVERTS: the business name is at the package LEAF (`mrp`), the
# roots are boilerplate. So on hitting one of these we walk from the END instead.
_PACKAGE_TLDS = {"org", "com", "net", "io", "edu", "gov"}


def _is_structural(name: str) -> bool:
    n = name.lower()
    return (not n) or n in STRUCTURAL or bool(_VERSIONED.match(n))


def humanize(name: str) -> str:
    """`payment_reconciliation` / `BankReconciliation` -> `payment reconciliation`."""
    words = [w for w in _SPLIT.split(_CAMEL.sub(" ", name)) if w]
    return " ".join(words).lower()


def unit_key(rel_path: str) -> str | None:
    """The business unit a file belongs to, or None if its whole path is structural.

    `accounts/doctype/payment_reconciliation/payment_reconciliation.py` -> payment reconciliation
    `banking/src/pages/BankReconciliation.tsx`                          -> bank reconciliation
    `accounts/utils.py`                                                 -> None (plumbing)
    """
    p = rel_path.replace("\\", "/")
    parts = [s for s in p.split("/") if s]
    if not parts:
        return None
    dirs, filename = parts[:-1], parts[-1]

    if any(d.lower() in NOT_A_CAPABILITY for d in dirs):
        return None                      # a report / print format / test tree: not a capability

    for i, d in enumerate(dirs):
        if not _is_structural(d):
            if d.lower() in _PACKAGE_TLDS:
                # A reversed-domain package tree: the name is at the LEAF, not the root. Skip
                # the tld + vendor segment, then take the deepest non-structural directory.
                for leaf in reversed(dirs[i + 2:]):
                    if not _is_structural(leaf):
                        return humanize(leaf)
                break                        # org/vendor/File.java - fall through to the stem
            return humanize(d)

    # Every directory was structural. The file's own name is the last place a business word can
    # hide - and it is where `pages/BankReconciliation.tsx` keeps it.
    stem = os.path.splitext(filename)[0]
    for suffix in (".test", ".spec", ".stories", ".d"):
        if stem.endswith(suffix):
            return None
    if _is_structural(stem):
        return None
    return humanize(stem)

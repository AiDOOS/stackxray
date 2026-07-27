"""Salesforce Apex extractor - the server-side business logic of a Salesforce org.

Why this exists: a real scan of a Salesforce app (trailheadapps/dreamhouse-lwc) returned
**2 capabilities and 0 opportunities** while silently ignoring 9 Apex classes of actual
business logic - because `.cls` was in no extractor AND in no gap list. The report said
"0 opportunities", which reads as "nothing to automate" when the truth was "we could not
read your stack". That is the one failure mode this product cannot have.

Apex is Java-shaped (`public with sharing class PropertyController { ... }`), so the parsing
is the Java pattern. What differs is Salesforce's conventions:

  * `.trigger` files are event handlers on an object - always work, never a data model.
  * There are no imports. Apex resolves classes globally, so the SaaS/AI dependency signal
    that `imports_of` normally provides is simply absent - we return an empty set rather
    than pretend. Dependencies for a Salesforce org live in metadata (named credentials,
    remote site settings), not in the code.
  * `@AuraEnabled` / `@RestResource` / `@HttpGet` mark the API surface the UI calls.
  * `@isTest` classes and `*Test` / `Test*` names are tests, not capabilities.

WHAT THIS STILL DOES NOT SEE (and `salesforce.py` handles): processes assembled by clicking
in Flow Designer. Those are metadata records, not code. Apex is only half a Salesforce org.
"""

from __future__ import annotations

import os

from ..base import ProductContext, bucket_and_draft

_ROLE_LABEL = {
    "api": "API / remote actions",
    "trigger": "triggers / event handlers",
    "services": "service layer",
    "data-model": "data model",
    "core": "core logic",
}

def _imports_of(text: str) -> set[str]:
    """Apex has no imports - classes resolve globally. Returning an empty set is the honest
    answer; inventing dependency names from `new Foo()` would manufacture a SaaS signal that
    is not there."""
    return set()


def _role_of(rel_path: str) -> str | None:
    p = rel_path.replace("\\", "/").lower()
    name = os.path.basename(p)
    stem = os.path.splitext(name)[0]

    # Tests are not capabilities. Salesforce convention puts Test on either end.
    if stem.startswith("test") or stem.endswith(("test", "tests")):
        return None
    if name.endswith(".trigger"):
        return "trigger"
    if stem.endswith(("controller", "resource", "invocable")):
        return "api"
    if stem.endswith(("service", "handler", "manager", "helper", "processor")):
        return "services"
    # A wrapper/DTO with no behaviour (PagedResult, XxxWrapper) is a data holder.
    if stem.endswith(("wrapper", "dto", "result", "selector")):
        return "data-model"
    return "core"


class ApexExtractor:
    name = "apex"
    extensions = (".cls", ".trigger")
    # `sfdx-project.json` marks a Salesforce DX project; `force-app` is the default source dir.
    product_markers = ("sfdx-project.json",)

    def extract_product(self, ctx: ProductContext):
        # Deliberately no post-hoc re-labelling of buckets. An earlier version rewrote a
        # "data model" draft to "API / remote actions" when its file carried @AuraEnabled -
        # which produced TWO capabilities with the same name (the bucket it was renamed into
        # already existed). Role belongs in role_of, decided once, per file.
        return bucket_and_draft(ctx, role_of=_role_of, role_labels=_ROLE_LABEL,
                                imports_of=_imports_of, id_prefix="apex", lang_tag="Apex")

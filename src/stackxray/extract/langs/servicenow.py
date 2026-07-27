"""ServiceNow extractor - the business logic a company builds ON the ServiceNow platform.

Joseph's question in the JMB call was ServiceNow *and* Salesforce: *"that's the main business
process engine of folks using."* We built Salesforce; this is the other half. In a big
enterprise ServiceNow is where HR service delivery, procurement, approvals, incident and change
management are actually BUILT - as records in the platform, exported to XML two ways:

  1. SCOPED-APP SOURCE (git-tracked):   records/sys_script_include_<sys_id>.xml
     each file is one record:           <record_update table="sys_script_include"> ...
  2. UPDATE SET (a customer hands you):  one file, <unload> wrapping <sys_update_xml> entries.

Either way the RECORD'S TABLE is its meaning, and that taxonomy is stable:

    sys_script            business rule      - server logic on a table, CONTAINS JavaScript
    sys_script_include    script include     - reusable server logic, JavaScript
    sysauto_script        scheduled job      - batch logic, JavaScript
    sys_ws_operation      scripted REST API  - an endpoint, JavaScript
    wf_workflow           workflow           - a CONFIGURED process (approvals, tasks)
    sys_hub_flow          Flow Designer flow - a configured process (the modern workflow)
    sys_ui_action/page/script  UI            - not business logic
    sys_security_acl, sys_scope_privilege    - access control, config not logic
    sys_dictionary, sys_db_object            - the data model

So we read the JavaScript out of the script records (the same `count_toil` we run on any code,
applied to the `<script>` CDATA), and we surface workflows as configured processes - exactly
like a Salesforce Flow, including whether a human approves in them.

WHAT WE DO NOT CLAIM. This detector is validated against a real scoped app for FORMAT and
RECORD CLASSIFICATION; the app happened to carry no business rules, so the JavaScript-toil path
is covered by tests, not by that one real sample. And a table we do not recognise is surfaced,
never silently dropped - same firewall as everywhere else.
"""

from __future__ import annotations

import os
import re

from ..base import CapabilityDraft, ProductContext
from ...models import AIClass, Evidence, Kind
from .. import _scan

# Cheap signature check on the file head - is this a ServiceNow XML at all? Keeps us from
# reading every .xml in a big repo in full.
_SN_SIGNATURE = re.compile(r"<(record_update\s+table=|unload\b|sys_update_xml\b)", re.IGNORECASE)

# table -> (role, is_code). is_code means it carries real JavaScript we should read.
_TABLE = {
    "sys_script": ("business rules", True),
    "sys_script_include": ("script includes", True),
    "sysauto_script": ("scheduled jobs", True),
    "sys_ws_operation": ("scripted REST API", True),
    "sys_processor": ("processors", True),
    "sys_transform_script": ("import transforms", True),
    "sys_script_client": ("client scripts", True),
    "wf_workflow": ("workflows", False),
    "sys_hub_flow": ("flows", False),
    "sys_ui_action": ("UI actions", False),
    "sys_ui_page": ("UI pages", False),
    "sys_ui_script": ("UI scripts", False),
    "sys_dictionary": ("data model", False),
    "sys_db_object": ("data model", False),
    "sys_security_acl": ("access control", False),
    "sys_scope_privilege": ("access control", False),
    "sys_security_acl_role": ("access control", False),
    "sys_app": ("application", False),
    "sys_app_module": ("navigation", False),
}
# Which roles are business WORK (an agent target) vs config/UI/data.
_WORK_ROLES = {"business rules", "script includes", "scheduled jobs", "scripted REST API",
               "processors", "import transforms", "workflows", "flows"}

_TABLE_RE = re.compile(r'<record_update\s+table="([a-z_]+)"', re.IGNORECASE)
_UNLOAD_TABLE_RE = re.compile(r'<(sys_[a-z_]+)\s+action=', re.IGNORECASE)
_SCRIPT_RE = re.compile(r"<script>(.*?)</script>", re.IGNORECASE | re.DOTALL)
_NAME_RE = re.compile(r"<name>([^<]+)</name>", re.IGNORECASE)
_APPROVAL_RE = re.compile(r"approv", re.IGNORECASE)


def _humanize(name: str) -> str:
    """`PurchaseOrderValidator` / `purchase_order_validator` -> `purchase order validator`.
    Lowercased like every other unit key so matching is case-insensitive; naming.pretty()
    title-cases it at display time."""
    spaced = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name)
    return ' '.join(w for w in re.split(r'[^A-Za-z0-9]+', spaced) if w).lower()


def _tables_in(text: str) -> list[str]:
    """Every record table named in the file - scoped-record form and update-set form."""
    tables = _TABLE_RE.findall(text)
    if not tables:                                   # update-set: <sys_XXX action="...">
        tables = [t for t in _UNLOAD_TABLE_RE.findall(text)
                  if t not in ("sys_remote_update_set", "sys_update_xml")]
    return tables


class ServiceNowExtractor:
    """Reads ServiceNow record XML. Claims `.xml` but activates only on ServiceNow content, so
    it never touches a Java pom.xml or a Salesforce `-meta.xml` (which has no <record_update)."""

    name = "servicenow"
    extensions = (".xml",)
    product_markers = ()          # ServiceNow files carry sys_id hashes; no stable marker name

    def extract_product(self, ctx: ProductContext) -> list[CapabilityDraft]:
        drafts: list[CapabilityDraft] = []
        # Config / UI / data records aggregate by role (17 ACLs are one "access control" line,
        # not 17 capabilities). WORK records do NOT: each script include / workflow is its own
        # business capability, named by its <name> - aggregating them into "script includes"
        # would repeat the "core logic" mistake and hide `PurchaseOrderValidator` from the scorer.
        agg: dict[str, dict] = {}

        for abs_path, rel in ctx.files:
            head = _scan.read_text(abs_path)[:600]
            if not _SN_SIGNATURE.search(head):
                continue                              # not ServiceNow - leave it to others
            text = _scan.read_text(abs_path)
            rec_name = (_NAME_RE.search(text).group(1).strip() if _NAME_RE.search(text) else "")
            approval = bool(_APPROVAL_RE.search(text))
            for table in _tables_in(text):
                role, is_code = _TABLE.get(table.lower(), ("other ServiceNow records", False))
                is_work = role in _WORK_ROLES
                toil = loc = 0
                if is_code:
                    for script in _SCRIPT_RE.findall(text):
                        toil += _scan.count_toil(script)
                        loc += _scan.count_loc(script)

                if is_work and rec_name:
                    # one capability per record, named for what it does
                    unit = _humanize(rec_name)
                    human = role in ("workflows", "flows") and approval
                    kind_word = "workflow" if role in ("workflows", "flows") else "server script"
                    detail = (f"ServiceNow {kind_word}: {rec_name}"
                              + (f", ~{loc} LOC of JavaScript" if is_code else "")
                              + (" - includes an approval step" if human else ""))
                    drafts.append(CapabilityDraft(
                        suffix=f"{unit} (ServiceNow)", id_hint=f"sn:{table}:{rec_name}",
                        kind=Kind.BUILT, ai=AIClass.NON_AI,
                        size_complexity=_scan.size_bucket(loc) if is_code else "medium",
                        toil=toil, domain_unit=unit, role="services", paths=[rel],
                        human_in_loop=human,      # an approval step = the twin seam
                        evidence=[Evidence("extract", detail, locator=rel)]))
                else:
                    b = agg.setdefault(role, {"n": 0, "files": [], "code": is_code})
                    b["n"] += 1
                    if len(b["files"]) < 8:
                        b["files"].append(rel)

        for role, b in agg.items():
            drafts.append(CapabilityDraft(
                suffix=f"{role} (ServiceNow)", id_hint=f"sn:{role.replace(' ', '-')}",
                kind=Kind.BUILT, ai=AIClass.NON_AI, size_complexity="small",
                role="data-model" if role == "data model" else "core", paths=b["files"],
                evidence=[Evidence("extract", f"{b['n']} ServiceNow {role} record(s)",
                                   locator=b["files"][0] if b["files"] else None)]))
        return drafts

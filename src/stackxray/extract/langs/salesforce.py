"""Salesforce METADATA extractor - the processes people assembled by clicking, not coding.

This is the half of a Salesforce org that a code scanner structurally cannot see, and it is
exactly what Joseph asked about: *"most of my processes are in ServiceNow... Salesforce - does
it look at that and do the same thing?"* In a modern org a large share of the business process
is not Apex at all. It is a **Flow**: a record in the platform, exported as XML.

    force-app/main/default/flows/Create_property.flow-meta.xml

That file IS a business process - it has steps, decisions, record updates, and often an
approval. It has no code, so every extractor we had walked straight past it.

WHAT WE READ, AND HOW HONESTLY
    A Flow's XML names its own semantics, so we do not have to guess:
      <decisions>       a branch - a rule being applied      -> decision density (toil)
      <recordUpdates>   / <recordCreates> / <recordDeletes>  -> it changes business records
      <screens>         it stops and asks a PERSON           -> a human decision point
      <subflows>        it calls another process
      <processType>     AutoLaunchedFlow | Flow (screen) | Workflow
    We count what the XML declares. We do not interpret intent.

    Custom OBJECTS (`objects/Property__c/`) are the domain nouns of the org - they are what
    makes `Property`, `Broker`, `Case` legible as business capabilities rather than
    `force-app: default`.

WHAT WE STILL DO NOT CLAIM
    Reading a Flow's XML tells us the SHAPE of the process (how many decisions, whether a
    human is in it, what it writes). It does not tell us the business value, and it does not
    tell us the org's runtime behaviour. Same firewall as everywhere else.
"""

from __future__ import annotations

import os
import re

from ..base import CapabilityDraft, ProductContext
from ...models import AIClass, Evidence, Kind
from .. import _scan

# Metadata suffixes Salesforce uses. Only these XML files are business metadata; a repo's
# other XML (pom.xml, config) must never be dragged in.
_FLOW = ".flow-meta.xml"
_OBJECT_DIRS = ("/objects/",)

# What a Flow declares about itself. These are Salesforce's own element names.
_DECISION_RE = re.compile(r"<decisions>", re.IGNORECASE)
_RULE_RE = re.compile(r"<rules>", re.IGNORECASE)
_SCREEN_RE = re.compile(r"<screens>", re.IGNORECASE)          # stops and asks a person
_WRITE_RE = re.compile(r"<record(Updates|Creates|Deletes)>", re.IGNORECASE)
_SUBFLOW_RE = re.compile(r"<subflows>", re.IGNORECASE)
_APPROVAL_RE = re.compile(r"approval", re.IGNORECASE)
_TYPE_RE = re.compile(r"<processType>([^<]+)</processType>", re.IGNORECASE)
# NOTE: deliberately NOT reading <label>. A Flow's XML is full of them - every screen, decision
# and rule has one - and the first is an inner STEP, not the flow. Grabbing it renamed
# `Create_property.flow-meta.xml` to "geocode address" (its first step). The FILE NAME is the
# flow's API name, which is what an admin actually calls it, and it cannot drift.


def humanize(stem: str) -> str:
    return " ".join(w for w in re.split(r"[^A-Za-z0-9]+", stem) if w).strip().lower()


def _flow_stats(text: str) -> dict:
    """Count what the Flow's own XML declares. No inference."""
    return {
        "decisions": len(_DECISION_RE.findall(text)) + len(_RULE_RE.findall(text)),
        "screens": len(_SCREEN_RE.findall(text)),
        "writes": len(_WRITE_RE.findall(text)),
        "subflows": len(_SUBFLOW_RE.findall(text)),
        "approval": bool(_APPROVAL_RE.search(text)),
        "type": (_TYPE_RE.search(text).group(1) if _TYPE_RE.search(text) else "Flow"),
    }


class SalesforceMetadataExtractor:
    """Not a language - a metadata reader. Emits one capability per Flow and per custom object.

    Registered like a language extractor so it rides the same orchestration, but it takes
    `.xml` and filters hard to Salesforce's own suffixes, so a Java repo's pom.xml is never
    touched.
    """

    name = "salesforce-metadata"
    # `-meta.xml`, NOT `.xml`. iter_files matches on suffix, so this claims ONLY Salesforce's
    # own metadata. Claiming all `.xml` would mark every XML in every repo as "handled" - and
    # the coverage guard skips handled types, so a ServiceNow update set (also XML, also
    # business logic, also unreadable by us) would be silently dropped. That is the very bug
    # this module was written to fix; do not widen this.
    extensions = ("-meta.xml",)
    product_markers = ("sfdx-project.json",)

    def extract_product(self, ctx: ProductContext) -> list[CapabilityDraft]:
        drafts: list[CapabilityDraft] = []
        objects: dict[str, list[str]] = {}

        for abs_path, rel in ctx.files:
            p = rel.replace("\\", "/")
            low = p.lower()

            # --- a FLOW: a configured business process --------------------------------
            if low.endswith(_FLOW):
                text = _scan.read_text(abs_path)
                if not text:
                    continue
                st = _flow_stats(text)
                stem = os.path.basename(p)[: -len(_FLOW)]
                name = humanize(stem)
                # A flow with a screen stops for a person; that is a human decision point and
                # the report must be able to say so (it is what a twin would scale).
                human = st["screens"] > 0 or st["approval"]
                bits = [f"{st['decisions']} decision point(s)"]
                if st["writes"]:
                    bits.append(f"{st['writes']} record write(s)")
                if st["subflows"]:
                    bits.append(f"{st['subflows']} subflow(s)")
                if human:
                    bits.append(f"stops for a person {st['screens']}x"
                                if st["screens"] else "needs an approval")
                drafts.append(CapabilityDraft(
                    suffix=f"{name} (Flow)",
                    id_hint=f"flow:{stem}",
                    kind=Kind.BUILT, ai=AIClass.NON_AI,
                    size_complexity=_scan.size_bucket(st["decisions"] * 40 + st["writes"] * 20),
                    # A flow's decisions ARE its rule density - the same signal count_toil
                    # derives from code branches, read from the XML instead.
                    toil=st["decisions"] * 6 + st["writes"] * 2,
                    domain_unit=humanize(name),
                    role="services",          # a flow is work, not a data model or a screen
                    human_in_loop=human,      # a screen/approval = the twin seam
                    paths=[p],
                    evidence=[Evidence("extract",
                                       f"Salesforce {st['type']} - " + ", ".join(bits),
                                       locator=p)],
                ))
                continue

            # --- a custom OBJECT: the domain noun of the org ---------------------------
            if any(seg in low for seg in _OBJECT_DIRS) and low.endswith("-meta.xml"):
                parts = [s for s in p.split("/") if s]
                try:
                    obj = parts[parts.index("objects") + 1]
                except (ValueError, IndexError):
                    continue
                if obj.endswith(".object-meta.xml"):
                    obj = obj[: -len(".object-meta.xml")]
                objects.setdefault(obj, []).append(p)

        for obj, files in sorted(objects.items()):
            if not obj.endswith("__c"):
                continue                      # standard objects are Salesforce's, not theirs
            drafts.append(CapabilityDraft(
                suffix=f"{humanize(obj[:-3])} (object)",
                id_hint=f"sobject:{obj}",
                kind=Kind.BUILT, ai=AIClass.NON_AI,
                size_complexity="small",
                toil=0,                       # a schema decides nothing - never an agent
                domain_unit=humanize(obj[:-3]),
                role="data-model",
                paths=files[:12],
                evidence=[Evidence("extract",
                                   f"custom object with {len(files)} metadata file(s)",
                                   locator=files[0])],
            ))
        return drafts

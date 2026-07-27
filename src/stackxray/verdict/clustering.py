"""Portfolio-level analysis for the verdict engine (SPEC §8).

Some verdicts can't be decided from one capability alone - they need cross-capability
context: CONSOLIDATE (a redundancy cluster) and BUY_REPLACE (a commodity the org builds
itself). This pass computes those tags once over the whole map; `verdict/__init__.py`
then applies them per capability with the right precedence.

Everything here is structural (no runtime), so tags are MEDIUM/LOW and phrased as
candidates, never guarantees (SPEC §4.4).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..consumption.catalog import category_of as _bought_category
from ..extract.saas import VENDOR_CATEGORY
from ..models import AIClass, Capability, Confidence, Kind, Level, Verdict

# Built capabilities whose name hints at a commodity function -> the SaaS category that
# could replace them. If the org has NO integration in that category, it's a buy/replace
# candidate (they maintain something they could rent).
_COMMODITY_TERMS: dict[str, str] = {
    "pdf": "documents", "search": "search", "email": "comms", "sms": "comms",
    "notification": "comms", "auth": "identity", "login": "identity",
    "billing": "payments", "invoice": "payments", "analytics": "analytics",
}


@dataclass
class PortfolioTag:
    """A cross-capability verdict suggestion for one capability."""
    verdict: Verdict
    confidence: Confidence
    reason: str
    cluster_id: str | None = None


def _vendor_of(cap: Capability) -> str:
    """'billing: Stripe integration' / 'Bought SaaS: Tableau' -> vendor name."""
    return cap.name.split(": ", 1)[-1].replace(" integration", "").strip()


def _category_of_vendor(vendor: str) -> str | None:
    """Category from either catalog: integrated-SaaS (extract.saas) or bought (consumption)."""
    return VENDOR_CATEGORY.get(vendor) or _bought_category(vendor)


def _commodity_category(name: str) -> str | None:
    n = name.lower()
    for term, category in _COMMODITY_TERMS.items():
        if term in n:
            return category
    return None


def analyze_portfolio(caps: list[Capability]) -> dict[str, PortfolioTag]:
    """Return cap_id -> PortfolioTag for CONSOLIDATE / BUY_REPLACE candidates."""
    tags: dict[str, PortfolioTag] = {}

    # --- 1. CONSOLIDATE: >=2 distinct vendors in one category (SPEC §5b/§8) -----------
    cat_caps: dict[str, list[Capability]] = defaultdict(list)
    cat_vendors: dict[str, set[str]] = defaultdict(set)
    for c in caps:
        if c.kind in (Kind.INTEGRATED_SAAS, Kind.BOUGHT_SAAS):
            vendor = _vendor_of(c)
            category = _category_of_vendor(vendor)
            if category:
                cat_caps[category].append(c)
                cat_vendors[category].add(vendor)
    categories_integrated = set(cat_vendors)  # used by the buy/replace pass below
    for category, vendors in cat_vendors.items():
        if len(vendors) >= 2:
            reason = (f"{len(vendors)} {category} integrations "
                      f"({', '.join(sorted(vendors))}) - candidates to consolidate to one")
            for c in cat_caps[category]:
                tags[c.id] = PortfolioTag(Verdict.CONSOLIDATE, Confidence.MEDIUM, reason,
                                          cluster_id=f"cluster:{category}")

    # --- 2. CONSOLIDATE (cross-cloud): same capability on >1 cloud (SPEC §8) ----------
    # Group by the product-stripped capability name; fires only once join/ supplies
    # cloud tags (won't trigger in v1 without cloud data - present and honest).
    bycloud: dict[str, list[Capability]] = defaultdict(list)
    for c in caps:
        if c.level == Level.CAPABILITY and c.cloud_environment:
            bycloud[c.name.split(": ", 1)[-1]].append(c)
    for key, group in bycloud.items():
        clouds = {c.cloud_environment for c in group}
        if len(clouds) >= 2:
            reason = (f"same capability runs on {len(clouds)} clouds "
                      f"({', '.join(sorted(clouds))}) - cross-cloud consolidation candidate")
            for c in group:
                tags[c.id] = PortfolioTag(Verdict.CONSOLIDATE, Confidence.MEDIUM, reason,
                                          cluster_id=f"cluster:xcloud:{key}")

    # --- 3. BUY_REPLACE: a built commodity the org has no SaaS for (SPEC §8) ----------
    for c in caps:
        if c.id in tags or c.kind != Kind.BUILT or c.level != Level.CAPABILITY:
            continue
        category = _commodity_category(c.name)
        if category and category not in categories_integrated:
            tags[c.id] = PortfolioTag(
                Verdict.BUY_REPLACE, Confidence.LOW,
                f"built '{category}' capability with no SaaS in place - commodity; "
                f"candidate to buy/replace rather than maintain",
            )
    return tags


def is_agentify_candidate(cap: Capability) -> bool:
    """Load-bearing, non-AI, non-trivial service/core/job logic - the natural target to
    rebuild as an AI agent (SPEC §8). A per-capability judgment, kept LOW-confidence
    because true value/feasibility needs human/LLM review."""
    used = cap.usage is not None and (cap.usage.requests or 0) > 0
    sizable = cap.size_complexity in ("medium", "large")
    toil_role = any(r in cap.name for r in ("service layer", "core logic", "background jobs"))
    return used and sizable and toil_role and cap.ai_or_not == AIClass.NON_AI

"""Bought-SaaS consumption lens (SPEC §5b, pulled into v1) - the estate's invisible third.

Standalone SaaS with NO code footprint is invisible to code scanning. This lens ingests
the CONSUMPTION signals (SSO / spend / egress) that reveal it, and emits bought-SaaS
capabilities onto the same map - so the verdict engine can flag **shelfware** (paid for,
nobody uses) and category redundancy (3 BI tools), exactly like built/integrated ones.

All file-import based (customer exports); no live connectors in v1. Merged by vendor,
sequenced by signal quality: SSO (authoritative) > spend > egress.
"""

from __future__ import annotations

from ..config import ConsumptionConfig
from ..models import AIClass, Capability, Confidence, Evidence, Kind, Level, ServiceUsage
from .catalog import category_of
from .sources import parse_egress, parse_spend, parse_sso

BOUGHT_PRODUCT_ID = "prod:__bought_saas__"


def _merge(cfg: ConsumptionConfig) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for part in (
        parse_sso(cfg.sso_path) if cfg.sso_path else {},
        parse_spend(cfg.spend_path) if cfg.spend_path else {},
        parse_egress(cfg.egress_path) if cfg.egress_path else {},
    ):
        for vendor, fields in part.items():
            merged.setdefault(vendor, {}).update({k: v for k, v in fields.items() if v is not None})
    return merged


def _usage_and_confidence(rec: dict) -> tuple[ServiceUsage | None, Confidence]:
    """Turn consumption signals into a usage proxy + evidence confidence.

    SSO active-user count is the trustworthy usage proxy (window ~1yr) -> HIGH.
    Egress requests are a weaker proxy -> LOW. Spend alone gives cost but no usage ->
    can't judge use (MEDIUM presence, but usage None so no forced verdict)."""
    if "sso_active" in rec:
        return ServiceUsage("bought", requests=rec["sso_active"], window_days=365,
                            last_used=rec.get("last_login"), source="sso"), Confidence.HIGH
    if "egress_requests" in rec:
        return ServiceUsage("bought", requests=rec["egress_requests"], window_days=90,
                            source="egress"), Confidence.LOW
    # spend-only: known to be paid for, but no usage signal -> MEDIUM presence, usage None
    return None, Confidence.MEDIUM


def _evidence(vendor: str, rec: dict) -> list[Evidence]:
    bits = []
    if rec.get("annual_cost") is not None:
        bits.append(f"${rec['annual_cost']:,}/yr")
    if "sso_active" in rec:
        bits.append(f"{rec.get('sso_active', 0)} of {rec.get('sso_assigned', '?')} users active")
    if "egress_requests" in rec:
        bits.append(f"{rec['egress_requests']:,} egress requests/90d")
    src = [s for s, k in (("SSO", "sso_active"), ("spend", "annual_cost"),
                          ("egress", "egress_requests")) if k in rec]
    return [Evidence("consumption", f"{vendor}: {', '.join(bits) or 'seen'} "
                     f"(sources: {', '.join(src)})")]


def build_bought_saas(cfg: ConsumptionConfig) -> list[Capability]:
    """Return a bought-SaaS product node + one capability per vendor (verdict-ready).

    Empty if no consumption sources are configured. Capabilities carry usage + confidence
    so the existing verdict engine fires shelfware RETIRE / KEEP; clustering handles
    category consolidation.
    """
    merged = _merge(cfg)
    if not merged:
        return []

    caps: list[Capability] = [Capability(
        id=BOUGHT_PRODUCT_ID, name="Bought SaaS (no code footprint)",
        level=Level.PRODUCT, parent_id="portfolio:root", kind=Kind.BOUGHT_SAAS,
    )]
    for vendor in sorted(merged):
        rec = merged[vendor]
        usage, conf = _usage_and_confidence(rec)
        cost = rec.get("annual_cost")
        caps.append(Capability(
            id=f"cap:bought:{vendor}",
            name=f"Bought SaaS: {vendor}",
            level=Level.CAPABILITY,
            parent_id=BOUGHT_PRODUCT_ID,
            kind=Kind.BOUGHT_SAAS,
            ai_or_not=AIClass.NON_AI,
            size_complexity="small",
            usage=usage,
            last_used=usage.last_used if usage else None,
            join_confidence=conf,
            est_effort_to_act=(f"${cost:,}/yr at stake" if cost else None),
            evidence=_evidence(vendor, rec),
        ))
    return caps


def category_for_cluster(vendor: str) -> str | None:
    return category_of(vendor)

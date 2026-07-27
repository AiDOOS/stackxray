"""Consumption-lens source parsers (SPEC §5b) - SSO, spend, egress. File imports only.

Each returns {normalized_vendor: {signal fields}}. The lens (consumption/__init__.py)
merges them by vendor. SSO is highest-signal (every login flows through it); spend catches
card-bought SaaS that bypasses SSO; egress catches shadow SaaS with neither.
"""

from __future__ import annotations

import csv

from .catalog import normalize_vendor, vendor_from_domain


def _int(v) -> int | None:
    v = (str(v) if v is not None else "").strip().replace(",", "").replace("$", "")
    try:
        return int(float(v)) if v else None
    except ValueError:
        return None


def parse_sso(path: str) -> dict[str, dict]:
    """Okta/Azure-AD app-assignment export.
    Columns: app,users_assigned,active_users,last_login[,category]."""
    out: dict[str, dict] = {}
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            app = (row.get("app") or row.get("application") or "").strip()
            if not app:
                continue
            out[normalize_vendor(app)] = {
                "sso_assigned": _int(row.get("users_assigned")),
                "sso_active": _int(row.get("active_users")),
                "last_login": (row.get("last_login") or "").strip() or None,
                "category": (row.get("category") or "").strip() or None,
            }
    return out


def parse_spend(path: str) -> dict[str, dict]:
    """Expense/procurement export. Columns: vendor,annual_cost,renewal_date[,category]."""
    out: dict[str, dict] = {}
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            vendor = (row.get("vendor") or row.get("supplier") or "").strip()
            if not vendor:
                continue
            out[normalize_vendor(vendor)] = {
                "annual_cost": _int(row.get("annual_cost") or row.get("amount")),
                "renewal": (row.get("renewal_date") or "").strip() or None,
                "category": (row.get("category") or "").strip() or None,
            }
    return out


def parse_egress(path: str) -> dict[str, dict]:
    """DNS/egress summary. Columns: domain,requests[,bytes]. Only rows that map to a known
    SaaS domain are attributed (unknown domains are ignored, not guessed)."""
    out: dict[str, dict] = {}
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            vendor = vendor_from_domain(row.get("domain") or "")
            if not vendor:
                continue
            reqs = _int(row.get("requests")) or 0
            prev = out.get(vendor, {}).get("egress_requests", 0)
            out[vendor] = {"egress_requests": prev + reqs}
    return out

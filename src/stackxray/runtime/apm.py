"""Vendor APM ingestion (SPEC §12 - pulled into v1) -> ServiceUsage.

Datadog / CloudWatch / New Relic / Dynatrace, all as EXPORTED query-result JSON the
customer hands us (the same offline, compliance-friendly model as Prometheus/OTel - no
secrets, no live connector to configure). Each parser normalizes one vendor's metric-
query shape into service -> ServiceUsage; load_usage() merges them with the rest.

The customer runs one request-count query per service in their tool and exports the
result; we never hold their APM credentials.
"""

from __future__ import annotations

import json

from ..models import ServiceUsage


def _sum(values) -> int | None:
    nums = [v for v in (values or []) if v is not None]
    if not nums:
        return None
    try:
        return int(sum(float(v) for v in nums))
    except (ValueError, TypeError):
        return None


def _svc(name: str, requests: int | None, source: str, window: int) -> ServiceUsage:
    return ServiceUsage(service_name=name, requests=requests, window_days=window, source=source)


def parse_datadog(obj: dict, window_days: int = 30) -> dict[str, ServiceUsage]:
    """Datadog /api/v1/query response: series[].scope 'service:NAME', series[].pointlist."""
    out: dict[str, ServiceUsage] = {}
    for series in (obj or {}).get("series", []):
        scope = series.get("scope") or ""
        name = None
        for tag in scope.split(","):
            if tag.strip().startswith("service:"):
                name = tag.strip().split(":", 1)[1]
        if not name:
            continue
        points = [p[1] for p in series.get("pointlist", []) if isinstance(p, (list, tuple)) and len(p) > 1]
        out[name] = _svc(name, _sum(points), "datadog", window_days)
    return out


def parse_cloudwatch(obj: dict, window_days: int = 30) -> dict[str, ServiceUsage]:
    """CloudWatch get-metric-data output: MetricDataResults[].Label + .Values."""
    out: dict[str, ServiceUsage] = {}
    for r in (obj or {}).get("MetricDataResults", []):
        name = r.get("Label")
        if name:
            out[name] = _svc(name, _sum(r.get("Values")), "cloudwatch", window_days)
    return out


def parse_newrelic(obj: dict, window_days: int = 30) -> dict[str, ServiceUsage]:
    """New Relic NRQL faceted result: results[] with 'facet' + 'count' (or 'value')."""
    out: dict[str, ServiceUsage] = {}
    for row in (obj or {}).get("results", []) or (obj or {}).get("facets", []):
        facet = row.get("facet") or row.get("name")
        name = facet[0] if isinstance(facet, list) and facet else facet
        if not name:
            continue
        count = row.get("count", row.get("value"))
        if count is None and isinstance(row.get("results"), list) and row["results"]:
            count = row["results"][0].get("count")
        out[str(name)] = _svc(str(name), _sum([count]) if count is not None else None,
                              "newrelic", window_days)
    return out


def parse_dynatrace(obj: dict, window_days: int = 30) -> dict[str, ServiceUsage]:
    """Dynatrace metrics v2: result[].data[] with 'dimensions' + 'values'."""
    out: dict[str, ServiceUsage] = {}
    for metric in (obj or {}).get("result", []):
        for d in metric.get("data", []):
            dims = d.get("dimensions") or []
            name = dims[0] if dims else None
            if name:
                out[str(name)] = _svc(str(name), _sum(d.get("values")), "dynatrace", window_days)
    return out


_PARSERS = {
    "datadog": parse_datadog, "cloudwatch": parse_cloudwatch,
    "newrelic": parse_newrelic, "dynatrace": parse_dynatrace,
}


def load_apm_file(vendor: str, path: str, window_days: int = 30) -> dict[str, ServiceUsage]:
    with open(path, "r", encoding="utf-8") as fh:
        return _PARSERS[vendor](json.load(fh), window_days)

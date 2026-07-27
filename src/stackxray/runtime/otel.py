"""OpenTelemetry ingestion (SPEC §6, §14.3 - IN v1) -> ServiceUsage.

Reads an OTel metrics JSON export (the OTLP/JSON shape). We look for a request-count
metric per service, keyed by the standard `service.name` resource attribute. Kept lenient:
different exporters nest slightly differently, so we walk resourceMetrics defensively.
"""

from __future__ import annotations

import json

from ..models import ServiceUsage

_COUNT_METRICS = ("http.server.request.count", "http.server.requests", "requests",
                  "http_requests_total", "rpc.server.duration")


def _service_of(resource: dict) -> str | None:
    for attr in resource.get("attributes", []):
        if attr.get("key") == "service.name":
            val = attr.get("value") or {}
            return val.get("stringValue") or val.get("value")
    return None


def _sum_points(metric: dict) -> int | None:
    data = metric.get("sum") or metric.get("gauge") or {}
    total = 0
    seen = False
    for pt in data.get("dataPoints", []):
        v = pt.get("asInt", pt.get("asDouble"))
        if v is not None:
            total += int(float(v))
            seen = True
    return total if seen else None


def parse_otel_metrics(obj: dict, window_days: int = 30) -> dict[str, ServiceUsage]:
    usage: dict[str, ServiceUsage] = {}
    for rm in (obj or {}).get("resourceMetrics", []):
        name = _service_of(rm.get("resource") or {})
        if not name:
            continue
        count = None
        for sm in rm.get("scopeMetrics", []):
            for metric in sm.get("metrics", []):
                if metric.get("name") in _COUNT_METRICS:
                    count = _sum_points(metric)
                    break
        usage[name] = ServiceUsage(service_name=name, requests=count,
                                   window_days=window_days, source="otel")
    return usage


def load_otel_file(path: str, window_days: int = 30) -> dict[str, ServiceUsage]:
    with open(path, "r", encoding="utf-8") as fh:
        return parse_otel_metrics(json.load(fh), window_days)

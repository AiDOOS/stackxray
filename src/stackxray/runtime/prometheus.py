"""Prometheus ingestion (SPEC §6, §14.3 - IN v1) -> ServiceUsage.

Two modes, same parser:
  - a saved query-result JSON the customer exports (offline, compliance-friendly), or
  - a live query to the customer's own Prometheus (via _prom_http; their endpoint, never
    AiDOOS).

We read the standard Prometheus HTTP-API result shape:
  {"data": {"result": [{"metric": {"service": "pay-retry", ...}, "value": [ts, "50000"]}]}}
The service label defaults to `service` but common alternates are tried.
"""

from __future__ import annotations

import json

from ..models import ServiceUsage

_SERVICE_LABELS = ("service", "job", "app", "kubernetes_name", "container", "deployment")


def _service_name(metric: dict) -> str | None:
    for label in _SERVICE_LABELS:
        if metric.get(label):
            return metric[label]
    return None


def parse_prometheus_result(obj: dict, window_days: int) -> dict[str, ServiceUsage]:
    """Parse a Prometheus range/instant query result into service -> ServiceUsage."""
    usage: dict[str, ServiceUsage] = {}
    results = ((obj or {}).get("data") or {}).get("result") or []
    for series in results:
        metric = series.get("metric") or {}
        name = _service_name(metric)
        if not name:
            continue
        # instant vector: "value":[ts,"n"]; range vector: "values":[[ts,"n"],...] -> last
        raw = series.get("value")
        if raw is None and series.get("values"):
            raw = series["values"][-1]
        try:
            requests = int(float(raw[1])) if raw else None
        except (ValueError, TypeError, IndexError):
            requests = None
        usage[name] = ServiceUsage(service_name=name, requests=requests,
                                   window_days=window_days, source="prometheus")
    return usage


def load_prometheus_file(path: str, window_days: int = 30) -> dict[str, ServiceUsage]:
    with open(path, "r", encoding="utf-8") as fh:
        return parse_prometheus_result(json.load(fh), window_days)


def query_prometheus(url: str, query: str, window_days: int = 30) -> dict[str, ServiceUsage]:
    """Live query against the customer's Prometheus (their endpoint). Returns {} on error
    so a telemetry hiccup never aborts the scan."""
    from . import _prom_http
    try:
        return parse_prometheus_result(_prom_http.query(url, query), window_days)
    except Exception:
        return {}

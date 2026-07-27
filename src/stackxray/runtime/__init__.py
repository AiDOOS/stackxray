"""Runtime / observability ingestion (SPEC §6) - deployed service -> ServiceUsage.

v1 sources (all merge; a service seen by ANY source is 'observed'):
  - generic usage CSV (service,requests,window_days,last_used[,source])
  - Prometheus (saved result file or live query) - prometheus.py
  - OpenTelemetry metrics export (JSON) - otel.py
  - VM host/process inventory CSV (host,process,cpu,last_active[,port]) - for bare VMs (§6)
Vendor APM (Datadog/New Relic/CloudWatch/Dynatrace) is v2.
"""

from __future__ import annotations

import csv

from ..config import ObservabilityConfig
from ..models import ServiceUsage
from . import apm, otel, prometheus


def _int_or_none(value) -> int | None:
    value = (str(value) if value is not None else "").strip()
    return int(value) if value else None


def load_usage_csv(path: str) -> dict[str, ServiceUsage]:
    """Parse a generic usage CSV. A service ABSENT is absent (never fabricated as 0);
    an explicit requests=0 is a real observed zero (the evidence a Retire needs)."""
    usage: dict[str, ServiceUsage] = {}
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            service = (row.get("service") or "").strip()
            if not service:
                continue
            usage[service] = ServiceUsage(
                service_name=service,
                requests=_int_or_none(row.get("requests")),
                window_days=_int_or_none(row.get("window_days")),
                last_used=(row.get("last_used") or "").strip() or None,
                source=(row.get("source") or "csv-import").strip(),
            )
    return usage


def load_host_inventory(path: str) -> dict[str, ServiceUsage]:
    """Parse a VM host/process inventory CSV -> per-process ServiceUsage (SPEC §6).

    Columns: process,last_active[,requests][,window_days][,host][,cpu]. On bare VMs the
    'service' is a process/unit name; usage is proxied by activity. Absent 'requests' but
    present 'cpu'>0 means 'alive' (requests stays None -> won't force a Retire).
    """
    usage: dict[str, ServiceUsage] = {}
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            proc = (row.get("process") or row.get("service") or "").strip()
            if not proc:
                continue
            reqs = _int_or_none(row.get("requests"))
            # if no request count but cpu==0 and it's in the inventory, treat as observed-idle
            if reqs is None and _int_or_none(row.get("cpu")) == 0:
                reqs = 0
            usage[proc] = ServiceUsage(
                service_name=proc, requests=reqs,
                window_days=_int_or_none(row.get("window_days")),
                last_used=(row.get("last_active") or "").strip() or None,
                source="host-inventory",
            )
    return usage


def load_usage(obs: ObservabilityConfig) -> dict[str, ServiceUsage]:
    """Merge every configured runtime source into one service -> ServiceUsage map.

    Later sources fill gaps but never overwrite a service already seen with a request
    count (first concrete signal wins). Missing sources are simply skipped - an absent
    service stays absent so the join can tell 'observed 0' from 'no observability'.
    """
    merged: dict[str, ServiceUsage] = {}

    def add(part: dict[str, ServiceUsage]):
        for name, u in part.items():
            existing = merged.get(name)
            if existing is None or (existing.requests is None and u.requests is not None):
                merged[name] = u

    if obs.usage_import_path:
        add(load_usage_csv(obs.usage_import_path))
    if obs.prometheus_result_path:
        add(prometheus.load_prometheus_file(obs.prometheus_result_path))
    if obs.prometheus_url:
        add(prometheus.query_prometheus(obs.prometheus_url, obs.prometheus_query))
    if obs.otel_metrics_path:
        add(otel.load_otel_file(obs.otel_metrics_path))
    for vendor, path in (("datadog", obs.datadog_path), ("cloudwatch", obs.cloudwatch_path),
                         ("newrelic", obs.newrelic_path), ("dynatrace", obs.dynatrace_path)):
        if path:
            add(apm.load_apm_file(vendor, path))
    if obs.host_inventory_path:
        add(load_host_inventory(obs.host_inventory_path))
    return merged

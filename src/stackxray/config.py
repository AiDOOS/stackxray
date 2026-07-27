"""Run configuration for a single scan (SPEC §6, §14).

Everything the container needs to run locally: where the repo is, which observability
source to read, and the customer's own LLM API key (SPEC §14.1 - no bundled model).
No secrets are ever written to the report or the fingerprint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    """Customer's own model endpoint (SPEC §14.1). Their key, their endpoint, so no
    code leaves the environment during extraction."""
    api_key_env: str = "STACKXRAY_LLM_API_KEY"   # read from env, never persisted
    base_url: Optional[str] = None             # customer endpoint if self-hosted
    model: Optional[str] = None


@dataclass
class ObservabilityConfig:
    """Where runtime usage comes from (SPEC §6). Generic import + OTel/Prometheus are IN
    v1; vendor APM is v2. All sources merge; a service seen by any source is 'observed'.

    Prometheus/OTel are supported as (a) an exported result FILE the customer hands us
    (fully offline, compliance-friendly) or (b) a live query URL (calls the CUSTOMER's own
    endpoint in their env, never AiDOOS)."""
    usage_import_path: Optional[str] = None       # generic CSV: service,requests,window,last
    prometheus_result_path: Optional[str] = None  # saved Prometheus query JSON
    prometheus_url: Optional[str] = None          # live Prometheus (customer endpoint)
    prometheus_query: str = "sum by (service) (increase(http_requests_total[30d]))"
    otel_metrics_path: Optional[str] = None       # OTel metrics JSON export
    host_inventory_path: Optional[str] = None     # VM host/process inventory CSV (§6)
    otel_endpoint: Optional[str] = None           # reserved
    # vendor APM query-result exports (customer runs the query, hands us the JSON)
    datadog_path: Optional[str] = None
    cloudwatch_path: Optional[str] = None
    newrelic_path: Optional[str] = None
    dynatrace_path: Optional[str] = None


@dataclass
class MonolithConfig:
    """Monolith mode (Milestone 11) - for apps deployed as ONE unit (Django/Rails/etc.),
    where runtime evidence is per-ROUTE traffic, not per-service. The route->module map is
    derived from the code (e.g. Django URLconf); the customer supplies an access-log
    summary. 'Retire' here = a module whose routes get no traffic = dead feature."""
    access_log_path: Optional[str] = None   # pre-aggregated CSV: path,requests[,last_seen]
    nginx_log_path: Optional[str] = None     # raw nginx logs (file or dir; reads .gz history)
    window_days: int = 90


@dataclass
class ConsumptionConfig:
    """Bought-SaaS consumption lens (SPEC §5b, pulled into v1). File imports the customer
    exports - no live connectors in v1. Every source is optional; more sources = sharper
    picture. SSO is the highest-signal ('every SaaS login flows through it')."""
    sso_path: Optional[str] = None       # Okta/Azure AD app-assignment export (CSV)
    spend_path: Optional[str] = None     # expense/procurement export (CSV)
    egress_path: Optional[str] = None    # DNS/egress log summary (CSV)


@dataclass
class ScanConfig:
    repo_path: str                             # local path to the checked-out repo
    deploy_config_globs: list[str] = field(default_factory=lambda: [
        "**/Dockerfile", "**/*.dockerfile",
        "**/k8s/**/*.yaml", "**/k8s/**/*.yml",
        "**/*.tf",
        "**/systemd/*.service", "**/ansible/**/*.yml",
    ])
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    consumption: ConsumptionConfig = field(default_factory=ConsumptionConfig)
    monolith: MonolithConfig = field(default_factory=MonolithConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    report_port: int = 7373                    # localhost only (SPEC §11)

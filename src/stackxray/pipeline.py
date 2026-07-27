"""The local pipeline (SPEC §6) - wires the tiers together, all inside the customer env.

extract -> deploy-parse -> runtime-ingest -> JOIN (§7) -> verdict -> report. Nothing
here touches the network; the only egress path is the consent-gated cloud call triggered
from the served report. This function is the backbone the CLI calls.

v1 status: orchestration skeleton; each step raises until its module is built.
"""

from __future__ import annotations

from . import consumption, deploy, extract, join, monolith, runtime, verdict
from .config import ScanConfig
from .models import CapabilityMap


def run_scan(config: ScanConfig, provider=None, budget=None) -> CapabilityMap:
    """Run the full local scan and return an enriched, verdicted CapabilityMap.

    Order matches SPEC §16: the join sits at the center and everything feeds/consumes it.
    Bought-SaaS (consumption lens) is added AFTER the join - those capabilities have no
    code/deploy footprint, so they carry their own usage/confidence and must not pass
    through the code<->runtime join (which would clobber them).

    `provider` (optional) drives the LLM universal track so unparsed languages are read, not
    just flagged; it is the same provider the agentify pass uses.
    """
    cmap: CapabilityMap = extract.extract_capabilities(config, provider=provider, budget=budget)
    deploy_links = deploy.parse_deploy_links(config)                    # §7 bridge
    service_usage = runtime.load_usage(config.observability)            # §6
    cmap.capabilities = join.join(cmap.capabilities, deploy_links, service_usage)  # §7 crux
    if config.monolith.access_log_path or config.monolith.nginx_log_path:  # monolith route-join
        cmap.capabilities = monolith.enrich(cmap.capabilities, config)
    cmap.capabilities += consumption.build_bought_saas(config.consumption)  # §5b bought-SaaS
    cmap.capabilities = verdict.assign_verdicts(cmap.capabilities)      # §8
    return cmap

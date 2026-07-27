"""THE CRUX (SPEC §7) - the code<->runtime join.

Connects a capability found in the CODE to the RUNNING service observed in production,
so usage evidence can back a verdict. Without this, "safe to retire" is a guess; with
it, every verdict carries proof. This is the load-bearing wall: everything upstream
feeds it, everything downstream consumes it.

v1 status: IMPLEMENTED for the HIGH-confidence path (Dockerfile+k8s). Honesty rules
(§7 'Reality') enforced: missing link, ambiguous link (one code unit -> many services),
and usage-absent all lower confidence and record why.
"""

from __future__ import annotations

from ..models import (
    Capability,
    Confidence,
    DeployLink,
    DeployedService,
    Evidence,
    JoinResult,
    Runtime,
    ServiceUsage,
    min_confidence,
)


def join_one(
    capability: Capability,
    deploy_links: list[DeployLink],
    service_usage: dict[str, ServiceUsage],
) -> JoinResult:
    """Join a single capability to its runtime reality (SPEC §7).

    Confidence = weakest link of (deploy-link confidence, usage completeness). Any of
    {no link, ambiguous link, usage absent} caps confidence and is stated in `notes`.
    """
    matches = [dl for dl in deploy_links if dl.code_unit == capability.name]

    # --- no bridge: code exists, we cannot see it running -----------------------------
    if not matches:
        return JoinResult(
            confidence=Confidence.LOW,
            notes="no deploy config maps this code unit to a running service",
            evidence=[Evidence("join", f"no deploy link for '{capability.name}'")],
        )

    # --- ambiguous bridge: one code unit -> many services -----------------------------
    if len(matches) > 1:
        services = ", ".join(sorted(dl.service_name for dl in matches))
        return JoinResult(
            confidence=Confidence.LOW,
            notes=f"ambiguous: code unit maps to multiple services ({services})",
            evidence=[e for dl in matches for e in dl.evidence]
            + [Evidence("join", "confidence lowered: shared/ambiguous deployment")],
        )

    link = matches[0]
    service = DeployedService(service_name=link.service_name, runtime=link.runtime,
                              cloud_environment=link.cloud_environment)
    usage = service_usage.get(link.service_name)
    evidence = list(link.evidence)

    # --- link found but no observability for the service ------------------------------
    if usage is None:
        return JoinResult(
            deployed_service=service,
            usage=None,
            confidence=Confidence.LOW,
            notes=f"service '{link.service_name}' has no usage data; cannot judge if it is used",
            evidence=evidence
            + [Evidence("join", f"no observability for service '{link.service_name}'")],
        )

    # --- clean join: link + observed usage -------------------------------------------
    # usage completeness: a known observation window makes the usage trustworthy.
    usage_conf = Confidence.HIGH if usage.window_days else Confidence.MEDIUM
    confidence = min_confidence(link.confidence, usage_conf)
    evidence.append(Evidence(
        source="join",
        detail=(
            f"service '{link.service_name}': {usage.requests} requests"
            f" over {usage.window_days}d (source: {usage.source})"
        ),
        locator=link.service_name,
    ))
    return JoinResult(
        deployed_service=service,
        usage=usage,
        confidence=confidence,
        evidence=evidence,
    )


def _apply(capability: Capability, result: JoinResult) -> Capability:
    """Write a JoinResult back onto the capability's runtime block (SPEC §10)."""
    if result.deployed_service:
        capability.deployed_service = result.deployed_service.service_name
        capability.runtime = result.deployed_service.runtime
        capability.cloud_environment = result.deployed_service.cloud_environment
    if result.usage:
        capability.usage = result.usage
        capability.last_used = result.usage.last_used
    capability.join_confidence = result.confidence
    capability.evidence.extend(result.evidence)
    return capability


def join(
    capabilities: list[Capability],
    deploy_links: list[DeployLink],
    service_usage: dict[str, ServiceUsage],
) -> list[Capability]:
    """Attach runtime reality to each capability and return them enriched (SPEC §7)."""
    return [_apply(cap, join_one(cap, deploy_links, service_usage)) for cap in capabilities]

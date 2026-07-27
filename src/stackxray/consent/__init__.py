"""Trust boundary (SPEC §6 boundary, §4.4, §14.4) - the ONLY thing that ever leaves.

Produces the abstract capability fingerprint: a de-identified structural summary
(categories, sizes, patterns, redundancy clusters). NEVER source, data, or secrets.
This is the one sentence a compliance officer approves.

Network egress itself lives in cloud/; this module only builds the payload and guarantees
it is safe to send. Keeping construction (here) and transport (cloud/) separate is what
makes the boundary auditable.

v1 status: IMPLEMENTED. build_fingerprint emits aggregates only; a test asserts no
customer free-text (names, purposes, locators, dependency identifiers) survives.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field

from ..models import CapabilityMap, Level


@dataclass
class RedundancyShape:
    """One redundancy cluster reduced to a generic category + member count. The category
    (e.g. 'payments', 'ai-llm') is a functional label, not a vendor/product name."""
    category: str
    size: int


@dataclass
class CapabilityFingerprint:
    """Abstract, de-identified summary of a CapabilityMap (SPEC §4 'fingerprint').

    Contains ONLY structural aggregates - counts by kind/verdict/level/AI, coarse size
    buckets, redundancy-cluster shapes, and a one-way-hashed scan token. By construction
    it holds no names that could identify source, no data, no secrets.
    """
    scan_token: str                                              # sha256(scan_id)[:12]
    portfolio_shape: dict[str, int] = field(default_factory=dict)  # products, capabilities
    counts_by_kind: dict[str, int] = field(default_factory=dict)
    counts_by_verdict: dict[str, int] = field(default_factory=dict)
    counts_by_ai: dict[str, int] = field(default_factory=dict)
    size_histogram: dict[str, int] = field(default_factory=dict)
    redundancy_shapes: list[RedundancyShape] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def build_fingerprint(cmap: CapabilityMap) -> CapabilityFingerprint:
    """De-identify a CapabilityMap into a CapabilityFingerprint.

    Drops (never copies): capability/product names, inferred_purpose, dependency
    identifiers, deployed_service/cloud/host identifiers, evidence + locators, raw
    scan_id. Keeps only counts, buckets, and generic redundancy categories.
    """
    caps = cmap.by_level(Level.CAPABILITY)

    clusters: Counter[str] = Counter()
    for c in caps:
        if c.redundancy_cluster:
            # "cluster:payments" / "cluster:xcloud:foo" -> generic category label only
            category = c.redundancy_cluster.split(":")[1] if ":" in c.redundancy_cluster else "other"
            clusters[category] += 1

    scan_token = hashlib.sha256((cmap.scan_id or "").encode("utf-8")).hexdigest()[:12]

    return CapabilityFingerprint(
        scan_token=scan_token,
        portfolio_shape={
            "products": len(cmap.by_level(Level.PRODUCT)),
            "capabilities": len(caps),
        },
        counts_by_kind=dict(Counter(c.kind.value for c in caps)),
        counts_by_verdict=dict(Counter(c.verdict.value for c in caps)),
        counts_by_ai=dict(Counter(c.ai_or_not.value for c in caps)),
        size_histogram=dict(Counter((c.size_complexity or "unknown") for c in caps)),
        redundancy_shapes=[RedundancyShape(cat, n) for cat, n in sorted(clusters.items())],
    )

"""Capability X-Ray - core data model.

This is the concrete realization of SPEC.md §10 (the capability record) and, per that
section, is *also* the AiDOOS calibration-ledger schema seen from the customer side -
the two are kept reconciled as one schema. Keep changes here in lockstep with the
ledger.

These dataclasses are deliberately dependency-free (stdlib only) so the model can be
imported by any tier without pulling in scanners, servers, or network clients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# --------------------------------------------------------------------------------------
# Enumerations (the vocabulary the whole tool shares)
# --------------------------------------------------------------------------------------

class Level(str, Enum):
    """The three recursive levels of the map (SPEC §5)."""
    PORTFOLIO = "portfolio"     # across all products/apps
    PRODUCT = "product"         # within one product
    CAPABILITY = "capability"   # atomic module/service/feature


class Kind(str, Enum):
    """Coverage model (SPEC §5b). What kind of thing this capability is."""
    BUILT = "built"                       # code in the repo - full code-scan coverage
    INTEGRATED_SAAS = "integrated-SaaS"   # SaaS with glue code in repo (Stripe, Twilio)
    BOUGHT_SAAS = "bought-SaaS"           # standalone SaaS, no code footprint - v2 lens


class Runtime(str, Enum):
    """Where the capability runs (SPEC §5b). VMs are in scope and often hide the wins."""
    CONTAINER = "container"   # k8s / containers
    VM = "vm"                 # bare VM: systemd / cron / monolith
    UNKNOWN = "unknown"       # no runtime evidence yet


class Verdict(str, Enum):
    """Verdict tiers (SPEC §8). Every capability gets exactly one, plus confidence."""
    KEEP = "keep-as-is"
    RETIRE = "retire"            # high confidence REQUIRES runtime evidence (§7/§8)
    CONSOLIDATE = "consolidate"  # incl. cross-cloud redundancy
    AGENTIFY = "agentify"        # may be partial
    BUY_REPLACE = "buy-replace"
    UNDECIDED = "undecided"      # not enough evidence to call it - a valid, honest state


class Confidence(str, Enum):
    """Confidence carried by every verdict and by the join (SPEC §4.4, §7 'Reality').

    Ordinal: LOW < MEDIUM < HIGH. HIGH on a RETIRE verdict is gated on runtime
    evidence - enforced in verdict/, informed by JoinResult.confidence.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AIClass(str, Enum):
    """Whether the capability itself is AI-based (SPEC §10 `ai_or_not`)."""
    AI = "ai"
    NON_AI = "non-ai"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------------------
# Evidence - every claim the tool makes must be able to point at where it came from
# --------------------------------------------------------------------------------------

@dataclass
class Evidence:
    """A single piece of backing for a verdict or a join (SPEC §4.4, §8).

    `source` names the tier that produced it (extract|deploy|runtime|join|verdict);
    `detail` is a short human string; `locator` points at the artifact (file:line,
    service name, metric query) so a skeptical CIO can verify it.
    """
    source: str
    detail: str
    locator: Optional[str] = None


# --------------------------------------------------------------------------------------
# Runtime & join records - the §7 crux produces these and stitches them onto Capability
# --------------------------------------------------------------------------------------

@dataclass
class DeployedService:
    """A running service as named by deploy configs + observability (SPEC §7).

    The join's job is to connect a code `Capability` to one (or more) of these.
    """
    service_name: str                       # e.g. "pay-retry", "pdfgen-v1"
    runtime: Runtime = Runtime.UNKNOWN
    cloud_environment: Optional[str] = None  # e.g. "gcp", "digitalocean", "vm:host-42"
    image: Optional[str] = None              # container image ref, if any


@dataclass
class ServiceUsage:
    """Observed usage for a deployed service (SPEC §6 observability, §7).

    Sourced from OTel/Prometheus or the generic CSV/JSON import
    (`service -> requests -> last_called`). Absence of data is itself signal, but
    NOT proof of "dead" unless the observability window is known to be complete.
    """
    service_name: str
    requests: Optional[int] = None           # over the observation window
    window_days: Optional[int] = None        # length of that window
    last_used: Optional[str] = None          # ISO date; None = never seen in window
    source: Optional[str] = None             # "otel" | "prometheus" | "csv-import"


@dataclass
class DeployLink:
    """A `code unit -> deployed service` mapping extracted from deploy configs (SPEC §7).

    Produced by deploy/. This is the bridge the join walks. `confidence` reflects how
    cleanly the config tied code to service (a Dockerfile+k8s image match is HIGH;
    a name-similarity fallback is LOW).
    """
    code_unit: str                           # identifier of the code module/service
    service_name: str                        # the deployed service it maps to
    confidence: Confidence = Confidence.LOW
    runtime: Runtime = Runtime.CONTAINER     # container (k8s/compose/TF) vs vm (systemd/ansible)
    cloud_environment: Optional[str] = None  # inferred: aws|gcp|azure|... (enables cross-cloud §8)
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class JoinResult:
    """Output of the §7 join for one capability - the load-bearing record.

    Carries the deployed service, its usage, and - critically - the *join confidence*
    which downstream verdict logic must respect. Where the join is weak, confidence is
    LOW and `notes` says why; the tool never forces a verdict on a bad join (§7 Reality).
    """
    deployed_service: Optional[DeployedService] = None
    usage: Optional[ServiceUsage] = None
    confidence: Confidence = Confidence.LOW
    evidence: list[Evidence] = field(default_factory=list)
    notes: Optional[str] = None


# --------------------------------------------------------------------------------------
# The capability record - SPEC §10, the schema everything rolls up to
# --------------------------------------------------------------------------------------

@dataclass
class Capability:
    """One atomic unit of function + everything the tool learns about it (SPEC §10).

    Fields map 1:1 to the §10 record. Extraction fills the top block; the join fills
    the runtime block; the verdict engine fills the decision block. Kept as one flat
    record so it round-trips cleanly to the AiDOOS ledger.
    """
    # identity / structure
    id: str
    name: str
    level: Level
    parent_id: Optional[str] = None
    kind: Kind = Kind.BUILT

    # what it is (extraction, LLM-assisted with the customer's own key)
    inferred_purpose: Optional[str] = None
    ai_or_not: AIClass = AIClass.UNKNOWN
    size_complexity: Optional[str] = None            # coarse bucket; keep de-identifiable
    dependencies: list[str] = field(default_factory=list)

    # runtime block (filled by the join, §7)
    deployed_service: Optional[str] = None           # service_name from the join
    runtime: Runtime = Runtime.UNKNOWN
    cloud_environment: Optional[str] = None
    usage: Optional[ServiceUsage] = None
    last_used: Optional[str] = None
    join_confidence: Confidence = Confidence.LOW

    # rationalization block
    redundancy_cluster: Optional[str] = None         # cluster id for consolidate verdicts

    # decision block (filled by verdict/, gated on evidence)
    verdict: Verdict = Verdict.UNDECIDED
    confidence: Confidence = Confidence.LOW
    evidence: list[Evidence] = field(default_factory=list)

    # conversion (SPEC §9) - draft in v1, precise once the ledger matures
    est_effort_to_act: Optional[str] = None

    # agentify (V1) - code-content decision/rule density; a naming-independent toil signal
    toil_signal: int = 0

    # The BUSINESS unit this capability names ("payment reconciliation", "purchase order"),
    # when the code is organised by domain rather than by layer. Empty for layer buckets
    # (core logic / API / hooks). This is the field that decides whether the report reads
    # "accounts: service layer" or "accounts: payment reconciliation" - see extract/units.py.
    # False = StackXray has no parser for this file type, so nothing here was assessed.
    # An UNREADABLE capability must never receive an actionable verdict: saying "KEEP - no
    # action indicated" about code we never parsed is the same overclaim as inventing a
    # finding. It gets UNDECIDED, which is the honest state.
    readable: bool = True
    domain_unit: str = ""
    # The architectural role of the code (core / api / components / data-model). Kept
    # SEPARATELY from the name, because a domain unit is named for its job and the role
    # is then the only thing that still says "this is a React page, not a workflow".
    role: str = ""
    # A few representative file paths. The domain vocabulary must be able to match what the
    # code is CALLED ON DISK, not only the label we gave it: `BankReconciliation.tsx` names
    # the single most obvious agent opportunity in the repo, and the scorer could not see it.
    paths: list[str] = field(default_factory=list)
    # True when the process STOPS for a person - a Salesforce Flow <screens>, an approval step,
    # a review/sign-off gate. This is the seam between an AGENT (automate a rules process) and a
    # DIGITAL TWIN (give the human a live model to decide against). Set by the extractors that
    # can see it (Salesforce/ServiceNow today); the twin lens reads it. See agentify/twin.py.
    human_in_loop: bool = False


@dataclass
class CapabilityMap:
    """The full multi-level inventory for one scan (SPEC §5).

    A flat list of Capabilities linked by parent_id, plus scan-level metadata. This is
    what report/ renders and what consent/fingerprint.py de-identifies before anything
    is allowed to leave the environment.
    """
    capabilities: list[Capability] = field(default_factory=list)
    scan_id: Optional[str] = None                    # local, opaque; not customer PII
    generated_at: Optional[str] = None               # ISO timestamp, set by the runner

    def by_level(self, level: Level) -> list[Capability]:
        return [c for c in self.capabilities if c.level == level]

    def children_of(self, parent_id: str) -> list[Capability]:
        return [c for c in self.capabilities if c.parent_id == parent_id]


# --------------------------------------------------------------------------------------
# Confidence helpers - LOW < MEDIUM < HIGH. Used by the join and verdict engines to
# combine and cap confidences (SPEC §4.4, §7). Kept here so the ordering has one home.
# --------------------------------------------------------------------------------------

_CONFIDENCE_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


def confidence_rank(c: Confidence) -> int:
    return _CONFIDENCE_RANK[c]


def min_confidence(*cs: Confidence) -> Confidence:
    """Return the lowest confidence among the arguments (the honest 'weakest link')."""
    return min(cs, key=confidence_rank)

"""AiDOOS cloud tier (SPEC §6 cloud, §9) - consented-only benchmark + estimate + proposal.

THE ONLY MODULE PERMITTED NETWORK EGRESS. It refuses any payload that is not a
CapabilityFingerprint (SPEC §14.4). Keeping all outbound-HTTP use confined here lets a
reviewer verify the boundary by reading one file (DESIGN.md §5). A test enforces that no
other module imports an outbound HTTP client.

v1 status: STUB responses (SPEC §16.5). The guard + fingerprint-only contract are REAL;
the actual HTTP call is not wired yet (no live endpoint). Real cross-customer benchmark +
calibration-ledger estimate live server-side, not in the shipped tool (SPEC §3).
"""

from __future__ import annotations

from ..consent import CapabilityFingerprint

# When the real endpoint is wired, the outbound client (httpx/requests) is imported HERE
# and nowhere else. Until then these return stubs - but the guard already holds.
AIDOOS_ENDPOINT = "https://cloud.aidoos.com/xray/v1"  # not called in v1


def _require_fingerprint(payload) -> None:
    """The boundary, in one line: nothing but a CapabilityFingerprint may be sent."""
    if not isinstance(payload, CapabilityFingerprint):
        raise TypeError(
            "cloud egress refused: only a CapabilityFingerprint may leave the environment "
            f"(got {type(payload).__name__}). See SPEC §4/§14.4."
        )


def send_for_benchmark(fp: CapabilityFingerprint) -> dict:
    """Send the fingerprint (and ONLY a fingerprint) to AiDOOS for cross-customer
    benchmarking ('orgs like you consolidated these'). v1: stubbed placeholder."""
    _require_fingerprint(fp)
    # TODO(v1.x): POST fp.to_json() to {AIDOOS_ENDPOINT}/benchmark and return the response.
    return {
        "status": "stub",
        "scan_token": fp.scan_token,
        "benchmark": "cross-customer benchmark runs server-side; not wired in v1",
    }


def request_estimate(fp: CapabilityFingerprint, capability_id: str) -> dict:
    """Ask the calibration ledger what an action would take (SPEC §9). v1: returns a draft
    range + scoping route, not a precise quote (ledger still thin, SPEC §12/§15)."""
    _require_fingerprint(fp)
    # TODO(v1.x): POST to {AIDOOS_ENDPOINT}/estimate with capability_id (an opaque local id).
    return {
        "status": "stub",
        "scan_token": fp.scan_token,
        "capability_id": capability_id,
        "estimate": "draft range only until the calibration ledger matures",
    }

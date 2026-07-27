"""Prometheus HTTP transport (SPEC §6) - queries the CUSTOMER's own Prometheus.

Isolated like extract/_llm_http.py so the trust boundary stays auditable: this talks only
to the customer-supplied Prometheus URL (their infra), never AiDOOS. Listed in the egress
allowlist alongside extract/_llm_http.py and cloud/.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request


def query(base_url: str, promql: str, timeout: int = 30) -> dict:
    """GET {base_url}/api/v1/query?query=... and return the parsed JSON result."""
    url = base_url.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": promql})
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

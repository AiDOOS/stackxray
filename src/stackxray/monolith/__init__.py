"""Monolith mode (Milestone 11) - runtime evidence for one-deployed-unit apps.

The container join (`code -> image -> service -> per-service usage`) can't judge a monolith:
there's one deployed unit, so the 'services' are really MODULES wired by a router. Here the
join key is the ROUTE: derive module -> route-prefix from the code (Django URLconf), ingest
an access-log summary, aggregate traffic per module, and attach it. A module whose routes
get zero traffic over the window is a dead feature -> RETIRE (evidence-backed).

This is what lights up the huge monolith/legacy estate the microservice model misses.
v1: Django URLconf + access-log CSV, app-level. Other frameworks/finer granularity later.

Confidence is MEDIUM: access-log traffic is solid evidence, but attributing a path to a
module via prefix is a mapping step (coarser than a container's direct service usage).
"""

from __future__ import annotations

import csv
import os
import re

from ..config import ScanConfig
from ..extract._scan import IGNORE_DIRS
from ..models import Capability, Confidence, Evidence, Level, ServiceUsage

# path('prefix/', include('app.urls'))  -> (prefix, app)
_INCLUDE_RE = re.compile(
    r"""path\(\s*['"]([^'"]*)['"]\s*,\s*include\(\s*['"]([\w.]+)\.urls['"]""")


def _find_root_urlconf(repo_path: str) -> str | None:
    """The Django project package holds wsgi.py + urls.py (the ROOT_URLCONF).

    Skips dependency/build dirs (a vendored Django in .venv also has wsgi.py+urls.py) and
    returns the SHALLOWEST match - the project's own package, not a dependency's."""
    candidates: list[str] = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        if "wsgi.py" in files and "urls.py" in files:
            candidates.append(os.path.join(root, "urls.py"))
    if not candidates:
        return None
    return min(candidates, key=lambda p: (p.count(os.sep), len(p)))


def django_route_map(repo_path: str) -> dict[str, str]:
    """Return {app_name: url_prefix} from the root URLconf's include() calls."""
    urlconf = _find_root_urlconf(repo_path)
    if not urlconf:
        return {}
    with open(urlconf, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    route_map: dict[str, str] = {}
    for prefix, dotted in _INCLUDE_RE.findall(text):
        app = dotted.split(".", 1)[0]                # 'contracts' from 'contracts.urls'
        # keep the most specific (longest) prefix if an app is mounted more than once
        if app not in route_map or len(prefix) > len(route_map[app]):
            route_map[app] = prefix.strip("/")
    return route_map


def parse_access_log(path: str) -> list[tuple[str, int, str | None]]:
    """Aggregated access-log CSV -> [(request_path, requests, last_seen)]."""
    rows: list[tuple[str, int, str | None]] = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            p = (row.get("path") or "").strip()
            if not p:
                continue
            try:
                reqs = int(float((row.get("requests") or "0").strip() or 0))
            except ValueError:
                reqs = 0
            rows.append((p, reqs, (row.get("last_seen") or row.get("last_used") or "").strip() or None))
    return rows


def app_usage_from_access(route_map: dict[str, str], rows: list[tuple[str, int, str | None]],
                          window_days: int) -> dict[str, ServiceUsage]:
    """Attribute each access-log path to the app with the longest matching NON-EMPTY prefix,
    sum traffic per app. Apps in the route map that never appear -> 0 (observed dead).

    Empty-prefix apps (mounted at '/') can't be disambiguated by prefix, so they're left
    unattributed (their capabilities stay honestly UNDECIDED) rather than mis-credited.
    """
    prefixed = {app: pfx for app, pfx in route_map.items() if pfx}
    totals: dict[str, int] = {app: 0 for app in prefixed}
    last: dict[str, str | None] = {app: None for app in prefixed}

    for req_path, reqs, last_seen in rows:
        norm = req_path.strip("/")
        best = max((app for app, pfx in prefixed.items() if norm.startswith(pfx)),
                   key=lambda a: len(prefixed[a]), default=None)
        if best is None:
            continue
        totals[best] += reqs
        if last_seen and (last[best] is None or last_seen > last[best]):
            last[best] = last_seen

    return {app: ServiceUsage(service_name=app, requests=totals[app], window_days=window_days,
                              last_used=last[app], source="access-log")
            for app in prefixed}


def enrich(capabilities: list[Capability], config: ScanConfig) -> list[Capability]:
    """Attach per-app access-log usage to each app's capabilities (app-level join).

    Only fills capabilities the container join left empty (usage is None), so a hybrid
    repo keeps its container verdicts and the monolith parts get theirs.
    """
    route_map = django_route_map(config.repo_path)
    if config.monolith.nginx_log_path:                       # connect: read raw nginx logs
        from .nginx import parse_nginx_logs
        rows, window = parse_nginx_logs(config.monolith.nginx_log_path)
    else:                                                    # or a pre-aggregated CSV export
        rows, window = parse_access_log(config.monolith.access_log_path), config.monolith.window_days
    app_usage = app_usage_from_access(route_map, rows, window)

    for cap in capabilities:
        if cap.level != Level.CAPABILITY or cap.usage is not None or not cap.parent_id:
            continue
        app = cap.parent_id.split(":", 1)[-1]        # 'prod:contracts' -> 'contracts'
        usage = app_usage.get(app)
        if usage is None:
            continue
        cap.usage = usage
        cap.last_used = usage.last_used
        cap.deployed_service = app
        cap.join_confidence = Confidence.MEDIUM      # coarser than a container service join
        cap.evidence.append(Evidence(
            "monolith",
            f"app '{app}' routes: {usage.requests} requests over {usage.window_days}d (access-log)",
            locator=route_map.get(app) or app))
    return capabilities

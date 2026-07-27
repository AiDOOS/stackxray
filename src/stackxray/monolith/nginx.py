"""nginx access-log connector (Milestone 13) - read prod logs directly, no export.

For a VM/nginx deployment, the runtime truth is the access log. This reads the raw logs
straight off the box - current AND rotated/gzipped history - parses every request, and
aggregates by route. No human exports anything, so nothing is missed. And it needs no
credentials: the logs are just a path on the server, exactly like the code path.

Point at a single log file or a directory (e.g. /var/log/nginx) - it reads them all.
Output feeds the monolith route-join (app_usage_from_access), which maps routes -> apps.
"""

from __future__ import annotations

import gzip
import os
import re
from datetime import datetime

# combined/common log: ... [10/Oct/2026:13:55:36 +0000] "GET /path?q=1 HTTP/1.1" 200 ...
_LINE = re.compile(r'\[([^\]]+)\]\s+"[A-Z]+\s+(\S+)\s+HTTP')


def _iter_log_files(path: str):
    if os.path.isfile(path):
        yield path
    elif os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for f in files:
                if "access" in f and ".log" in f:      # access.log, access.log.1, access.log.2.gz
                    yield os.path.join(root, f)


def _open(fp: str):
    if fp.endswith(".gz"):
        return gzip.open(fp, "rt", encoding="utf-8", errors="replace")
    return open(fp, "r", encoding="utf-8", errors="replace")


def parse_nginx_logs(path: str) -> tuple[list[tuple[str, int, str | None]], int]:
    """Return ([(request_path, count, last_seen_iso)], window_days) from the log(s).

    window_days is the span from the earliest to latest logged request - the real
    observation window, derived from the data, not guessed.
    """
    counts: dict[str, int] = {}
    latest: dict[str, str] = {}
    earliest = newest = None

    for fp in _iter_log_files(path):
        try:
            fh = _open(fp)
        except OSError:
            continue
        with fh:
            for line in fh:
                m = _LINE.search(line)
                if not m:
                    continue
                req_path = m.group(2).split("?", 1)[0]      # strip query string
                counts[req_path] = counts.get(req_path, 0) + 1
                try:
                    dt = datetime.strptime(m.group(1), "%d/%b/%Y:%H:%M:%S %z")
                except ValueError:
                    continue
                iso = dt.date().isoformat()
                if req_path not in latest or iso > latest[req_path]:
                    latest[req_path] = iso
                if earliest is None or dt < earliest:
                    earliest = dt
                if newest is None or dt > newest:
                    newest = dt

    rows = [(p, counts[p], latest.get(p)) for p in counts]
    window = max(1, (newest - earliest).days) if earliest and newest else 30
    return rows, window

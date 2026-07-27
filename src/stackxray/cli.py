"""One-command entrypoint (SPEC §11, §14.2).

`stackxray scan --repo <path> [--usage-import <csv>] --report-port 7373`
Runs the local pipeline and serves the HTML report on localhost. This is the single
command the customer runs inside their environment.

Report host defaults to 127.0.0.1 (loopback, per SPEC §11). Inside a container, pass
`--report-host 0.0.0.0` and map the port to host-loopback: `-p 127.0.0.1:7373:7373`.
"""

from __future__ import annotations

import argparse

from .config import ConsumptionConfig, MonolithConfig, ObservabilityConfig, ScanConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stackxray",
        description="StackXray - self-run software capability scan (SPEC.md).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan a repo and serve the local report")
    scan.add_argument("--repo", required=True, help="path to the checked-out repo")

    obs = scan.add_argument_group("runtime evidence (any/all; more sources = sharper verdicts)")
    obs.add_argument("--usage-import", help="generic usage CSV (service,requests,window_days,last_used)")
    obs.add_argument("--prometheus-url", help="live Prometheus base URL (customer endpoint)")
    obs.add_argument("--prometheus-file", help="saved Prometheus query-result JSON")
    obs.add_argument("--otel-file", help="OpenTelemetry metrics JSON export")
    obs.add_argument("--datadog", help="Datadog query-result JSON export")
    obs.add_argument("--cloudwatch", help="CloudWatch get-metric-data JSON export")
    obs.add_argument("--newrelic", help="New Relic NRQL result JSON export")
    obs.add_argument("--dynatrace", help="Dynatrace metrics v2 JSON export")
    obs.add_argument("--host-inventory", help="VM host/process inventory CSV")
    obs.add_argument("--nginx-log", help="nginx access-log file or folder (reads .gz history)")
    obs.add_argument("--access-log", help="pre-aggregated access-log CSV (path,requests,last_seen)")

    con = scan.add_argument_group("bought-SaaS consumption lens (no code footprint)")
    con.add_argument("--sso", help="SSO app-assignment export CSV (Okta/Azure AD)")
    con.add_argument("--spend", help="expense/procurement export CSV")
    con.add_argument("--egress", help="DNS/egress summary CSV")

    scan.add_argument("--report-port", type=int, default=7373, help="report port")
    scan.add_argument("--report-host", default="127.0.0.1",
                      help="bind host for the report (default loopback; use 0.0.0.0 in a "
                           "container and map -p 127.0.0.1:7373:7373)")

    app = sub.add_parser("app", help="launch the local app (a form + report in your browser)")
    app.add_argument("--port", type=int, default=7373)
    app.add_argument("--host", default="127.0.0.1",
                     help="default loopback; use 0.0.0.0 only inside a container")
    app.add_argument("--no-open", action="store_true", help="don't auto-open the browser")
    return p


def _config_from_args(args: argparse.Namespace) -> ScanConfig:
    return ScanConfig(
        repo_path=args.repo,
        observability=ObservabilityConfig(
            usage_import_path=args.usage_import,
            prometheus_url=args.prometheus_url,
            prometheus_result_path=args.prometheus_file,
            otel_metrics_path=args.otel_file,
            datadog_path=args.datadog,
            cloudwatch_path=args.cloudwatch,
            newrelic_path=args.newrelic,
            dynatrace_path=args.dynatrace,
            host_inventory_path=args.host_inventory,
        ),
        consumption=ConsumptionConfig(
            sso_path=args.sso, spend_path=args.spend, egress_path=args.egress,
        ),
        monolith=MonolithConfig(nginx_log_path=args.nginx_log, access_log_path=args.access_log),
        report_port=args.report_port,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        from .pipeline import run_scan
        from .report import serve
        cmap = run_scan(_config_from_args(args))
        caps = [c for c in cmap.capabilities if c.level.value == "capability"]
        print(f"Scanned {args.repo}: {len(caps)} capabilities across "
              f"{sum(1 for c in cmap.capabilities if c.level.value == 'product')} products.")
        serve(cmap, args.report_port, host=args.report_host)
    elif args.command == "app":
        from .webapp import serve_app
        serve_app(port=args.port, host=args.host, open_browser=not args.no_open)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

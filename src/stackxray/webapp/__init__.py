"""Local web app (Milestone 12) - the usable, no-CLI face of StackXray.

Serves an input FORM + the report on localhost. 100% local: the user types PATHS to code
and (optionally) exported telemetry/SaaS files that already sit on their machine; the scan
runs in-process; the report renders in the same browser. Nothing leaves (SPEC §11).

Every input is a path (text field) - consistent with path-over-upload, and it means no
file-upload plumbing. A later pywebview wrapper turns this same UI into a native window
with 'Browse…' dialogs; the HTML/handlers here are unchanged.

Friction ladder in the form: ONE required field (code path). Everything else is optional
and grouped under collapsed sections - each one only sharpens the verdicts.
"""

from __future__ import annotations

import os
import subprocess
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..config import (
    ConsumptionConfig,
    LLMConfig,
    MonolithConfig,
    ObservabilityConfig,
    ScanConfig,
)
from ..pipeline import run_scan
from ..report import render_html

LOOPBACK = "127.0.0.1"

_CSS = """
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
  color:#16181d;background:#f4f2ec}
.hero{background:linear-gradient(180deg,#12161d,#0c0f14);color:#eef2f4;padding:26px 0}
.wrap{max-width:760px;margin:0 auto;padding:0 24px}
.wordmark{font-weight:800;letter-spacing:.22em;font-size:13px}.wordmark b{color:#4fe3d6}
.hero h1{font-family:Georgia,serif;font-weight:500;font-size:30px;margin:14px 0 4px}
.hero p{color:#aeb6bd;margin:0;font-size:13.5px}
form{max-width:760px;margin:26px auto;padding:0 24px 60px}
.card{background:#fffdf8;border:1px solid #e5e2d9;border-radius:12px;padding:20px;margin:0 0 16px}
label{display:block;font-weight:600;font-size:13px;margin:0 0 4px}
.hint{color:#6b7076;font-size:12.5px;margin:0 0 10px;font-weight:400}
input[type=text],input[type=password]{width:100%;padding:9px 11px;border:1px solid #d7d3c8;border-radius:8px;
  font:inherit;font-size:14px;background:#fff}
input:focus{outline:2px solid #4fe3d6;border-color:#4fe3d6}
.req label::after{content:' *';color:#c22a21}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.row{margin:0 0 14px}.row:last-child{margin:0}
details{border:1px solid #e5e2d9;border-radius:12px;margin:0 0 16px;background:#fffdf8}
details>summary{cursor:pointer;padding:15px 20px;font-weight:600;list-style:none;display:flex;justify-content:space-between}
details>summary::-webkit-details-marker{display:none}
details>summary .opt{color:#6b7076;font-weight:400;font-size:12.5px}
details .body{padding:4px 20px 18px}
.check{display:flex;gap:8px;align-items:center;font-weight:400;font-size:13.5px}
.check input{width:auto}
button{background:#16181d;color:#fff;border:0;border-radius:10px;padding:13px 22px;font:inherit;
  font-weight:700;font-size:15px;cursor:pointer;margin-top:6px}
button:hover{background:#000}
.err{background:#fbe9e7;border:1px solid #f3c0ba;color:#a1231b;border-radius:10px;padding:12px 16px;margin:0 0 16px}
.foot{color:#6b7076;font-size:12.5px;margin-top:14px}
"""


def _field(name, label, hint, placeholder="", required=False, kind="text"):
    cls = ' class="row req"' if required else ' class="row"'
    return (f'<div{cls}><label for="{name}">{label}</label>'
            f'<p class="hint">{hint}</p>'
            f'<input type="{kind}" id="{name}" name="{name}" placeholder="{placeholder}"></div>')


def _esc(s: str) -> str:
    import html as _html
    return _html.escape(s)


def form_html(error: str | None = None) -> str:
    err = f'<div class="err">{_esc(error)}</div>' if error else ""

    code = _field("repo", "Code path", "Point at code already on disk - a repo, an app folder, "
                  "or a workspace root holding many. Nothing is uploaded or cloned.",
                  "C:\\path\\to\\repo", required=True)
    pull = ('<div class="row"><label class="check"><input type="checkbox" name="pull_latest" value="1">'
            'Pull latest first (git fetch/pull on this working copy - small repos)</label></div>')
    infra = _field("infra_repo", "Separate infra repo (optional)",
                   "If your Kubernetes/Terraform lives in a different repo, add its path.",
                   "C:\\path\\to\\infra")

    runtime_fields = "".join([
        _field("access_log", "Access-log summary (monolith)", "CSV: path,requests[,last_seen]. Lights up per-app KEEP/RETIRE for monoliths."),
        _field("usage_csv", "Generic usage CSV", "CSV: service,requests,window_days,last_used."),
        _field("prometheus_file", "Prometheus result JSON", "Exported /api/v1/query result."),
        _field("otel_file", "OpenTelemetry metrics JSON", "OTLP/JSON metrics export."),
        _field("datadog", "Datadog export", "query-result JSON."),
        _field("cloudwatch", "CloudWatch export", "get-metric-data JSON."),
        _field("newrelic", "New Relic export", "NRQL result JSON."),
        _field("dynatrace", "Dynatrace export", "metrics v2 JSON."),
        _field("host_inventory", "VM host inventory CSV", "process,requests,last_active,cpu - for bare VMs."),
    ])
    saas_fields = "".join([
        _field("sso", "SSO app-assignment export", "Okta/Azure AD CSV: app,users_assigned,active_users,last_login."),
        _field("spend", "Spend / expense export", "CSV: vendor,annual_cost,renewal_date."),
        _field("egress", "DNS / egress summary", "CSV: domain,requests."),
    ])
    connect_fields = "".join([
        _field("nginx_log", "Nginx access-log path (server / VM)",
               "Point at the log file OR folder (e.g. /var/log/nginx). Reads them ALL - current and "
               "rotated .gz history - and maps every request to your app's routes. No export, nothing "
               "missed, no credentials (it's just a path on the box)."),
        _field("prometheus_url", "Prometheus URL (live)",
               "For k8s/containers: the tool queries Prometheus directly for ALL service traffic. Uses "
               "this machine's existing access; URL/token stay local, never sent to AiDOOS.",
               "http://prometheus.internal:9090"),
        _field("prometheus_query", "Prometheus query (optional)",
               "Override the default request-count query if your metric differs."),
    ])
    llm_fields = "".join([
        _field("llm_base_url", "LLM endpoint (your own)", "OpenAI-compatible base URL. Enriches descriptions; used locally, never sent to AiDOOS.", "https://api.openai.com/v1"),
        _field("llm_model", "LLM model", "e.g. gpt-4o-mini."),
        _field("llm_key", "LLM API key (your own)", "Stays on this machine.", kind="password"),
    ])

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StackXray - new scan</title><style>{_CSS}</style></head><body>
<div class="hero"><div class="wrap"><div class="wordmark">STACK<b>XRAY</b></div>
  <h1>Scan your stack</h1>
  <p>Everything runs locally on this machine. Only a path is required - add exports below to sharpen the verdicts.</p>
</div></div>
<form method="POST" action="/scan">
  {err}
  <div class="card">{code}{pull}{infra}</div>
  <details><summary><span>Connect to your environment (live)</span><span class="opt">reads prod directly · nothing missed</span></summary>
    <div class="body">{connect_fields}</div></details>
  <details><summary><span>Runtime evidence (exports)</span><span class="opt">optional · or use live connect above</span></summary>
    <div class="body">{runtime_fields}</div></details>
  <details><summary><span>Bought-SaaS (SSO / spend / egress)</span><span class="opt">optional · finds shelfware</span></summary>
    <div class="body">{saas_fields}</div></details>
  <details><summary><span>LLM enrichment</span><span class="opt">optional · your own model</span></summary>
    <div class="body">{llm_fields}</div></details>
  <button type="submit">Run scan</button>
  <p class="foot">Local scan · your code and data never leave this machine. Large repos may take a moment.</p>
</form></body></html>"""


def _config_from_form(fields: dict[str, list[str]]) -> ScanConfig:
    def g(name: str) -> str | None:
        v = (fields.get(name) or [""])[0].strip()
        return v or None

    if g("llm_key"):
        os.environ[LLMConfig().api_key_env] = g("llm_key")

    return ScanConfig(
        repo_path=g("repo") or "",
        observability=ObservabilityConfig(
            usage_import_path=g("usage_csv"), prometheus_result_path=g("prometheus_file"),
            prometheus_url=g("prometheus_url"),
            prometheus_query=g("prometheus_query") or ObservabilityConfig().prometheus_query,
            otel_metrics_path=g("otel_file"), datadog_path=g("datadog"),
            cloudwatch_path=g("cloudwatch"), newrelic_path=g("newrelic"),
            dynatrace_path=g("dynatrace"), host_inventory_path=g("host_inventory"),
        ),
        consumption=ConsumptionConfig(sso_path=g("sso"), spend_path=g("spend"), egress_path=g("egress")),
        monolith=MonolithConfig(access_log_path=g("access_log"), nginx_log_path=g("nginx_log")),
        llm=LLMConfig(base_url=g("llm_base_url"), model=g("llm_model")),
    )


def run_from_form(fields: dict[str, list[str]]) -> tuple[int, str]:
    """Return (status, html): the report on success, or the form + error on failure."""
    repo = (fields.get("repo") or [""])[0].strip()
    if not repo:
        return 400, form_html("Please provide a code path.")
    if not os.path.isdir(repo):
        return 400, form_html(f"Path not found or not a directory: {repo}")

    if (fields.get("pull_latest") or [""])[0] and os.path.isdir(os.path.join(repo, ".git")):
        try:
            subprocess.run(["git", "-C", repo, "pull", "--ff-only"], timeout=120,
                           capture_output=True)
        except Exception:
            pass  # best-effort freshness; never block the scan

    try:
        cmap = run_scan(_config_from_form(fields))
    except Exception:
        return 500, form_html("Scan failed:\n" + traceback.format_exc().splitlines()[-1])
    return 200, render_html(cmap)


def build_handler():
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, html: str):
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html", "/new"):
                self._send(200, form_html())
            else:
                self.send_error(404)

        def do_POST(self):  # noqa: N802
            if self.path != "/scan":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            fields = urllib.parse.parse_qs(body, keep_blank_values=True)
            status, html = run_from_form(fields)
            self._send(status, html)

        def log_message(self, *args):
            pass

    return Handler


def serve_app(port: int = 7373, host: str = LOOPBACK, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer((host, port), build_handler())
    url = f"http://{host}:{port}"
    print(f"StackXray is running at {url}  (Ctrl-C to stop)")
    if open_browser and os.environ.get("STACKXRAY_OPEN", "1") != "0":
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

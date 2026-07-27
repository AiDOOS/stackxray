"""V1 browser app - a clean single-field form to scan a folder, served on localhost.

Simpler than the full webapp: one input (the folder path), one button, then the Agentify
report. Everything local. Launched by the packaged StackXray.bat.
"""

from __future__ import annotations

import html
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from ..report._brand import favicon, logo
from ..v1 import MissingKeyError, build_report_html

_FORM_CSS = """
*{box-sizing:border-box}
body{margin:0;min-height:100vh;font:16px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
  color:#eef2f4;background:radial-gradient(120% 90% at 80% -10%,rgba(124,92,255,.28)0,transparent 55%),
  linear-gradient(180deg,#141b26,#0c0f14);display:flex;align-items:center;justify-content:center;padding:24px}
.box{width:100%;max-width:560px}
.brandrow{display:flex;align-items:center;gap:12px;margin-bottom:30px}
.brand{height:32px;width:auto}
.wordmark{font-weight:800;letter-spacing:.22em;font-size:13px}.wordmark b{color:#7c5cff}
.byline{margin-left:auto;color:#8892a0;font-size:12px;letter-spacing:.06em}
.byline b{color:#fff;font-weight:700}
h1{font-family:Georgia,serif;font-weight:500;font-size:32px;margin:0 0 8px}
.sub{color:#aeb6bd;margin:0 0 26px;font-size:15px}
label{display:block;font-weight:600;font-size:13px;margin:0 0 6px;color:#cdd4da}
input[type=text]{width:100%;padding:13px 15px;border:1px solid #2a3340;border-radius:10px;font:inherit;
  font-size:15px;background:#0e141d;color:#fff}
input:focus{outline:2px solid #7c5cff;border-color:#7c5cff}
.hint{color:#8892a0;font-size:12.5px;margin:8px 0 0}
button{margin-top:20px;width:100%;background:#7c5cff;color:#fff;border:0;border-radius:11px;padding:15px;
  font:inherit;font-weight:700;font-size:16px;cursor:pointer}
button:hover{background:#6a49f5}
.err{background:#3a1d1b;border:1px solid #7a3a34;color:#ffb4ab;border-radius:10px;padding:12px 15px;margin:0 0 18px;font-size:14px}
.foot{color:#71797f;font-size:12px;margin-top:22px;text-align:center}
.wait{color:#aeb6bd;font-size:13px;margin-top:14px;display:none}
"""

_JS = ("var f=document.querySelector('form');if(f){f.addEventListener('submit',function(){"
       "document.getElementById('wait').style.display='block';"
       "var b=document.querySelector('button');b.disabled=true;b.textContent='Scanning...';});}")


def form_html(error: str | None = None) -> str:
    err = f'<div class="err">{html.escape(error)}</div>' if error else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StackXray</title>{favicon()}<style>{_FORM_CSS}</style></head><body>
<div class="box">
  <div class="brandrow">{logo()}<div class="wordmark">STACK<b>XRAY</b></div>
    <div class="byline">by <b>AiDOOS</b></div></div>
  <h1>Find your AI-agent opportunities</h1>
  <p class="sub">Point at a folder of code, or a GitHub URL. Everything runs on this computer - your code never leaves.</p>
  <form method="POST" action="/scan">{err}
    <label for="repo">Folder path or GitHub URL</label>
    <input type="text" id="repo" name="repo" placeholder="C:\\path\\to\\your-project   or   https://github.com/org/repo" autofocus>
    <label for="tickets" style="margin-top:16px">Ticket / issue export <span style="font-weight:400;color:#8892a0">(optional)</span></label>
    <input type="text" id="tickets" name="tickets" placeholder="C:\\path\\to\\jira-export.csv   (.csv or .json)">
    <p class="hint">A Jira / ServiceNow CSV or GitHub issues JSON. Findings then show <b>how many
      real tickets relate to each capability</b>, and heavy volume lifts a candidate in the
      ranking - measured from your own tracker, never estimated.</p>
    <p class="hint">Paste your AI key (Anthropic or OpenAI) into <b>API-KEY.txt</b> next to this
      launcher. StackXray reads your code with it - your key and your code stay on this computer.</p>
    <button type="submit">Run scan</button>
    <p class="wait" id="wait">Scanning your code. The report will appear here in a moment.</p>
  </form>
  <p class="foot">Local scan · nothing leaves this computer.</p>
</div><script>{_JS}</script></body></html>"""


def _run(fields: dict) -> tuple[int, str]:
    repo = (fields.get("repo") or [""])[0].strip()
    if not repo:
        return 400, form_html("Please enter a folder path or a GitHub URL.")
    # Local = path-based, not upload: the export already sits on this disk. Validate up front so
    # a typo'd path is a clear message, not a silently ticket-less report.
    tickets = (fields.get("tickets") or [""])[0].strip().strip('"')
    if tickets and not os.path.isfile(tickets):
        return 400, form_html(f"Ticket export not found: {tickets}")
    try:
        return 200, build_report_html(repo, tickets_path=tickets or None)
    except MissingKeyError as e:                      # no key -> tell them how to add one
        return 400, form_html(str(e).replace("\n", "<br>"))
    except ValueError as e:                          # not-found / clone problems -> friendly
        return 400, form_html(str(e))
    except Exception:
        return 500, form_html("Scan failed: " + traceback.format_exc().splitlines()[-1])


def build_handler():
    class H(BaseHTTPRequestHandler):
        def _send(self, status, body):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            self._send(200, form_html()) if self.path in ("/", "/index.html") else self.send_error(404)

        def do_POST(self):  # noqa: N802
            if self.path != "/scan":
                return self.send_error(404)
            n = int(self.headers.get("Content-Length", 0))
            fields = parse_qs(self.rfile.read(n).decode("utf-8"), keep_blank_values=True)
            self._send(*_run(fields))

        def log_message(self, *a):
            pass

    return H


def serve(port: int = 7373, host: str = "127.0.0.1", open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer((host, port), build_handler())
    url = f"http://{host}:{port}"
    print(f"StackXray is open in your browser at {url}   (close this window to stop)")
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

"""Serve the report on localhost (SPEC §11) - 127.0.0.1 ONLY, never 0.0.0.0.

The report is rendered once, up front, and held in memory; the server just hands it out.
No routes accept input and nothing egresses - the consent-gated cloud call is a separate,
explicit action (M5), not something this server does.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..models import CapabilityMap
from .render import render_html

LOOPBACK = "127.0.0.1"


def build_handler(page_html: str):
    body = page_html.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (stdlib naming)
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def log_message(self, *args):  # keep the console quiet
            pass

    return Handler


def serve(cmap: CapabilityMap, port: int, host: str = LOOPBACK) -> None:
    """Render the map and serve it at http://127.0.0.1:<port> until interrupted."""
    handler = build_handler(render_html(cmap))
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"StackXray report ready at http://{host}:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

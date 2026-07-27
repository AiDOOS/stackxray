"""Local HTML report (SPEC §4, §11) - served on localhost, nothing leaves.

Renders the CapabilityMap + verdict tiers into a report a CIO/CTO can read, with the
per-verdict "What would it take to do this?" disclosure and a consent-gated share action
(SPEC §9, §11). Useful stand-alone even if the customer never consents to share.

v1 status: IMPLEMENTED - see render.py (self-contained, script-free HTML) and server.py
(127.0.0.1-only stdlib server).
"""

from __future__ import annotations

from .render import render_html
from .server import serve

__all__ = ["render_html", "serve"]

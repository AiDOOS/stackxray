"""LLM enrichment + universal extraction (SPEC §6, §14.1; Milestone 7c) - customer's key.

Track B. Two capabilities, both using the CUSTOMER's own model (their key/endpoint, so
data stays within their vendor relationship - never AiDOOS):
  - enrich(): add an inferred_purpose to a structurally-extracted capability.
  - universal_extract(): extract capabilities from ANY language (incl. COBOL/RPG) where a
    native parser is thin or absent.

Both degrade to a no-op / None with no key, so the tool is fully useful offline and only
gets richer when a key is supplied. Parsing is separated from transport so it's testable
without a network call.
"""

from __future__ import annotations

import json
import os

from ..config import LLMConfig
from ..models import AIClass, Capability, Evidence
from . import _scan
from .base import CapabilityDraft

_MAX_FILES = 40           # cap context so a huge product doesn't blow the token budget
_MAX_CHARS_PER_FILE = 2000

_EXTRACT_SYSTEM = (
    "You are a software capability analyst. Given file names and code excerpts from ONE "
    "product, list its distinct capabilities. Reply with ONLY a JSON array of objects, "
    'each: {"suffix": short role/name, "id_hint": stable slug, "ai": true/false, '
    '"size": "small"|"medium"|"large"}. No prose.'
)


# ---- pure parsing (unit-testable without a network call) ------------------------------

def parse_capabilities_json(text: str) -> list[CapabilityDraft]:
    """Parse the model's JSON array into CapabilityDrafts. Tolerates ```json fences and
    leading/trailing prose by extracting the first [...] block."""
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        items = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return []
    drafts: list[CapabilityDraft] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not it.get("suffix"):
            continue
        drafts.append(CapabilityDraft(
            suffix=str(it["suffix"])[:80],
            id_hint=f"llm:{it.get('id_hint') or i}",
            ai=AIClass.AI if it.get("ai") else AIClass.NON_AI,
            size_complexity=it.get("size") if it.get("size") in ("small", "medium", "large") else None,
            evidence=[Evidence("extract", "identified by the LLM universal extractor")],
        ))
    return drafts


def _context_from(files: list[tuple[str, str]]) -> str:
    parts = []
    for _abs, rel in files[:_MAX_FILES]:
        parts.append(f"// FILE: {rel}\n{_scan.read_text(_abs)[:_MAX_CHARS_PER_FILE]}")
    return "\n\n".join(parts)


# ---- enrichment ----------------------------------------------------------------------

class NullEnricher:
    """No key -> no enrichment. Leaves inferred_purpose as-is (honest blank)."""

    def enrich(self, capability: Capability, code_context: str) -> Capability:
        return capability


class CustomerKeyEnricher:
    """Fills inferred_purpose via the customer's model. Network egress goes to THEIR
    endpoint (_llm_http), never AiDOOS."""

    def __init__(self, cfg: LLMConfig, api_key: str):
        self.cfg = cfg
        self.api_key = api_key

    def enrich(self, capability: Capability, code_context: str) -> Capability:
        from . import _llm_http
        prompt = (f"Capability: {capability.name}\nKind: {capability.kind.value}\n"
                  f"Dependencies: {', '.join(capability.dependencies) or 'none'}\n"
                  f"In one sentence, what does this capability most likely do?")
        try:
            capability.inferred_purpose = _llm_http.chat(
                self.cfg.base_url or "", self.api_key, self.cfg.model or "",
                "You infer the purpose of a software capability in one sentence.", prompt).strip()
        except Exception:
            pass  # enrichment is best-effort; never fail the scan on a model hiccup
        return capability


def get_enricher(cfg: LLMConfig):
    api_key = os.environ.get(cfg.api_key_env)
    if api_key and cfg.model and cfg.base_url:
        return CustomerKeyEnricher(cfg, api_key)
    return NullEnricher()


# ---- universal extraction (Track B) --------------------------------------------------

def universal_extract(product_name: str, files: list[tuple[str, str]],
                      provider=None, budget=None) -> list[CapabilityDraft] | None:
    """Extract capabilities from any language via the configured LLM.

    This is what turns an unparsed stack (PHP, Ruby, Kotlin, ABAP, PL/SQL, X++, ...) from a
    "not read" coverage gap into actual capabilities: with a key, the model reads the code the
    native parsers can't. It uses the SAME provider path as the rest of the tool - the AiDOOS
    key on the hosted free tier, the customer's own key when they bring one, or ANTHROPIC_API_KEY
    locally - so Anthropic-direct works with no base_url (the old self-hosted-endpoint-only gate
    was why this never fired). `budget` is honored so a gap-heavy repo can't run the tier dry.

    Returns drafts when a key is available, else None so the caller falls back to a VISIBLE gap
    capability (never a silent drop, SPEC §4.4).
    """
    if not files:
        return None
    from ..llm_client import ask, available
    if not available(provider):
        return None
    user = f"Product: {product_name}\n\n{_context_from(files)}"
    reply = ask(_EXTRACT_SYSTEM, user, provider=provider, budget=budget)
    if not reply:
        return None                       # no key / exhausted budget / model error -> visible gap
    return parse_capabilities_json(reply) or None

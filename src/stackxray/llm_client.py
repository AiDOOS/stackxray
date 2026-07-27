"""Provider-agnostic LLM access, with an enforceable token budget.

Two ways to configure a provider:
  - LOCAL tool: one env var (or API-KEY.txt next to the launcher) - see provider_from_env().
      ANTHROPIC_API_KEY -> Claude (recommended; this is an AiDOOS tool)
      OPENAI_API_KEY    -> OpenAI-compatible (OPENAI_BASE_URL to override the endpoint)
  - HOSTED tool: the caller passes an explicit Provider (the AiDOOS key for the free tier,
      or the customer's own key when they bring one). No env, no key file.

No provider -> the tool falls back to rule-based reasoning (fully functional).

TokenBudget makes the hosted free tier real: ask() refuses to spend once the cap is hit, so
a scan degrades to the heuristic instead of running up a bill. Actual HTTP lives in
extract/_llm_http.py (the audited egress file).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import NamedTuple

# Fast, cheap models are right for many small per-capability calls.
_DEFAULT_CLAUDE = "claude-haiku-4-5-20251001"
_DEFAULT_OPENAI = "gpt-4o-mini"

_KEY_FILES = ("API-KEY.txt", "stackxray.env", ".env")


class Provider(NamedTuple):
    provider: str            # "anthropic" | "openai"
    model: str
    api_key: str
    base_url: str | None


@dataclass
class TokenBudget:
    """A hard cap on tokens spent in one scan. limit=None means unlimited (BYO key)."""
    limit: int | None = None
    used: int = 0
    calls: int = 0
    _hit: bool = field(default=False, repr=False)

    @property
    def exhausted(self) -> bool:
        return self.limit is not None and self.used >= self.limit

    @property
    def remaining(self) -> int | None:
        return None if self.limit is None else max(0, self.limit - self.used)

    def spend(self, tokens: int) -> None:
        self.used += max(0, int(tokens))
        self.calls += 1
        if self.exhausted:
            self._hit = True

    @property
    def capped(self) -> bool:
        """True if we stopped early because the cap was reached (report can say so)."""
        return self._hit


def _from_key_file() -> dict[str, str]:
    """Read KEY=VALUE lines from a key file next to the launcher (cwd), ignoring comments.
    Lets a non-technical user just paste a key into a text file instead of setting a
    Windows environment variable."""
    out: dict[str, str] = {}
    for name in _KEY_FILES:
        if not os.path.isfile(name):
            continue
        try:
            with open(name, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    out.setdefault(k.strip(), v.strip())
        except OSError:
            pass
        break
    return out


def _get(name: str, file_cfg: dict[str, str]) -> str | None:
    return os.environ.get(name) or file_cfg.get(name)


def provider_from_env() -> Provider | None:
    """Return the Provider from env OR the local key file, or None. (Local tool path.)"""
    cfg = _from_key_file()
    model = _get("STACKXRAY_LLM_MODEL", cfg)
    if _get("ANTHROPIC_API_KEY", cfg):
        return Provider("anthropic", model or _DEFAULT_CLAUDE, _get("ANTHROPIC_API_KEY", cfg), None)
    if _get("OPENAI_API_KEY", cfg):
        base = _get("OPENAI_BASE_URL", cfg) or "https://api.openai.com/v1"
        return Provider("openai", model or _DEFAULT_OPENAI, _get("OPENAI_API_KEY", cfg), base)
    return None


def provider_for_key(api_key: str, model: str | None = None) -> Provider | None:
    """Build a Provider from a raw key (hosted path). Anthropic keys start with 'sk-ant-'."""
    key = (api_key or "").strip()
    if not key:
        return None
    if key.startswith("sk-ant-"):
        return Provider("anthropic", model or _DEFAULT_CLAUDE, key, None)
    return Provider("openai", model or _DEFAULT_OPENAI, key, "https://api.openai.com/v1")


def available(provider: Provider | None = None) -> bool:
    return (provider or provider_from_env()) is not None


def probe(provider: Provider | None = None) -> tuple[bool, str | None]:
    """Make ONE cheap call and report the REAL outcome: (ok, error).

    `ask()` deliberately swallows every error so a scan never dies because of the optional LLM.
    That is right for the hosted free tier, and WRONG for a local run where the customer pasted a
    key and expects it to be used: a rejected key would silently produce the heuristic-only report
    we already rejected, while the footer still claimed the code had been read by their model.
    Probing once turns that silent downgrade into a plain message.
    """
    p = provider or provider_from_env()
    if not p:
        return False, "no API key configured"
    from .extract import _llm_http
    try:
        if p.provider == "anthropic":
            _llm_http.chat_anthropic(p.api_key, p.model, "Reply with OK.", "Say OK.")
        else:
            _llm_http.chat(p.base_url or "", p.api_key, p.model, "Reply with OK.", "Say OK.")
        return True, None
    except Exception as e:
        detail = str(e)
        if "401" in detail or "403" in detail:
            return False, (f"the {p.provider} API rejected the key ({detail.strip()}) - it may be "
                           "expired, revoked, or from a different account")
        return False, f"the {p.provider} API call failed - {type(e).__name__}: {detail.strip()}"


def ask(system: str, user: str, provider: Provider | None = None,
        budget: TokenBudget | None = None) -> str | None:
    """Ask the configured provider; return text, or None on no-key / exhausted budget / any
    error (so the scan never fails because of the optional LLM)."""
    p = provider or provider_from_env()
    if not p:
        return None
    if budget is not None and budget.exhausted:
        return None                       # free tier spent: stop calling, keep the heuristic
    from .extract import _llm_http
    try:
        if p.provider == "anthropic":
            text, tokens = _llm_http.chat_anthropic(p.api_key, p.model, system, user)
        else:
            text, tokens = _llm_http.chat(p.base_url or "", p.api_key, p.model, system, user)
    except Exception:
        return None
    if budget is not None:
        budget.spend(tokens)
    return plain(text)


# Punctuation that models love and this product does not ship. Applied to EVERY model reply at
# the one choke point they all pass through, so an em-dash or a smart quote can never reach the
# report (or a proposal) no matter which pass produced it. Same rule the rest of the tool holds
# to: plain ASCII punctuation, no AI tells.
_PUNCT = {
    "—": "-", "–": "-", "‒": "-", "‐": "-", "‑": "-",  # dashes
    "→": "->", "←": "<-", "’": "'", "‘": "'",
    "“": '"', "”": '"', "…": "...", " ": " ", "•": "-",
    "≤": "<=", "≥": ">=", "×": "x",
}
_PUNCT_TABLE = str.maketrans(_PUNCT)


def plain(text: str | None) -> str | None:
    return text.translate(_PUNCT_TABLE) if text else text

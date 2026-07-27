"""LLM transport - calls a model endpoint (Anthropic or OpenAI-compatible), never AiDOOS.

Isolated here so the trust boundary stays auditable: outbound model HTTP lives only in this
file, and the AiDOOS fingerprint egress lives only in cloud/. The target URL is ALWAYS the
configured provider endpoint - there is no AiDOOS address anywhere in this module.

Both functions return (text, total_tokens). The token count is what makes a metered free
tier possible in the hosted tool: the caller can stop spending before it overruns the cap.
"""

from __future__ import annotations

import json
import urllib.request

_MAX_OUT = 400


def chat(base_url: str, api_key: str, model: str, system: str, user: str,
         timeout: int = 60) -> tuple[str, int]:
    """POST a chat completion to an OpenAI-compatible endpoint.

    base_url MUST be the configured endpoint (e.g. https://api.openai.com/v1 or a
    self-hosted URL). This function never constructs an AiDOOS URL.
    Returns (message_content, total_tokens_used).
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    usage = data.get("usage") or {}
    tokens = int(usage.get("total_tokens")
                 or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)))
    return data["choices"][0]["message"]["content"], tokens


def chat_anthropic(api_key: str, model: str, system: str, user: str,
                   timeout: int = 60) -> tuple[str, int]:
    """Anthropic (Claude) Messages API. Same trust boundary: talks only to Anthropic with
    the supplied key, never to AiDOOS. Returns (text, total_tokens_used)."""
    payload = json.dumps({
        "model": model,
        "max_tokens": _MAX_OUT,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=payload,
                                 method="POST", headers={
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    usage = data.get("usage") or {}
    tokens = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
    return data["content"][0]["text"], tokens

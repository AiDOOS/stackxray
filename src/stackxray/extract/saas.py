"""Integrated-SaaS + AI detection from import/package signatures (SPEC §5b, §10 ai_or_not).

'Integrated' = a SaaS the org built glue to; the SaaS code isn't in the repo but the
integration IS (SDK/API-client imports). We detect those so verdicts apply to them
(consolidate 3 payment SaaS; retire a dead integration). 'Bought' SaaS with no code
footprint is invisible here - that's the v2 consumption lens.

Matching is by SUBSTRING so one table works across languages: Python `import stripe`,
JS `@stripe/stripe-js`, Java `com.stripe`, Go `github.com/stripe/stripe-go` all match
the root token 'stripe'.
"""

from __future__ import annotations

# root token (lowercase) -> vendor label. Curated; extend as real repos surface more.
SAAS_SIGNATURES: dict[str, str] = {
    "stripe": "Stripe",
    "twilio": "Twilio",
    "sendgrid": "SendGrid",
    "boto3": "AWS", "botocore": "AWS", "aws-sdk": "AWS", "@aws-sdk": "AWS",
    "googleapiclient": "Google Cloud", "googleapis": "Google Cloud", "cloud.google": "Google Cloud",
    "azure": "Azure",
    "salesforce": "Salesforce",
    "slack_sdk": "Slack", "@slack": "Slack",
    "razorpay": "Razorpay",
    "paypal": "PayPal",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "cohere": "Cohere",
    "pymongo": "MongoDB", "mongodb": "MongoDB", "mongoose": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "algolia": "Algolia",
}

# Root tokens whose presence marks a capability as AI (SPEC §10 ai_or_not).
AI_SIGNATURES: set[str] = {
    "openai", "anthropic", "cohere", "torch", "tensorflow", "transformers",
    "sklearn", "langchain", "llama_index", "llamaindex", "spacy",
    "sentence_transformers", "generativeai", "vertexai", "huggingface", "onnx",
}


# vendor -> functional category. Two+ DISTINCT vendors in one category across the
# portfolio is the CONSOLIDATE signal ("3 payment SaaS -> stitch to one", SPEC §5b/§8).
VENDOR_CATEGORY: dict[str, str] = {
    "Stripe": "payments", "PayPal": "payments", "Razorpay": "payments",
    "Twilio": "comms", "SendGrid": "comms", "Slack": "comms",
    "OpenAI": "ai-llm", "Anthropic": "ai-llm", "Cohere": "ai-llm",
    "AWS": "cloud", "Google Cloud": "cloud", "Azure": "cloud",
    "MongoDB": "datastore", "Redis": "datastore",
    "Elasticsearch": "search", "Algolia": "search",
}


def _matches(signature: str, imports: set[str]) -> bool:
    """True if the signature token appears as a substring of any import specifier
    (case-insensitive) - cross-language: 'stripe' hits '@stripe/stripe-js', 'com.stripe'."""
    return any(signature in imp for imp in imports)


def detect_saas(imports: set[str]) -> dict[str, str]:
    """Return {vendor_label: token_that_matched} for SaaS SDKs seen in `imports`."""
    low = {imp.lower() for imp in imports}
    found: dict[str, str] = {}
    for token, vendor in SAAS_SIGNATURES.items():
        if _matches(token, low):
            found.setdefault(vendor, token)
    return found


def looks_ai(imports: set[str]) -> bool:
    low = {imp.lower() for imp in imports}
    return any(_matches(sig, low) for sig in AI_SIGNATURES)


def vendor_is_ai(vendor: str) -> bool:
    """Is this SaaS vendor itself an AI provider? (for ai_or_not on integration caps)."""
    return VENDOR_CATEGORY.get(vendor) == "ai-llm"

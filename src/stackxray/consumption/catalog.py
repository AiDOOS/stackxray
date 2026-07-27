"""SaaS vendor catalog for the consumption lens (SPEC §5b).

Maps vendor names + known domains to a functional category, so bought-SaaS can be
normalized (Okta/spend/DNS all name vendors slightly differently) and grouped for
category-redundancy consolidation ("3 BI tools -> pick one"). Extend freely; this is a
lookup table, not logic.
"""

from __future__ import annotations

# vendor (normalized) -> functional category
VENDOR_CATEGORY: dict[str, str] = {
    # analytics / BI
    "Tableau": "analytics-bi", "Looker": "analytics-bi", "Power BI": "analytics-bi",
    "Mode": "analytics-bi", "Metabase": "analytics-bi", "Sisense": "analytics-bi",
    "Amplitude": "product-analytics", "Mixpanel": "product-analytics", "Heap": "product-analytics",
    # design
    "Figma": "design", "Sketch": "design", "Adobe": "design", "InVision": "design",
    # docs / collab
    "Notion": "docs-collab", "Confluence": "docs-collab", "Coda": "docs-collab",
    # comms
    "Slack": "comms", "Zoom": "comms", "Microsoft Teams": "comms", "Google Meet": "comms",
    # crm / marketing
    "Salesforce": "crm", "HubSpot": "crm", "Pipedrive": "crm",
    "Marketo": "marketing", "Mailchimp": "marketing",
    # ticketing / pm
    "Jira": "project-mgmt", "Asana": "project-mgmt", "Monday": "project-mgmt",
    "Linear": "project-mgmt", "Trello": "project-mgmt",
    # support
    "Zendesk": "support", "Intercom": "support", "Freshdesk": "support",
    # observability (bought)
    "Datadog": "observability", "New Relic": "observability", "Dynatrace": "observability",
    # payments (also seen as integrated)
    "Stripe": "payments", "PayPal": "payments",
    # HR / finance
    "Workday": "hr", "BambooHR": "hr", "Gusto": "hr", "NetSuite": "finance", "QuickBooks": "finance",
}

# known SaaS domain -> vendor (for egress/DNS attribution)
DOMAIN_VENDOR: dict[str, str] = {
    "tableau.com": "Tableau", "looker.com": "Looker", "powerbi.com": "Power BI",
    "figma.com": "Figma", "sketch.com": "Sketch", "adobe.com": "Adobe",
    "notion.so": "Notion", "atlassian.net": "Confluence", "coda.io": "Coda",
    "slack.com": "Slack", "zoom.us": "Zoom", "amplitude.com": "Amplitude",
    "mixpanel.com": "Mixpanel", "salesforce.com": "Salesforce", "hubspot.com": "HubSpot",
    "asana.com": "Asana", "monday.com": "Monday", "linear.app": "Linear",
    "zendesk.com": "Zendesk", "intercom.com": "Intercom", "datadoghq.com": "Datadog",
    "workday.com": "Workday", "gusto.com": "Gusto", "netsuite.com": "NetSuite",
}

_ALIASES = {
    "power bi": "Power BI", "powerbi": "Power BI", "ms teams": "Microsoft Teams",
    "teams": "Microsoft Teams", "gsuite": "Google Meet", "adobe cc": "Adobe",
}


def normalize_vendor(name: str) -> str:
    """Best-effort canonical vendor name from a messy export string."""
    raw = (name or "").strip()
    low = raw.lower()
    if low in _ALIASES:
        return _ALIASES[low]
    low = low.replace(", inc.", "").replace(" inc", "").replace(".com", "").strip()
    for known in VENDOR_CATEGORY:
        if low == known.lower():
            return known
    return raw or "Unknown"


def category_of(vendor: str) -> str | None:
    return VENDOR_CATEGORY.get(normalize_vendor(vendor))


def vendor_from_domain(domain: str) -> str | None:
    d = (domain or "").strip().lower().lstrip(".")
    for known_domain, vendor in DOMAIN_VENDOR.items():
        if d == known_domain or d.endswith("." + known_domain):
            return vendor
    return None

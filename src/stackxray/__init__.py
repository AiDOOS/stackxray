"""StackXray - a self-run scanner that maps an org's software capabilities and
gives an honest keep/retire/consolidate/agentify/buy verdict per capability.

Runs entirely inside the customer's environment (SPEC §6). Nothing leaves except, on
explicit consent, an abstract capability fingerprint (SPEC §4/§14.4).

See SPEC.md for the full brief and DESIGN.md for the module map.
"""

__version__ = "0.0.1"  # v1 scaffold

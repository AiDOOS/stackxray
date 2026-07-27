"""Language extractors (Milestone 7). Register a new language by adding it here.

The orchestrator (extract/__init__.py) walks EXTRACTORS to route files by extension.
Native (heuristic, offline, keyless): Python, JS/TS, Java, C#, Go, C/C++, COBOL, RPG.
The LLM universal track (extract/llm.py) covers anything else when a key is present.
"""

from __future__ import annotations

from .apex import ApexExtractor
from .cobol import CobolExtractor
from .cpp import CppExtractor
from .csharp import CSharpExtractor
from .go import GoExtractor
from .java import JavaExtractor
from .javascript import JavaScriptExtractor
from .python import PythonExtractor
from .rpg import RpgExtractor
from .salesforce import SalesforceMetadataExtractor
from .servicenow import ServiceNowExtractor

EXTRACTORS = [
    PythonExtractor(),
    JavaScriptExtractor(),
    JavaExtractor(),
    CSharpExtractor(),
    GoExtractor(),
    CppExtractor(),
    CobolExtractor(),
    RpgExtractor(),
    ApexExtractor(),
    # Not a language: reads Salesforce's metadata (Flows = processes people CONFIGURED rather
    # than coded, custom objects = the org's domain nouns). Filters hard to Salesforce's own
    # `-meta.xml` suffixes so an ordinary repo's pom.xml/config XML is never touched.
    SalesforceMetadataExtractor(),
    # Activates only on ServiceNow record XML (content-sniffed), so it never touches a Java
    # pom.xml or Salesforce metadata. Claiming `.xml` also makes a ServiceNow-only estate
    # (all XML, no code files) DISCOVERABLE as a product.
    ServiceNowExtractor(),
]

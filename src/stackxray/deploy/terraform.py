"""Terraform parsing (SPEC §6 - a PRIMARY portable format) -> DeployLink.

HCL without a parser lib, so regex-based and deliberately coarse: find resource blocks for
known service-ish types, pull a name + image if present, infer cloud from the type prefix.
MEDIUM confidence (a service definition, but no Dockerfile-level code->image proof). VMs
(aws_instance / google_compute_instance) are tagged runtime = vm.
"""

from __future__ import annotations

import os
import re

from ..models import Confidence, DeployLink, Evidence, Runtime
from .clouds import cloud_from_tf_type

# resource type -> runtime kind. Container/serverless services vs bare VMs.
_SERVICE_TYPES = {
    "aws_ecs_service": Runtime.CONTAINER, "aws_ecs_task_definition": Runtime.CONTAINER,
    "google_cloud_run_service": Runtime.CONTAINER, "google_cloud_run_v2_service": Runtime.CONTAINER,
    "azurerm_container_app": Runtime.CONTAINER, "kubernetes_deployment": Runtime.CONTAINER,
    "aws_lambda_function": Runtime.CONTAINER, "google_cloudfunctions_function": Runtime.CONTAINER,
    "aws_instance": Runtime.VM, "google_compute_instance": Runtime.VM,
    "azurerm_linux_virtual_machine": Runtime.VM, "digitalocean_droplet": Runtime.VM,
}

_RESOURCE_RE = re.compile(r'resource\s+"([a-z0-9_]+)"\s+"([a-zA-Z0-9_-]+)"\s*\{', re.IGNORECASE)
_NAME_ATTR = re.compile(r'\b(?:name|function_name|service_name)\s*=\s*"([^"]+)"')
_IMAGE_ATTR = re.compile(r'\b(?:image|image_uri|container_image)\s*=\s*"([^"]+)"')


def _block_body(text: str, open_brace_idx: int) -> str:
    """Return the {...} body starting at open_brace_idx by brace-matching."""
    depth, i = 0, open_brace_idx
    for i in range(open_brace_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_idx:i + 1]
    return text[open_brace_idx:]


def parse_terraform(repo_path: str) -> list[DeployLink]:
    links: list[DeployLink] = []
    for root, _dirs, files in os.walk(repo_path):
        for fname in files:
            if not fname.endswith(".tf"):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            for m in _RESOURCE_RE.finditer(text):
                rtype, rname = m.group(1), m.group(2)
                if rtype not in _SERVICE_TYPES:
                    continue
                body = _block_body(text, text.index("{", m.end() - 1))
                name = (_NAME_ATTR.search(body) or [None, rname])[1] if _NAME_ATTR.search(body) else rname
                image_m = _IMAGE_ATTR.search(body)
                code_unit = rname
                if image_m:
                    ref = image_m.group(1).rsplit("/", 1)[-1]
                    code_unit = ref.rsplit(":", 1)[0] if ":" in ref else ref
                links.append(DeployLink(
                    code_unit=code_unit,
                    service_name=name,
                    confidence=Confidence.MEDIUM,
                    runtime=_SERVICE_TYPES[rtype],
                    cloud_environment=cloud_from_tf_type(rtype),
                    evidence=[Evidence("deploy",
                              f"terraform {rtype}.{rname} -> service '{name}'", locator=path)],
                ))
    return links

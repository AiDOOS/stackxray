"""Deploy/infra config parsing (SPEC §6, §7) - the BRIDGE for the code->runtime join.

Parses portable, multi-cloud formats (k8s, Docker, Terraform, compose) and VM artifacts
(systemd, Ansible) to produce DeployLink records that tie
`code unit -> container/image/service`, each tagged with runtime (container|vm) and an
inferred cloud (§8 cross-cloud). Cloud-specific IaC (CloudFormation, ARM/Bicep, DO App
spec) is added incrementally (SPEC §6).

v1 sources: k8s+Dockerfile (HIGH), Terraform + docker-compose (MEDIUM), systemd/Ansible
VM artifacts (MEDIUM/LOW). Vendor-specific IaC is later.
"""

from __future__ import annotations

import os

import yaml

from ..config import ScanConfig
from ..models import Confidence, DeployLink, Evidence, Runtime
from .clouds import cloud_from_image
from .compose import parse_compose
from .terraform import parse_terraform
from .vm import parse_vm


def _image_basename(image_ref: str) -> str:
    """registry.internal/payment-retry-worker:1.4 -> payment-retry-worker.

    Strips registry host/path and the :tag or @digest, leaving the image name that (by
    convention) matches the code module that builds it.
    """
    ref = image_ref.split("@", 1)[0]                  # drop @sha256:... digest
    last = ref.rsplit("/", 1)[-1]                     # registry/path/name:tag -> name:tag
    name = last.rsplit(":", 1)[0] if ":" in last else last  # drop :tag
    return name


def _find_dockerfile_modules(repo_path: str) -> dict[str, str]:
    """Map module-name -> Dockerfile path for every module that ships a Dockerfile.

    The module name is its directory name - the code->image half of the join (§7). A
    Dockerfile present in a module is what upgrades a name match from MEDIUM to HIGH.
    """
    modules: dict[str, str] = {}
    for root, _dirs, files in os.walk(repo_path):
        for fname in files:
            if fname == "Dockerfile" or fname.endswith(".dockerfile"):
                module = os.path.basename(root.rstrip(os.sep))
                modules[module] = os.path.join(root, fname)
    return modules


def _containers(doc: dict) -> list[dict]:
    """Dig out the container list across the kind-specific pod-spec nesting."""
    spec = doc.get("spec") or {}
    if "jobTemplate" in spec:  # CronJob
        spec = spec["jobTemplate"].get("spec") or {}
    pod_spec = (spec.get("template") or {}).get("spec") or spec  # Deployment/... vs Pod
    containers = pod_spec.get("containers") or []
    return [c for c in containers if isinstance(c, dict)]


def _parse_k8s_services(deploy_dir: str) -> list[tuple[str, str, str, str]]:
    """Return (service_name, container_name, image_ref, manifest_path) per workload.

    Handles Deployment/StatefulSet/DaemonSet/CronJob/Job/Pod and multi-doc YAML files.
    """
    out: list[tuple[str, str, str, str]] = []
    workload_kinds = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"}
    for root, _dirs, files in os.walk(deploy_dir):
        for fname in files:
            if not (fname.endswith(".yaml") or fname.endswith(".yml")):
                continue
            path = os.path.join(root, fname)
            with open(path, "r", encoding="utf-8") as fh:
                docs = list(yaml.safe_load_all(fh))
            for doc in docs:
                if not isinstance(doc, dict) or doc.get("kind") not in workload_kinds:
                    continue
                service = (doc.get("metadata") or {}).get("name")
                for container in _containers(doc):
                    image = container.get("image")
                    if service and image:
                        out.append((service, container.get("name", ""), image, path))
    return out


def parse_deploy_links(config: ScanConfig) -> list[DeployLink]:
    """Return code-unit -> deployed-service links with per-link confidence (§8.3).

    Signal ordering (locked §8.3):
      Dockerfile + k8s image match        -> HIGH
      k8s image name match, no Dockerfile -> LOW (name-similarity only)
    Terraform / VM artifacts (systemd, Ansible) -> next; MEDIUM/LOW tiers.
    """
    dockerfile_modules = _find_dockerfile_modules(config.repo_path)
    links: list[DeployLink] = []

    # k8s + Dockerfile - the HIGH-confidence container path (§8.3)
    for service, container_name, image_ref, manifest in _parse_k8s_services(config.repo_path):
        image_name = _image_basename(image_ref)
        evidence = [Evidence(
            source="deploy",
            detail=f"k8s workload '{service}' runs image '{image_ref}' (container '{container_name}')",
            locator=manifest,
        )]

        if image_name in dockerfile_modules:
            confidence = Confidence.HIGH
            evidence.append(Evidence(
                source="deploy",
                detail=f"module '{image_name}' builds this image (Dockerfile present)",
                locator=dockerfile_modules[image_name],
            ))
        else:
            confidence = Confidence.LOW  # image name matched no Dockerfile module

        links.append(DeployLink(
            code_unit=image_name,
            service_name=service,
            confidence=confidence,
            runtime=Runtime.CONTAINER,
            cloud_environment=cloud_from_image(image_ref),
            evidence=evidence,
        ))

    # Terraform + docker-compose (MEDIUM) and VM artifacts (MEDIUM/LOW)
    links += parse_terraform(config.repo_path)
    links += parse_compose(config.repo_path)
    links += parse_vm(config.repo_path)
    return links

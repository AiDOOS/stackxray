"""docker-compose parsing (SPEC §6) -> DeployLink (MEDIUM confidence).

A compose service ties `build context (code) -> image -> service name`. Less authoritative
than a k8s manifest + Dockerfile match, so MEDIUM. runtime = container.
"""

from __future__ import annotations

import os

import yaml

from ..models import Confidence, DeployLink, Evidence, Runtime
from .clouds import cloud_from_image

_COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")


def _code_unit(service_name: str, svc: dict, compose_dir: str) -> str:
    build = svc.get("build")
    if isinstance(build, str):
        return os.path.basename(os.path.normpath(os.path.join(compose_dir, build)))
    if isinstance(build, dict) and build.get("context"):
        return os.path.basename(os.path.normpath(os.path.join(compose_dir, build["context"])))
    if svc.get("image"):
        ref = svc["image"].rsplit("/", 1)[-1]
        return ref.rsplit(":", 1)[0] if ":" in ref else ref
    return service_name


def parse_compose(repo_path: str) -> list[DeployLink]:
    links: list[DeployLink] = []
    for root, _dirs, files in os.walk(repo_path):
        for fname in files:
            if fname not in _COMPOSE_NAMES:
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    doc = yaml.safe_load(fh)
            except Exception:
                continue
            services = (doc or {}).get("services") or {}
            for svc_name, svc in services.items():
                if not isinstance(svc, dict):
                    continue
                image = svc.get("image", "")
                links.append(DeployLink(
                    code_unit=_code_unit(svc_name, svc, root),
                    service_name=svc_name,
                    confidence=Confidence.MEDIUM,
                    runtime=Runtime.CONTAINER,
                    cloud_environment=cloud_from_image(image),
                    evidence=[Evidence("deploy",
                              f"compose service '{svc_name}'"
                              + (f" (image '{image}')" if image else " (build context)"),
                              locator=path)],
                ))
    return links

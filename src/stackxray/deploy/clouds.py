"""Cloud/deployment-environment inference (SPEC §8, §10) - enables cross-cloud detection.

Cloud is rarely stated outright, so we infer it from signals that ARE in the configs: the
container image registry host, and the Terraform/IaC resource-type prefix. This is what
lets the map tag each capability's cloud and surface the same capability running on GCP
*and* DigitalOcean (the §8 cross-cloud consolidation differentiator).
"""

from __future__ import annotations

# registry host substring -> cloud
_REGISTRY_CLOUD = {
    "gcr.io": "gcp", "pkg.dev": "gcp", ".run.app": "gcp",
    ".dkr.ecr.": "aws", "public.ecr.aws": "aws", "amazonaws.com": "aws",
    ".azurecr.io": "azure", "azure": "azure",
    "registry.digitalocean.com": "digitalocean", "digitaloceanspaces": "digitalocean",
    "registry.gitlab.com": None,  # host-agnostic; leave unknown
}

# terraform/iac resource-type prefix -> cloud
_TF_PREFIX_CLOUD = {
    "aws_": "aws", "google_": "gcp", "azurerm_": "azure", "azuread_": "azure",
    "digitalocean_": "digitalocean", "oci_": "oracle", "linode_": "linode",
}


def cloud_from_image(image_ref: str) -> str | None:
    ref = (image_ref or "").lower()
    for host, cloud in _REGISTRY_CLOUD.items():
        if host in ref:
            return cloud
    return None


def cloud_from_tf_type(resource_type: str) -> str | None:
    rt = (resource_type or "").lower()
    for prefix, cloud in _TF_PREFIX_CLOUD.items():
        if rt.startswith(prefix):
            return cloud
    return None

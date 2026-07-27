"""VM provisioning/service artifacts (SPEC §6, §7) -> DeployLink (runtime = vm).

The VM equivalent of the code->service bridge: systemd unit files and Ansible service tasks
name the services running on a box. The join is messier here than on containers (no image
to tie code to), so confidence is MEDIUM at best and LOW when we can only guess the code
unit - stated honestly (§7 'Reality': the biggest retire wins hide on VMs, lower confidence).
"""

from __future__ import annotations

import os
import re

import yaml

from ..models import Confidence, DeployLink, Evidence, Runtime

_EXECSTART_RE = re.compile(r"^\s*ExecStart\s*=\s*(.+)$", re.MULTILINE)


def _code_unit_from_execstart(line: str) -> str | None:
    """/usr/bin/python3 /opt/pay-retry/worker.py -> pay-retry (dir) or worker (script)."""
    tokens = [t for t in line.split() if not t.startswith("-")]
    for tok in tokens:
        base = os.path.basename(tok)
        if base in ("python", "python3", "java", "node", "sh", "bash", "/usr/bin/env", "env"):
            continue
        # prefer the parent dir name of a script (usually the service/module), else the binary
        parent = os.path.basename(os.path.dirname(tok))
        if parent and parent not in ("bin", "usr", "opt", "local", "sbin"):
            return parent
        return base.rsplit(".", 1)[0]
    return None


def _parse_systemd(repo_path: str) -> list[DeployLink]:
    links: list[DeployLink] = []
    for root, _dirs, files in os.walk(repo_path):
        for fname in files:
            if not fname.endswith(".service"):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            service = fname[: -len(".service")]
            m = _EXECSTART_RE.search(text)
            code_unit = _code_unit_from_execstart(m.group(1)) if m else None
            links.append(DeployLink(
                code_unit=code_unit or service,
                service_name=service,
                confidence=Confidence.MEDIUM if code_unit else Confidence.LOW,
                runtime=Runtime.VM,
                evidence=[Evidence("deploy",
                          f"systemd unit '{service}'"
                          + (f" starts '{code_unit}'" if code_unit else " (code unit unresolved)"),
                          locator=path)],
            ))
    return links


def _parse_ansible(repo_path: str) -> list[DeployLink]:
    """Ansible tasks using the systemd/service module name a managed service (LOW-MEDIUM)."""
    links: list[DeployLink] = []
    for root, _dirs, files in os.walk(repo_path):
        if "ansible" not in root.lower() and "playbook" not in " ".join(files).lower():
            # cheap filter: only look where ansible plausibly lives
            if not any(f in ("playbook.yml", "site.yml") or "playbook" in f for f in files):
                continue
        for fname in files:
            if not (fname.endswith(".yml") or fname.endswith(".yaml")):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    docs = list(yaml.safe_load_all(fh))
            except Exception:
                continue
            for doc in docs:
                for task in _iter_tasks(doc):
                    mod = task.get("systemd") or task.get("service") or task.get("ansible.builtin.systemd")
                    if isinstance(mod, dict) and mod.get("name"):
                        svc = str(mod["name"])
                        links.append(DeployLink(
                            code_unit=svc, service_name=svc, confidence=Confidence.LOW,
                            runtime=Runtime.VM,
                            evidence=[Evidence("deploy", f"ansible manages service '{svc}'", locator=path)],
                        ))
    return links


def _iter_tasks(doc):
    if isinstance(doc, list):
        for item in doc:
            if isinstance(item, dict):
                yield from (item.get("tasks") or [])
                if "service" in item or "systemd" in item:
                    yield item


def parse_vm(repo_path: str) -> list[DeployLink]:
    return _parse_systemd(repo_path) + _parse_ansible(repo_path)

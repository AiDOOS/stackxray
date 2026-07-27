"""Safety boundary for the HOSTED tool (aidoos.com/StackXray).

The local tool trusted its input: the user pointed at their own folder. The hosted tool does
not - the repo URL and the uploaded zip are attacker-controlled. Everything that turns
untrusted input into a directory on disk lives here, so the boundary stays auditable.

Threats handled:
  - SSRF via clone URL      -> scheme + host allowlist, no userinfo, DNS resolved and every
                               resolved IP checked against private/loopback/link-local ranges
  - Credential prompts      -> GIT_TERMINAL_PROMPT=0, no askpass, hard timeout
  - Zip slip (../, absolute) -> every member path resolved and confined to the destination
  - Zip symlink escape      -> symlink members rejected outright
  - Zip bomb                -> caps on member count, per-member size, total size, and ratio
  - Oversized repos         -> byte + file-count caps enforced after clone

Note: the scan engine only PARSES source, it never imports or executes it, so a hostile
repo cannot run code here. These caps are about resource exhaustion and path escape.
"""

from __future__ import annotations

import ipaddress
import os
import shutil
import socket
import subprocess
import zipfile
from urllib.parse import urlparse

# --- caps ------------------------------------------------------------------------------
MAX_UPLOAD_BYTES = 100 * 1024 * 1024        # the zip itself
MAX_LOG_BYTES = 200 * 1024 * 1024           # access logs (they get big; .gz is fine)
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # sum of members
MAX_MEMBER_BYTES = 50 * 1024 * 1024         # any single member
MAX_FILES = 50_000
MAX_RATIO = 200                             # per-member compression ratio (zip bomb)
CLONE_TIMEOUT = 300                         # seconds
MAX_REPO_BYTES = 500 * 1024 * 1024

ALLOWED_HOSTS = {"github.com", "www.github.com", "gitlab.com", "www.gitlab.com",
                 "bitbucket.org", "www.bitbucket.org"}


class UnsafeSource(ValueError):
    """The supplied repo URL or archive is not something we are willing to fetch/unpack."""


class AuthRequired(UnsafeSource):
    """The repo exists but we could not read it without credentials (private, or the URL is
    wrong - GitHub returns the same 404 for both). The UI turns this into a just-in-time
    'connect / paste a token' prompt rather than a hard failure, so the user never has to
    declare up front whether their repo is public or private."""


# git stderr fragments that mean "we could not authenticate" (prompts are disabled, so a
# private repo fails immediately rather than hanging on a username prompt).
_AUTH_HINTS = (
    "could not read username", "authentication failed", "terminal prompts disabled",
    "invalid username or password", "repository not found", "not found",
    "403", "permission denied", "please make sure you have the correct access rights",
)


# --- clone URL -------------------------------------------------------------------------
def _ip_is_public(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
                or a.is_multicast or a.is_unspecified)


def validate_clone_url(url: str) -> str:
    """Return a normalized https clone URL, or raise UnsafeSource.

    Blocks: non-https schemes (ssh/file/git), embedded credentials, hosts outside the
    allowlist, and any host whose DNS resolves to a private/loopback address (SSRF into
    our own network, e.g. http://169.254.169.254 metadata or an internal git server).
    """
    url = (url or "").strip()
    if not url:
        raise UnsafeSource("No repository URL supplied.")
    parts = urlparse(url)
    if parts.scheme != "https":
        raise UnsafeSource("Only https:// repository URLs are supported.")
    if parts.username or parts.password or "@" in (parts.netloc.split(":")[0] or ""):
        raise UnsafeSource("Remove credentials from the URL; connect the repo instead.")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise UnsafeSource(f"Unsupported host '{host}'. Use GitHub, GitLab, or Bitbucket.")
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise UnsafeSource(f"Could not resolve '{host}'.")
    for info in infos:
        ip = info[4][0]
        if not _ip_is_public(ip):
            raise UnsafeSource(f"'{host}' resolves to a non-public address.")
    if not parts.path.strip("/"):
        raise UnsafeSource("That URL has no repository path.")
    return url


def clone(url: str, dest: str, token: str | None = None) -> None:
    """Shallow-clone a validated URL into dest. Never prompts; hard timeout.

    `token` (private repos) is injected via an http.extraheader argument rather than the
    URL, so it cannot leak into the remote's stored config or into error text we surface.
    """
    url = validate_clone_url(url)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", GCM_INTERACTIVE="never")
    cmd = ["git"]
    if token:
        import base64
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        cmd += ["-c", f"http.extraheader=Authorization: Basic {basic}"]
    cmd += ["clone", "--depth", "1", "--single-branch", "--no-tags", url, dest]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=CLONE_TIMEOUT, env=env)
    except FileNotFoundError:
        raise UnsafeSource("git is not installed on the server.")
    except subprocess.TimeoutExpired:
        shutil.rmtree(dest, ignore_errors=True)
        raise UnsafeSource("Cloning timed out. That repository is too large to scan here.")
    except subprocess.CalledProcessError as e:
        shutil.rmtree(dest, ignore_errors=True)
        stderr = (e.stderr.decode(errors="replace") if e.stderr else "")
        tail = stderr[-200:]
        if token:
            tail = tail.replace(token, "***")
        looks_auth = any(h in stderr.lower() for h in _AUTH_HINTS)
        if looks_auth and not token:
            # Private (or wrong URL) and we had no credential: ask for access, don't fail.
            raise AuthRequired(
                "This repository is private, or the URL isn't quite right. Connect GitHub or "
                "paste a read-only token to let StackXray in.")
        if looks_auth and token:
            raise UnsafeSource(
                "That token didn't grant access to this repository. Check it's read-only and "
                "scoped to this repo, then try again.")
        raise UnsafeSource(f"Could not clone that repository (check the URL / access). {tail}")
    enforce_tree_caps(dest)


# --- zip upload ------------------------------------------------------------------------
def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return (info.external_attr >> 16) & 0o170000 == 0o120000


def safe_extract_zip(zip_path: str, dest: str) -> None:
    """Extract an untrusted zip into dest, refusing anything that escapes or explodes."""
    if os.path.getsize(zip_path) > MAX_UPLOAD_BYTES:
        raise UnsafeSource("That archive is larger than the 100 MB upload limit.")
    dest_real = os.path.realpath(dest)
    total = 0
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise UnsafeSource("That file is not a valid .zip archive.")
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES:
            raise UnsafeSource(f"That archive has more than {MAX_FILES:,} files.")
        for info in infos:
            if _is_symlink(info):
                raise UnsafeSource(f"Archive contains a symlink ({info.filename}).")
            name = info.filename
            if name.startswith("/") or name.startswith("\\") or ":" in name.split("/")[0]:
                raise UnsafeSource(f"Archive contains an absolute path ({name}).")
            target = os.path.realpath(os.path.join(dest_real, name))
            if target != dest_real and not target.startswith(dest_real + os.sep):
                raise UnsafeSource(f"Archive tries to write outside the folder ({name}).")
            if info.file_size > MAX_MEMBER_BYTES:
                raise UnsafeSource(f"Archive contains an oversized file ({name}).")
            if info.compress_size and info.file_size / max(1, info.compress_size) > MAX_RATIO:
                raise UnsafeSource(f"Archive looks like a zip bomb ({name}).")
            total += info.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise UnsafeSource("That archive expands beyond the 500 MB limit.")
        zf.extractall(dest_real)


# --- tree caps -------------------------------------------------------------------------
def enforce_tree_caps(path: str) -> None:
    """Refuse a tree that is too big to scan (bytes or file count)."""
    total = files = 0
    for root, dirs, names in os.walk(path):
        if ".git" in dirs:
            dirs.remove(".git")
        for n in names:
            files += 1
            if files > MAX_FILES:
                raise UnsafeSource(f"That codebase has more than {MAX_FILES:,} files.")
            try:
                total += os.path.getsize(os.path.join(root, n))
            except OSError:
                pass
            if total > MAX_REPO_BYTES:
                raise UnsafeSource("That codebase is larger than the 500 MB scan limit.")

"""
updater.py — Check for newer cc-notify releases on GitHub.

SSL note: urllib's default HTTPS context can fail in a PyInstaller bundle on
Windows because the bundle does not carry the system certificate store.
certifi ships the Mozilla CA bundle as a plain file, so it works reliably
regardless of the deployment environment.
"""
from __future__ import annotations

import json
import logging
import ssl
import urllib.request
from typing import Optional

from version import __version__

logger = logging.getLogger(__name__)

_REPO        = "Decent-Cypher/ai-notification"
_API_URL     = f"https://api.github.com/repos/{_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{_REPO}/releases"


def _ssl_context() -> ssl.SSLContext:
    """
    Return an SSL context backed by certifi's CA bundle.

    In a PyInstaller bundle urllib's default context may fail certificate
    verification because the bundle does not include the Windows cert store.
    certifi provides a self-contained Mozilla CA bundle that works in any
    deployment environment, including frozen executables.
    """
    import certifi
    return ssl.create_default_context(cafile=certifi.where())


def _parse_semver(tag: str) -> tuple[int, ...]:
    """'v0.1.2' → (0, 1, 2). Returns (0,) on any parse failure."""
    try:
        return tuple(int(x) for x in tag.lstrip("v").split("."))
    except ValueError:
        return (0,)


def latest_release_tag() -> str:
    """
    Query GitHub for the latest non-draft, non-prerelease tag.

    Raises an exception on any network or parse error so the caller can
    surface the specific failure reason to the user.
    """
    req = urllib.request.Request(
        _API_URL,
        headers={"User-Agent": f"cc-notify/{__version__}"},
    )
    with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    tag = data.get("tag_name", "").strip()
    logger.debug("Latest release tag from GitHub: %s", tag or "(none)")
    if not tag:
        raise ValueError("GitHub response contained no tag_name field")
    return tag


def check_for_update() -> tuple[bool, Optional[str], Optional[str]]:
    """
    Compare the running version against the latest GitHub release.

    Returns a 3-tuple:
        (True,  latest_tag, None)       — a newer version is available
        (False, latest_tag, None)       — already on the latest version
        (False, None,       error_msg)  — check failed; error_msg describes why
    """
    try:
        tag = latest_release_tag()
    except Exception as exc:
        error = str(exc)
        logger.warning("Update check failed: %s", error)
        return False, None, error

    available = _parse_semver(tag) > _parse_semver(__version__)
    logger.info(
        "Update check: running=%s latest=%s available=%s",
        __version__, tag, available,
    )
    return available, tag, None

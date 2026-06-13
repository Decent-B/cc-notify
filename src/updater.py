"""
updater.py — Check for newer cc-notify releases on GitHub.

Uses only the Python standard library (urllib, json) so no extra dependency
is needed and the module works reliably inside a PyInstaller bundle.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Optional

from version import __version__

logger = logging.getLogger(__name__)

_REPO        = "Decent-Cypher/ai-notification"
_API_URL     = f"https://api.github.com/repos/{_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{_REPO}/releases"


def _parse_semver(tag: str) -> tuple[int, ...]:
    """'v0.1.2' → (0, 1, 2). Returns (0,) on any parse failure."""
    try:
        return tuple(int(x) for x in tag.lstrip("v").split("."))
    except ValueError:
        return (0,)


def latest_release_tag() -> Optional[str]:
    """
    Query GitHub for the latest non-draft, non-prerelease tag.
    Returns the tag string (e.g. 'v0.1.2'), or None on any error.
    """
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={"User-Agent": f"cc-notify/{__version__}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "").strip()
        logger.debug("Latest release tag from GitHub: %s", tag or "(none)")
        return tag if tag else None
    except Exception as exc:
        logger.warning("Update check network error: %s", exc)
        return None


def check_for_update() -> tuple[bool, Optional[str]]:
    """
    Compare the running version against the latest GitHub release.

    Returns:
        (True,  latest_tag) — a newer version is available
        (False, latest_tag) — already on the latest version
        (False, None)       — check failed (network error, parse error, etc.)
    """
    tag = latest_release_tag()
    if tag is None:
        return False, None
    available = _parse_semver(tag) > _parse_semver(__version__)
    logger.info(
        "Update check: running=%s latest=%s available=%s",
        __version__, tag, available,
    )
    return available, tag

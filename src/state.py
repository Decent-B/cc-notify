"""
Persistent runtime state for cc-notify.

Tracks which version last successfully configured Claude Code hooks so that
auto-setup can be skipped on normal restarts and re-triggered automatically
after a version upgrade or a clean install.

Also holds the per-install webhook authentication token, which is generated
once and embedded in the hook URL so the server can reject unsolicited requests.

State is stored in %APPDATA%/cc-notify/state.json alongside config.json.
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Optional

from config import CONFIG_DIR

logger = logging.getLogger(__name__)

_STATE_PATH = CONFIG_DIR / "state.json"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _read_state() -> dict:
    if not _STATE_PATH.exists():
        return {}
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read state file %s: %s", _STATE_PATH, exc)
        return {}


def _write_state(data: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write state file %s: %s", _STATE_PATH, exc)


# ── Hook version tracking ─────────────────────────────────────────────────────

def get_hooks_version() -> Optional[str]:
    """
    Return the version that last successfully configured Claude Code hooks,
    or None if hooks have never been configured (fresh install).
    """
    return _read_state().get("hooks_configured_for_version")


def set_hooks_version(version: str) -> None:
    """
    Record that hooks were successfully configured for *version*.
    Merges into any existing state so unrelated keys are preserved.
    """
    data = _read_state()
    data["hooks_configured_for_version"] = version
    _write_state(data)
    logger.debug("State updated: hooks_configured_for_version=%s", version)


# ── Webhook authentication token ──────────────────────────────────────────────

def get_webhook_token() -> Optional[str]:
    """Return the stored webhook token, or None if it has not been generated yet."""
    return _read_state().get("webhook_token")


def ensure_webhook_token() -> str:
    """
    Return the existing per-install webhook token, generating and persisting
    a new one if none exists.

    The token is a 256-bit cryptographically random hex string.  It is embedded
    in the hook URL written to Claude Code's settings.json so that the server
    can reject requests that do not carry the correct token.

    Call this once from the main thread before starting any background threads,
    so all later callers can use get_webhook_token() without a generation race.
    """
    data = _read_state()
    token: Optional[str] = data.get("webhook_token")
    if token:
        return token

    token = secrets.token_hex(32)  # 256 bits of entropy
    data["webhook_token"] = token
    _write_state(data)
    logger.info("Generated new webhook token (stored in %s)", _STATE_PATH)
    return token

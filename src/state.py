"""
Persistent runtime state for cc-notify.

Tracks which version last successfully configured Claude Code hooks so that
auto-setup can be skipped on normal restarts and re-triggered automatically
after a version upgrade or a clean install.

State is stored in %APPDATA%/cc-notify/state.json alongside config.json.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from config import CONFIG_DIR

logger = logging.getLogger(__name__)

_STATE_PATH = CONFIG_DIR / "state.json"


def get_hooks_version() -> Optional[str]:
    """
    Return the version that last successfully configured Claude Code hooks,
    or None if hooks have never been configured (fresh install).
    """
    if not _STATE_PATH.exists():
        return None
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        return data.get("hooks_configured_for_version")
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read state file %s: %s", _STATE_PATH, exc)
        return None


def set_hooks_version(version: str) -> None:
    """
    Record that hooks were successfully configured for *version*.
    Merges into any existing state so unrelated keys are preserved.
    """
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if _STATE_PATH.exists():
            try:
                data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass  # start fresh if the file is corrupt
        data["hooks_configured_for_version"] = version
        _STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("State updated: hooks_configured_for_version=%s", version)
    except OSError as exc:
        logger.warning("Could not write state file %s: %s", _STATE_PATH, exc)

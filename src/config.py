"""
Configuration management for cc-notify.

Settings are persisted to %APPDATA%/cc-notify/config.json so they survive
restarts and are writable without admin privileges.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

_APPDATA = Path(os.environ.get("APPDATA", Path.home()))
CONFIG_DIR = _APPDATA / "cc-notify"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_PORT = 9876


@dataclass
class Config:
    # Port the webhook HTTP server listens on.
    port: int = DEFAULT_PORT

    # Whether to play a sound with each notification.
    sound_enabled: bool = True

    # Which Claude Code events trigger a notification.
    notify_on_stop: bool = True
    notify_on_stop_failure: bool = True
    notify_on_permission: bool = True
    notify_on_idle: bool = True

    @classmethod
    def load(cls) -> "Config":
        """Load config from disk, falling back to defaults on any error."""
        if not CONFIG_PATH.exists():
            return cls()
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            known = cls.__dataclass_fields__
            return cls(**{k: v for k, v in data.items() if k in known})
        except (json.JSONDecodeError, TypeError, ValueError):
            return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

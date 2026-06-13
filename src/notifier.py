"""
Windows toast notification wrapper.

Abstracts win11toast so the rest of the app deals only with high-level
event types (permission, idle, stop, generic). All calls are fire-and-forget;
errors are logged but never propagated — a broken notification must not
take down the webhook server.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# WinRT system sound events used per notification type.
_SOUNDS: dict[str, str] = {
    "permission": "ms-winsoundevent:Notification.Looping.Alarm2",
    "idle":       "ms-winsoundevent:Notification.Default",
    "stop":       "ms-winsoundevent:Notification.Default",
    "generic":    "ms-winsoundevent:Notification.Default",
}


def _send(title: str, body: str, sound_key: str, sound_enabled: bool) -> None:
    """Dispatch a single toast notification. Swallows all exceptions."""
    try:
        from win11toast import notify  # imported lazily — not available outside Windows

        kwargs: dict = {}
        if sound_enabled:
            kwargs["audio"] = {"src": _SOUNDS.get(sound_key, _SOUNDS["generic"])}

        notify(title, body, **kwargs)
        logger.debug("Notification sent: %s — %s", title, body)
    except Exception as exc:
        logger.warning("Failed to send notification: %s", exc)


def permission(message: str, sound_enabled: bool = True) -> None:
    """Claude Code is paused waiting for the user to approve an action."""
    body = message or "Claude Code is waiting for your approval to proceed."
    _send("Claude Code — Permission Required", body, "permission", sound_enabled)


def idle(message: str, sound_enabled: bool = True) -> None:
    """Claude Code is idle and waiting for the user to respond."""
    body = message or "Claude Code is waiting for your response."
    _send("Claude Code — Waiting for Input", body, "idle", sound_enabled)


def stop(sound_enabled: bool = True) -> None:
    """Claude Code has finished generating a response."""
    _send("Claude Code — Task Complete", "Claude has finished responding.", "stop", sound_enabled)


def generic(title: str, message: str, sound_enabled: bool = True) -> None:
    """Fallback for any other Claude Code notification type."""
    _send(title or "Claude Code", message, "generic", sound_enabled)


def update_available(current: str, latest: str, releases_url: str, sound_enabled: bool = True) -> None:
    """
    Notify that a newer release is available.

    The toast is clickable — clicking it opens releases_url in the browser.
    on_click is handled directly here because the shared _send helper does
    not expose that parameter (no other notification type needs it).
    """
    try:
        from win11toast import notify

        kwargs: dict = {}
        if sound_enabled:
            kwargs["audio"] = {"src": _SOUNDS["generic"]}

        notify(
            "cc-notify — Update Available",
            f"Version {latest} is available. You have {current}. Click to download.",
            on_click=releases_url,
            **kwargs,
        )
        logger.debug("Update notification sent: %s → %s", current, latest)
    except Exception as exc:
        logger.warning("Failed to send update notification: %s", exc)

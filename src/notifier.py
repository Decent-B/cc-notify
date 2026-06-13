"""
Windows toast notification wrapper.

Abstracts win11toast so the rest of the app deals only with high-level
event types (permission, idle, stop, generic). All calls are fire-and-forget;
errors are logged but never propagated — a broken notification must not
take down the webhook server.
"""
from __future__ import annotations

import logging
import os.path
import shlex

logger = logging.getLogger(__name__)

# WinRT system sound events used per notification type.
_SOUNDS: dict[str, str] = {
    "permission": "ms-winsoundevent:Notification.Looping.Alarm2",
    "idle":       "ms-winsoundevent:Notification.Default",
    "stop":       "ms-winsoundevent:Notification.Default",
    "generic":    "ms-winsoundevent:Notification.Default",
}


def _vscode_launcher(cwd: str):
    """
    Return an on_click callable that opens VS Code at cwd, or None if cwd is
    empty or does not look like an absolute filesystem path.

    Clicking the toast runs `code <cwd>`.  Two path styles are handled:

      Windows path (e.g. C:\\Users\\...):
        subprocess.Popen(["code", "--", cwd]) — the "--" sentinel tells the
        VS Code CLI that the following argument is a path, not a flag.  This
        prevents a crafted cwd value like "--inspect" from being interpreted
        as a CLI option.

      WSL2 Linux path (e.g. /home/user/project):
        wsl.exe runs `code <cwd>` inside the distro so VS Code opens with
        the Remote WSL extension active for that folder.  shlex.quote handles
        shell-safe quoting so path characters cannot escape the argument.

    Only absolute paths pass the os.path.isabs() guard, so values that begin
    with "--" or are otherwise not filesystem paths are silently ignored.
    """
    # Reject empty or non-absolute values — legitimate Claude Code cwd fields
    # are always absolute paths (e.g. "C:\projects\foo" or "/home/user/foo").
    if not cwd or not os.path.isabs(cwd):
        return None

    def _launch(args=None):
        import subprocess
        try:
            if cwd.startswith("/"):
                # Linux/WSL2 path — delegate to the distro's `code` binary so
                # VS Code opens as a Remote WSL session for this folder.
                subprocess.Popen(
                    ["wsl.exe", "--", "bash", "-c", f"code {shlex.quote(cwd)}"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                # "--" separates options from positional arguments, ensuring cwd
                # is treated as a path even if it begins with a hyphen.
                subprocess.Popen(
                    ["code", "--", cwd],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            logger.debug("Opened VS Code at: %s", cwd)
        except Exception as exc:
            logger.warning("Failed to open VS Code at %r: %s", cwd, exc)

    return _launch


def _send(
    title: str,
    body: str,
    sound_key: str,
    sound_enabled: bool,
    on_click=None,
) -> None:
    """Dispatch a single toast notification. Swallows all exceptions."""
    try:
        from win11toast import notify  # imported lazily — not available outside Windows

        kwargs: dict = {}
        if sound_enabled:
            kwargs["audio"] = {"src": _SOUNDS.get(sound_key, _SOUNDS["generic"])}
        if on_click is not None:
            kwargs["on_click"] = on_click

        notify(title, body, **kwargs)
        logger.debug("Notification sent: %s", title)
    except Exception as exc:
        logger.warning("Failed to send notification: %s", exc)


def permission(message: str, sound_enabled: bool = True, cwd: str = "") -> None:
    """Claude Code is paused waiting for the user to approve an action."""
    body = message or "Claude Code is waiting for your approval to proceed."
    _send(
        "Claude Code — Permission Required", body, "permission", sound_enabled,
        on_click=_vscode_launcher(cwd),
    )


def idle(message: str, sound_enabled: bool = True, cwd: str = "") -> None:
    """Claude Code is idle and waiting for the user to respond."""
    body = message or "Claude Code is waiting for your response."
    _send(
        "Claude Code — Waiting for Input", body, "idle", sound_enabled,
        on_click=_vscode_launcher(cwd),
    )


def stop(sound_enabled: bool = True, cwd: str = "") -> None:
    """Claude Code has finished generating a response."""
    _send(
        "Claude Code — Task Complete", "Claude has finished responding.", "stop", sound_enabled,
        on_click=_vscode_launcher(cwd),
    )


def generic(title: str, message: str, sound_enabled: bool = True) -> None:
    """Fallback for any other Claude Code notification type. No VS Code focus."""
    _send(title or "Claude Code", message, "generic", sound_enabled)


def update_available(current: str, latest: str, releases_url: str, sound_enabled: bool = True) -> None:
    """
    Notify that a newer release is available.

    The toast is clickable — clicking it opens releases_url in the browser.
    on_click is a URL string here (not a callable) because the target is a
    browser page, not VS Code.
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
        logger.debug("Update notification sent: %s -> %s", current, latest)
    except Exception as exc:
        logger.warning("Failed to send update notification: %s", exc)

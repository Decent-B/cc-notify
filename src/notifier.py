"""
Windows toast notification wrapper.

Abstracts win11toast so the rest of the app deals only with high-level
event types (permission, idle, stop, generic). All calls are fire-and-forget;
errors are logged but never propagated — a broken notification must not
take down the webhook server.

VS Code focus on click
  Toast notifications that carry a cwd field use a vscode:// URI as the
  on_click value (not a Python callable). When on_click is a string, win11toast
  writes it as the toast XML <toast launch="..."> attribute, so Windows
  delivers the URI directly to VS Code's registered protocol handler on click —
  including when the toast is clicked from Action Center after it has timed out.

  A Python callable on_click is unreliable in this scenario: win11toast
  dispatches it via asyncio call_soon_threadsafe(), but by the time a
  timed-out toast is clicked from Action Center the asyncio future is already
  resolved and the activation event is silently discarded.

  Using a URI also avoids the foreground-focus chain problem:
    wsl.exe → bash → code → SetForegroundWindow
  Windows foreground rights expire (~200 ms) long before VS Code receives the
  IPC message through that chain. A URI activation via the Windows shell lets
  the shell grant foreground rights to VS Code directly.
"""
from __future__ import annotations

import logging
import os.path
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)

# WinRT system sound events used per notification type.
_SOUNDS: dict[str, str] = {
    "permission": "ms-winsoundevent:Notification.Looping.Alarm2",
    "idle":       "ms-winsoundevent:Notification.Default",
    "stop":       "ms-winsoundevent:Notification.Default",
    "generic":    "ms-winsoundevent:Notification.Default",
}

# Cached after first detection — wsl.exe is called at most once per session.
_wsl2_default_distro: Optional[str] = None


def _get_default_wsl2_distro() -> Optional[str]:
    """
    Return the name of the default WSL2 distro (e.g. "Ubuntu-24.04").

    The result is cached after the first successful call so subsequent
    notifications pay no subprocess overhead.  Returns None if WSL2 is
    unavailable or detection fails — callers should handle this gracefully.
    """
    global _wsl2_default_distro
    if _wsl2_default_distro is not None:
        return _wsl2_default_distro

    import subprocess
    try:
        result = subprocess.run(
            ["wsl.exe", "--list", "--quiet"],
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return None

        # WSL2 outputs UTF-16 LE on most Windows versions; fall back to UTF-8.
        try:
            text = result.stdout.decode("utf-16-le")
        except UnicodeDecodeError:
            text = result.stdout.decode("utf-8", errors="ignore")

        for line in text.splitlines():
            name = line.strip().replace("\x00", "")
            if name:
                _wsl2_default_distro = name
                logger.debug("Detected default WSL2 distro: %s", name)
                return name
    except Exception as exc:
        logger.debug("Could not detect WSL2 distro: %s", exc)
    return None


def _vscode_uri(cwd: str) -> Optional[str]:
    """
    Build a vscode:// URI for opening VS Code at cwd, or return None.

    URI formats:
      WSL2 path  (starts with /):  vscode://vscode-remote/wsl+<distro><path>
      Windows path (drive letter): vscode://file/<forward-slash path>

    The URI is percent-encoded so that spaces and special characters in the
    path are transmitted correctly to VS Code's URI handler.

    Only absolute paths pass the os.path.isabs() guard.  Values that start
    with "--" or are not filesystem paths are rejected, preventing a crafted
    cwd payload from reaching VS Code as a CLI flag.

    Returns None when the URI cannot be constructed (empty cwd, non-absolute
    path, or WSL2 not available for a Linux path).
    """
    if not cwd or not os.path.isabs(cwd):
        return None

    if cwd.startswith("/"):
        # WSL2/Linux path — use the vscode-remote URI scheme so VS Code opens
        # the folder as a proper Remote-WSL session.  The distro name forms part
        # of the authority component, e.g. wsl+Ubuntu-24.04.
        distro = _get_default_wsl2_distro()
        if not distro:
            logger.warning(
                "Cannot build VS Code URI for WSL2 path: distro not detected. "
                "Ensure WSL2 is installed and at least one distro is running."
            )
            return None
        # Encode the path component (spaces → %20 etc.) but keep slashes as-is.
        encoded_path = urllib.parse.quote(cwd, safe="/")
        # Encode the distro name in case it contains unusual characters.
        encoded_distro = urllib.parse.quote(distro, safe="")
        return f"vscode://vscode-remote/wsl+{encoded_distro}{encoded_path}"
    else:
        # Windows absolute path — use the vscode://file/ scheme.
        # Convert backslashes to forward slashes; keep the colon after the
        # drive letter (e.g. C:/Users/...).
        forward = cwd.replace("\\", "/")
        encoded = urllib.parse.quote(forward, safe=":/")
        return f"vscode://file/{encoded}"


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
        on_click=_vscode_uri(cwd),
    )


def idle(message: str, sound_enabled: bool = True, cwd: str = "") -> None:
    """Claude Code is idle and waiting for the user to respond."""
    body = message or "Claude Code is waiting for your response."
    _send(
        "Claude Code — Waiting for Input", body, "idle", sound_enabled,
        on_click=_vscode_uri(cwd),
    )


def stop(sound_enabled: bool = True, cwd: str = "") -> None:
    """Claude Code has finished generating a response."""
    _send(
        "Claude Code — Task Complete", "Claude has finished responding.", "stop", sound_enabled,
        on_click=_vscode_uri(cwd),
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

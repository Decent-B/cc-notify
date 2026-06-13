"""
System tray icon using pystray.

Provides a persistent tray presence so the user can see that cc-notify is
running and exit cleanly.  pystray must run in the main thread on Windows,
so this module is always called from main() — the HTTP server runs in a
daemon thread behind it.
"""
from __future__ import annotations

import logging
import sys
import threading
import webbrowser
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)

_GITHUB_URL = "https://github.com/Decent-B/cc-notify"

# The running tray icon — set inside run_tray() so trigger_install_update()
# can stop it cleanly from a background thread.
_icon: Optional[object] = None


# ── Icon ──────────────────────────────────────────────────────────────────────

def _build_icon_image():
    """
    Create the tray icon at runtime using Pillow.
    Returns a 64×64 RGBA PIL Image: a purple circle with a white bell.
    """
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background — Anthropic purple
    draw.ellipse([2, 2, 62, 62], fill=(134, 94, 212, 255))

    # Bell body (white rounded rectangle)
    draw.rounded_rectangle([20, 24, 44, 44], radius=5, fill=(255, 255, 255, 230))

    # Bell arch (semicircle on top)
    draw.pieslice([18, 14, 46, 38], start=180, end=0, fill=(255, 255, 255, 230))

    # Clapper dot at bottom
    draw.ellipse([28, 43, 36, 51], fill=(255, 255, 255, 230))

    # Stem at top centre
    draw.rectangle([30, 10, 34, 18], fill=(255, 255, 255, 200))

    return img


# ── Background tasks (each runs in a daemon thread) ───────────────────────────

def _run_update_check(config: "Config") -> None:
    """
    Query GitHub for the latest release and notify the user of the result.
    Stores a pending ReleaseInfo when an update is found so the tray menu can
    offer a one-click install item.  Runs on a daemon thread.
    """
    import notifier
    from updater import INSTALL_URI, fetch_latest_release, set_pending_release
    from version import __version__

    try:
        release = fetch_latest_release()
        if release:
            set_pending_release(release)
            notifier.update_available(
                __version__, release.tag, INSTALL_URI,
                sound_enabled=config.sound_enabled,
            )
        else:
            notifier.generic(
                "cc-notify — Up to Date",
                f"You are running the latest version ({__version__}).",
                sound_enabled=False,
            )
    except Exception as exc:
        logger.error("Update check crashed: %s", exc, exc_info=True)
        try:
            import notifier as _n
            _n.generic(
                "cc-notify — Update Check Failed",
                str(exc),
                sound_enabled=False,
            )
        except Exception:
            pass


def _run_hook_setup(config: "Config", *, auto: bool = False) -> None:
    """
    Detect available environments and configure Claude Code hooks in all of them.

    Shows a "working" toast immediately, then a result toast when finished.
    Runs on a daemon thread so it never blocks the tray event loop.

    When auto=True the working toast mentions that setup is running automatically
    (first launch or post-update), so the user knows they didn't trigger it.
    """
    import notifier
    import state
    from hooks_setup import setup_all
    from version import __version__

    try:
        if auto:
            notifier.generic(
                "cc-notify — Configuring hooks…",
                "Setting up Claude Code hooks automatically.",
                sound_enabled=False,
            )
        else:
            notifier.generic(
                "cc-notify — Setting up hooks…",
                "Detecting environments, please wait.",
                sound_enabled=False,
            )

        result = setup_all(config.port)

        # Persist the configured version so future launches skip auto-setup.
        # Save as long as the Windows side succeeded — WSL2 is a secondary target
        # and its failure should not cause the app to re-run setup every launch.
        if result.windows_ok:
            state.set_hooks_version(__version__)

        if result.fully_ok:
            notifier.generic(
                "Hooks configured — Restart Claude Code",
                result.summary(),
                sound_enabled=config.sound_enabled,
            )
        else:
            notifier.generic(
                "Hook setup completed with issues",
                result.summary(),
                sound_enabled=config.sound_enabled,
            )

    except Exception as exc:
        logger.error("Hook setup crashed: %s", exc, exc_info=True)
        try:
            import notifier as _n
            _n.generic("Hook setup failed", str(exc), sound_enabled=config.sound_enabled)
        except Exception:
            pass


def _run_install_update(config: "Config") -> None:
    """
    Download and apply the pending release, then stop the tray so the process
    exits and the PowerShell helper script can swap the EXE.
    """
    import notifier
    from updater import apply_update, get_pending_release

    release = get_pending_release()
    if not release:
        logger.warning("No pending release to install")
        return

    def notify_fn(title: str, body: str) -> None:
        notifier.generic(title, body, sound_enabled=False)

    def stop_icon_fn() -> None:
        if _icon is not None:
            _icon.stop()  # type: ignore[attr-defined]

    apply_update(release, notify_fn=notify_fn, stop_icon_fn=stop_icon_fn)


def maybe_run_auto_setup(config: "Config") -> None:
    """
    Trigger hook setup in a background thread if this version has not yet
    configured hooks — covers both fresh installs and post-update launches.

    Silently skips if the stored configured version already matches __version__,
    so normal restarts incur no overhead.
    """
    import state
    from version import __version__

    configured = state.get_hooks_version()
    if configured == __version__:
        return  # already configured for this version — nothing to do

    logger.info(
        "Auto hook setup: current version=%s, last configured=%s",
        __version__, configured or "(never)",
    )
    threading.Thread(
        target=_run_hook_setup,
        args=(config,),
        kwargs={"auto": True},
        daemon=True,
        name="auto-hook-setup",
    ).start()


def trigger_install_update(config: "Config") -> None:
    """
    Start the update install in a daemon thread.  Called from the tray menu
    or from the /do-update server endpoint.  Safe to call from any thread.
    """
    threading.Thread(
        target=_run_install_update,
        args=(config,),
        daemon=True,
        name="install-update",
    ).start()


# ── Tray ──────────────────────────────────────────────────────────────────────

def run_tray(config: "Config") -> None:
    """
    Start the system tray icon.  Blocks until the user selects Exit or the
    icon is stopped programmatically (e.g. by the self-update flow).
    Must be called from the main thread.
    """
    import pystray
    global _icon

    icon_image = _build_icon_image()

    def on_setup_hooks(icon, item):
        threading.Thread(
            target=_run_hook_setup,
            args=(config,),
            daemon=True,
            name="hook-setup",
        ).start()

    def on_check_updates(icon, item):
        threading.Thread(
            target=_run_update_check,
            args=(config,),
            daemon=True,
            name="update-check",
        ).start()

    def on_install_update(icon, item):
        trigger_install_update(config)

    def on_open_github(icon, item):
        webbrowser.open(_GITHUB_URL)

    def on_exit(icon, item):
        logger.info("Exit requested from tray menu")
        icon.stop()
        sys.exit(0)

    def _build_menu():
        from updater import get_pending_release
        items = [
            pystray.MenuItem("Claude Code Notifier", None, enabled=False),
            pystray.MenuItem(f"Listening on :{config.port}", None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]
        pending = get_pending_release()
        if pending:
            items.append(pystray.MenuItem(f"Install Update {pending.tag}", on_install_update))
            items.append(pystray.Menu.SEPARATOR)
        items += [
            pystray.MenuItem("Setup Claude Code Hooks…", on_setup_hooks),
            pystray.MenuItem("Check for Updates", on_check_updates),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open GitHub", on_open_github),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", on_exit),
        ]
        return items

    menu = pystray.Menu(_build_menu)

    icon = pystray.Icon(
        name="cc-notify",
        icon=icon_image,
        title=f"Claude Code Notifier  |  :{config.port}",
        menu=menu,
    )
    _icon = icon

    def _make_visible(icon):
        icon.visible = True

    # setup= runs in a background thread once the icon is ready.
    icon.run(setup=_make_visible)

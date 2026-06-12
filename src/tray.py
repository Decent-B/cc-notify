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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)

_GITHUB_URL = "https://github.com/Decent-Cypher/ai-notification"


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


# ── Hook setup (runs in a background thread) ──────────────────────────────────

def _run_hook_setup(config: "Config") -> None:
    """
    Detect available environments and configure Claude Code hooks in all of them.

    Shows a "working" toast immediately, then a result toast when finished.
    Runs on a daemon thread so it never blocks the tray event loop.
    """
    import notifier
    from hooks_setup import setup_all

    try:
        notifier.generic(
            "cc-notify — Setting up hooks…",
            "Detecting environments, please wait.",
            sound_enabled=False,
        )

        result = setup_all(config.port)

        if result.fully_ok:
            notifier.generic(
                "Hooks configured! Restart Claude Code.",
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


# ── Tray ──────────────────────────────────────────────────────────────────────

def run_tray(config: "Config") -> None:
    """
    Start the system tray icon.  Blocks until the user selects Exit.
    Must be called from the main thread.
    """
    import pystray

    icon_image = _build_icon_image()

    def on_setup_hooks(icon, item):
        # Spawn a daemon thread so WSL2 subprocess calls don't stall the tray.
        threading.Thread(
            target=_run_hook_setup,
            args=(config,),
            daemon=True,
            name="hook-setup",
        ).start()

    def on_open_github(icon, item):
        webbrowser.open(_GITHUB_URL)

    def on_exit(icon, item):
        logger.info("Exit requested from tray menu")
        icon.stop()
        sys.exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Claude Code Notifier", None, enabled=False),
        pystray.MenuItem(f"Listening on :{config.port}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Setup Claude Code Hooks…", on_setup_hooks),
        pystray.MenuItem("Open GitHub", on_open_github),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_exit),
    )

    icon = pystray.Icon(
        name="cc-notify",
        icon=icon_image,
        title=f"Claude Code Notifier  |  :{config.port}",
        menu=menu,
    )

    def _make_visible(icon):
        icon.visible = True

    # setup= runs in a background thread once the icon is ready.
    icon.run(setup=_make_visible)

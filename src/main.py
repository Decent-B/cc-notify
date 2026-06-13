"""
cc-notify — Claude Code Windows Notifier
Entry point for the PyInstaller-bundled tray application.

Startup sequence:
  1. Load config from %APPDATA%/cc-notify/config.json
  2. Ensure the per-install webhook token exists in state.json
  3. Check the webhook port is free (single-instance guard)
  4. Start the Waitress WSGI server on 127.0.0.1 in a daemon thread
  5. Auto-configure Claude Code hooks if this version hasn't done so yet
     (first install or post-update launch) — runs in a background thread
  6. Hand control to the pystray tray icon (blocks until Exit)
"""
from __future__ import annotations

import logging
import socket
import sys
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cc-notify")


def _port_in_use(port: int) -> bool:
    """Return True if something is already listening on the port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _start_server(app, host: str, port: int) -> None:
    """Run the Waitress WSGI server (called inside a daemon thread)."""
    from waitress import serve
    logger.info("Webhook server listening on %s:%d", host, port)
    serve(app, host=host, port=port, threads=4)


def main() -> None:
    from config import Config
    from server import create_app
    from state import ensure_webhook_token
    from tray import maybe_run_auto_setup, run_tray

    config = Config.load()

    # Generate the per-install token before any background threads start so
    # there is no race between generation (main thread) and reads (other threads).
    webhook_token = ensure_webhook_token()

    if _port_in_use(config.port):
        logger.error(
            "Port %d is already in use — another cc-notify instance may be running.",
            config.port,
        )
        try:
            # Best-effort: show a toast before exiting so the user knows why
            # the tray icon didn't appear.
            from win11toast import notify
            notify(
                "cc-notify — Already Running",
                f"Port {config.port} is busy. Only one instance can run at a time.",
            )
        except Exception:
            pass
        sys.exit(1)

    app = create_app(config, webhook_token)

    server_thread = threading.Thread(
        # Bind only to the loopback interface.  Claude Code on native Windows and
        # inside WSL2 both reach this via localhost (WSL2 localhost forwarding is
        # on by default).  Binding to 0.0.0.0 would expose the port to every host
        # on the LAN, which is unnecessary and increases the attack surface.
        target=_start_server,
        args=(app, "127.0.0.1", config.port),
        daemon=True,
        name="webhook-server",
    )
    server_thread.start()

    # Run hook setup in the background if this version hasn't configured it yet.
    # The check is near-instant on normal restarts; setup only runs on first
    # launch or after an update, and never blocks the tray from appearing.
    maybe_run_auto_setup(config)

    # Block the main thread in the tray icon loop.
    run_tray(config)


if __name__ == "__main__":
    main()

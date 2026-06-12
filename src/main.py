"""
cc-notify — Claude Code Windows Notifier
Entry point for the PyInstaller-bundled tray application.

Startup sequence:
  1. Load config from %APPDATA%/cc-notify/config.json
  2. Check the webhook port is free (single-instance guard)
  3. Start the Waitress WSGI server in a daemon thread
  4. Hand control to the pystray tray icon (blocks until Exit)
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
    from tray import run_tray

    config = Config.load()

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

    app = create_app(config)

    server_thread = threading.Thread(
        target=_start_server,
        args=(app, "0.0.0.0", config.port),
        daemon=True,
        name="webhook-server",
    )
    server_thread.start()

    # Block the main thread in the tray icon loop.
    run_tray(config)


if __name__ == "__main__":
    main()

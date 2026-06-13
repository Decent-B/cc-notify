"""
cc-notify — Claude Code Windows Notifier
Entry point for the PyInstaller-bundled tray application.

Normal startup sequence:
  1. Load config from %APPDATA%/cc-notify/config.json
  2. Ensure the per-install webhook token exists in state.json
  3. Check the webhook port is free (single-instance guard)
  4. Start the Waitress WSGI server on 127.0.0.1 in a daemon thread
  5. Auto-configure Claude Code hooks if this version hasn't done so yet
     (first install or post-update launch) — runs in a background thread
  6. Hand control to the pystray tray icon (blocks until Exit)

Protocol handler mode (cc-notify:// URI):
  When Windows activates the app via the cc-notify:// URI scheme (i.e. the
  user clicked an update toast), the process receives the URI as argv[1].
  In that case the startup sequence above is skipped entirely — the process
  reads the stored token, sends GET /do-update to the running instance, and
  exits immediately.
"""
from __future__ import annotations

import logging
import socket
import sys
import threading
import time

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


def _handle_protocol_uri(uri: str) -> None:
    """
    Handle a cc-notify:// URI activation.

    Reads the stored webhook token and port, sends GET /do-update to the
    running tray instance, then exits.  This process is intentionally
    short-lived — its only job is to signal the running instance.
    """
    import json
    import os
    import urllib.error
    import urllib.request
    from pathlib import Path

    appdata = Path(os.environ.get("APPDATA", Path.home()))
    config_dir = appdata / "cc-notify"

    try:
        port = json.loads(
            (config_dir / "config.json").read_text(encoding="utf-8")
        ).get("port", 9876)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        port = 9876

    try:
        state = json.loads(
            (config_dir / "state.json").read_text(encoding="utf-8")
        )
        token = state.get("webhook_token", "")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        token = ""

    if not token:
        logger.warning("Protocol handler: no webhook token found in state.json")
        sys.exit(1)

    url = f"http://127.0.0.1:{port}/do-update?token={token}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            logger.debug("Protocol handler: /do-update response %d", resp.status)
    except urllib.error.HTTPError as exc:
        logger.warning("Protocol handler: /do-update returned HTTP %d", exc.code)
    except Exception as exc:
        logger.warning("Protocol handler: could not reach running instance: %s", exc)

    sys.exit(0)


def main() -> None:
    # Handle cc-notify:// URI activations before normal startup.
    # Windows passes the full URI (e.g. cc-notify://install) as argv[1].
    if len(sys.argv) > 1 and sys.argv[1].startswith("cc-notify://"):
        _handle_protocol_uri(sys.argv[1])
        return

    from config import Config
    from server import create_app
    from state import ensure_webhook_token
    from tray import maybe_run_auto_setup, run_tray, trigger_install_update

    config = Config.load()

    # Generate the per-install token before any background threads start so
    # there is no race between generation (main thread) and reads (other threads).
    webhook_token = ensure_webhook_token()

    # Allow a brief grace period for post-update restarts: the PowerShell
    # helper script starts the new EXE immediately after the old process dies,
    # and the OS may not have released the socket by then.  Retry for up to
    # three seconds before concluding a real conflict exists.
    for _attempt in range(4):
        if not _port_in_use(config.port):
            break
        if _attempt == 0:
            logger.info("Port %d in use, waiting for it to be released…", config.port)
        time.sleep(1)
    else:
        logger.error(
            "Port %d is still in use — another cc-notify instance may be running.",
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

    app = create_app(
        config,
        webhook_token,
        on_do_update=lambda: trigger_install_update(config),
    )

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

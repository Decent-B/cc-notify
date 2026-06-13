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
  When Windows activates the app via the cc-notify:// URI scheme the process
  receives the URI as argv[1] and exits immediately after handling it; the
  normal startup sequence is skipped entirely.

  cc-notify://install
    Reads the stored token and port, sends GET /do-update to the running
    instance to trigger the self-update flow.

  cc-notify://focus?uri=<encoded-vscode-uri>
    Activates the VS Code window using SetForegroundWindow while this process
    still holds the foreground activation rights granted by Windows shell.
    On Windows 11 this switches the active virtual desktop when VS Code is on
    a different one.  The decoded vscode:// URI is then dispatched via the
    Windows shell for navigation.
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


# ── Protocol handler helpers ──────────────────────────────────────────────────

def _activate_vscode() -> None:
    """
    Find the topmost VS Code window and bring it to the foreground.

    Must be called from a process that holds foreground activation rights —
    a process just started by Windows shell via a URI scheme activation
    qualifies.  On Windows 11, SetForegroundWindow with those rights also
    switches the active virtual desktop when the target window is on a
    different one.
    """
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    found = [None]

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )

    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if "Visual Studio Code" in buf.value:
            found[0] = hwnd
            return False  # stop at the first (topmost Z-order) match
        return True

    user32.EnumWindows(WNDENUMPROC(_cb), 0)

    if found[0]:
        user32.ShowWindow(found[0], 9)        # SW_RESTORE: un-minimise if needed
        user32.SetForegroundWindow(found[0])
        logger.debug("Activated VS Code window hwnd=%d", found[0])
    else:
        logger.debug("No VS Code window found to activate")


def _handle_install_uri() -> None:
    """Signal the running tray instance to apply the pending update."""
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
        state_data = json.loads(
            (config_dir / "state.json").read_text(encoding="utf-8")
        )
        token = state_data.get("webhook_token", "")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        token = ""

    if not token:
        logger.warning("Protocol handler: no webhook token found in state.json")
        return

    url = f"http://127.0.0.1:{port}/do-update?token={token}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            logger.debug("Protocol handler: /do-update response %d", resp.status)
    except urllib.error.HTTPError as exc:
        logger.warning("Protocol handler: /do-update returned HTTP %d", exc.code)
    except Exception as exc:
        logger.warning("Protocol handler: could not reach running instance: %s", exc)


def _handle_focus_uri(uri: str) -> None:
    """
    Activate VS Code's window (switching virtual desktops if needed), then
    dispatch the embedded vscode:// URI for workspace navigation.

    The vscode:// target is percent-encoded in the uri query string as the
    'uri' parameter.  parse_qs decodes it automatically before forwarding.
    """
    import subprocess
    import urllib.parse

    parsed = urllib.parse.urlparse(uri)
    params = urllib.parse.parse_qs(parsed.query)
    vscode_uri = params.get("uri", [""])[0]  # parse_qs URL-decodes values

    # Activate VS Code before dispatching the URI so our foreground rights
    # are used for SetForegroundWindow, not VS Code's IPC forwarding path.
    _activate_vscode()

    if vscode_uri.startswith("vscode://"):
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", vscode_uri],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )


def _handle_protocol_uri(uri: str) -> None:
    """
    Dispatch a cc-notify:// URI activation to the appropriate handler,
    then exit.  This process is always ephemeral in protocol handler mode.
    """
    if uri.startswith("cc-notify://install"):
        _handle_install_uri()
    elif uri.startswith("cc-notify://focus"):
        _handle_focus_uri(uri)
    else:
        logger.warning("Protocol handler: unrecognised URI %r", uri)
    sys.exit(0)


# ── Normal startup ────────────────────────────────────────────────────────────

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

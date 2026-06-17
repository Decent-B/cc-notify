"""
Webhook HTTP server.

Receives POST /webhook from Claude Code hooks and dispatches the appropriate
Windows toast notification. All hook calls are fire-and-forget (async: true in
settings.json), so the server always returns 200 immediately — Claude Code does
not wait for the response.

Authentication
  Every request to /webhook and GET /do-update must carry the per-install
  secret token as a query parameter: ?token=<value>
  The token is generated at first launch, stored in state.json, and embedded
  in the hook URL written to Claude Code's settings.json during setup.
  Requests without a valid token are rejected with 403 before any processing.

Claude Code hook payload reference:
  https://docs.anthropic.com/en/docs/claude-code/hooks
"""
from __future__ import annotations

import hmac
import logging
from typing import TYPE_CHECKING, Callable, Optional

from flask import Flask, jsonify, request

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)


def create_app(
    config: "Config",
    webhook_token: str,
    on_do_update: Optional[Callable[[], None]] = None,
) -> Flask:
    """
    Build the Flask application.

    webhook_token  — the per-install secret every /webhook and /do-update
        request must supply as ?token=<value>.
    on_do_update   — optional callback invoked by GET /do-update to trigger
        the self-update flow in the tray process.
    """
    app = Flask(__name__, instance_relative_config=False)
    # Suppress Flask's startup banner and per-request logging in the tray app.
    import logging as _logging
    _logging.getLogger("werkzeug").setLevel(_logging.ERROR)

    @app.before_request
    def _authenticate():
        # /health is intentionally unauthenticated — pre-push check scripts
        # and basic monitoring probe it without needing the secret token.
        if request.endpoint not in ("webhook", "do_update"):
            return
        provided = request.args.get("token", "")
        # hmac.compare_digest performs a constant-time comparison so an attacker
        # cannot infer the correct token from response-timing differences.
        if not provided or not hmac.compare_digest(provided, webhook_token):
            logger.warning(
                "Rejected /%s request with invalid or missing token "
                "(remote_addr=%s)", request.endpoint, request.remote_addr,
            )
            return jsonify({"error": "unauthorized"}), 403

    @app.post("/webhook")
    def webhook():
        payload: dict = request.get_json(silent=True) or {}
        event: str             = payload.get("hook_event_name", "")
        notification_type: str = payload.get("notification_type", "")
        message: str           = payload.get("message", "")
        title: str             = payload.get("title", "")
        # cwd is included in every Claude Code hook payload and used as the
        # click target so toasts open VS Code in the relevant project folder.
        cwd: str               = payload.get("cwd", "")

        logger.debug("hook received: event=%s type=%s cwd=%s", event, notification_type, cwd)
        _dispatch(config, event, notification_type, title, message, cwd, payload)

        # Return empty 200; Claude Code ignores the body for async hooks.
        return jsonify({}), 200

    @app.get("/do-update")
    def do_update():
        """
        Trigger the self-update flow in the running tray process.

        Called by the short-lived protocol-handler process that is launched
        when the user clicks a cc-notify:// URI on an update toast.  The
        response is immediate; the actual download and restart happen in a
        background thread spawned by on_do_update.
        """
        if on_do_update:
            on_do_update()
        return jsonify({"status": "ok"}), 200

    @app.get("/health")
    def health():
        """Simple liveness check — curl http://localhost:9876/health."""
        return jsonify({"status": "ok", "port": config.port})

    return app


def _dispatch(
    config: "Config",
    event: str,
    notification_type: str,
    title: str,
    message: str,
    cwd: str,
    payload: dict,
) -> None:
    """Route a Claude Code hook event to the correct notifier function."""
    import notifier

    if event == "Notification":
        if notification_type == "permission_prompt" and config.notify_on_permission:
            notifier.permission(message, config.sound_enabled, cwd=cwd)

        elif notification_type == "idle_prompt" and config.notify_on_idle:
            notifier.idle(message, config.sound_enabled, cwd=cwd)

        elif notification_type in ("auth_success", "elicitation_dialog", "elicitation_complete"):
            # Low-priority status updates — only send if a message is provided.
            # No VS Code focus for these; they don't require user interaction.
            if message:
                notifier.generic(title or "Claude Code", message, config.sound_enabled)

    elif event == "Stop" and config.notify_on_stop:
        notifier.stop(config.sound_enabled, cwd=cwd)

    elif event == "StopFailure" and config.notify_on_stop_failure:
        # stop_reason carries the error category (rate_limit, server_error, etc.)
        # and is used to choose a descriptive title for the toast.
        stop_reason: str = payload.get("stop_reason", "")
        notifier.stop_failure(stop_reason, config.sound_enabled, cwd=cwd)

    elif event == "PermissionRequest" and config.notify_on_permission:
        # PermissionRequest carries the tool name and input, giving more detail
        # than the generic Notification[permission_prompt] message.
        tool = payload.get("tool_name", "a tool")
        notifier.permission(
            f"{tool} is requesting permission. Switch to Claude Code to approve or deny.",
            config.sound_enabled,
            cwd=cwd,
        )

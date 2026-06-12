"""
Webhook HTTP server.

Receives POST /webhook from Claude Code hooks and dispatches the appropriate
Windows toast notification. All hook calls are fire-and-forget (async: true in
settings.json), so the server always returns 200 immediately — Claude Code does
not wait for the response.

Claude Code hook payload reference:
  https://docs.anthropic.com/en/docs/claude-code/hooks
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flask import Flask, jsonify, request

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)


def create_app(config: "Config") -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    # Suppress Flask's startup banner and per-request logging in the tray app.
    import logging as _logging
    _logging.getLogger("werkzeug").setLevel(_logging.ERROR)

    @app.post("/webhook")
    def webhook():
        payload: dict = request.get_json(silent=True) or {}
        event: str = payload.get("hook_event_name", "")
        notification_type: str = payload.get("notification_type", "")
        message: str = payload.get("message", "")
        title: str = payload.get("title", "")

        logger.debug("hook received: event=%s type=%s", event, notification_type)
        _dispatch(config, event, notification_type, title, message, payload)

        # Return empty 200; Claude Code ignores the body for async hooks.
        return jsonify({}), 200

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
    payload: dict,
) -> None:
    """Route a Claude Code hook event to the correct notifier function."""
    import notifier

    if event == "Notification":
        if notification_type == "permission_prompt" and config.notify_on_permission:
            notifier.permission(message, config.sound_enabled)

        elif notification_type == "idle_prompt" and config.notify_on_idle:
            notifier.idle(message, config.sound_enabled)

        elif notification_type in ("auth_success", "elicitation_dialog", "elicitation_complete"):
            # Low-priority status updates — only send if a message is provided.
            if message:
                notifier.generic(title or "Claude Code", message, config.sound_enabled)

    elif event == "Stop" and config.notify_on_stop:
        notifier.stop(config.sound_enabled)

    elif event == "PermissionRequest" and config.notify_on_permission:
        # PermissionRequest carries the tool name and input, giving more detail
        # than the generic Notification[permission_prompt] message.
        tool = payload.get("tool_name", "a tool")
        notifier.permission(
            f"{tool} is requesting permission. Switch to Claude Code to approve or deny.",
            config.sound_enabled,
        )

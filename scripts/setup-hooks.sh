#!/usr/bin/env bash
# setup-hooks.sh — Configure Claude Code hooks from inside WSL2.
#
# Run this script from WITHIN your WSL2 distro after cc-notify.exe is running
# on the Windows side. It writes the webhook URL (including the auth token)
# into ~/.claude/settings.json.
#
# The preferred setup method is the in-app "Setup Claude Code Hooks…" tray
# menu item, which handles the token automatically. Use this script only for
# additional WSL2 distros that the app did not configure automatically.
#
# Token retrieval
#   The auth token is read from cc-notify's state file in Windows APPDATA.
#   If that read fails, set CC_NOTIFY_TOKEN explicitly:
#     CC_NOTIFY_TOKEN=<token> bash scripts/setup-hooks.sh
#   The token value can be found in %APPDATA%\cc-notify\state.json on Windows.
#
# Webhook host strategy
#   WSL2 forwards localhost connections from inside the distro to the Windows
#   host by default (localhostForwarding = true in .wslconfig, the factory
#   default). So 'localhost' is used unless CC_NOTIFY_HOST is set.
#   If you have disabled localhost forwarding, override the host:
#     CC_NOTIFY_HOST=$(awk '/^nameserver/{print $2}' /etc/resolv.conf)
#
# Usage:
#   bash scripts/setup-hooks.sh                # localhost:9876, auto token
#   CC_NOTIFY_PORT=9999 bash setup-hooks.sh    # custom port
#   CC_NOTIFY_HOST=172.20.0.1 bash setup-hooks.sh  # explicit Windows host IP
#   CC_NOTIFY_TOKEN=abc123 bash setup-hooks.sh # explicit token
#   bash setup-hooks.sh --dry-run              # print config without writing

set -euo pipefail

PORT="${CC_NOTIFY_PORT:-9876}"
DRY_RUN=false

for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
done

SETTINGS="$HOME/.claude/settings.json"

# ── Determine webhook host ─────────────────────────────────────────────────────

if [[ -n "${CC_NOTIFY_HOST:-}" ]]; then
  HOST="$CC_NOTIFY_HOST"
  echo "Host (CC_NOTIFY_HOST): $HOST"
elif grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
  HOST="localhost"
  echo "WSL2 detected. Using localhost (WSL2 localhost forwarding)."
  echo "If toasts do not appear, set CC_NOTIFY_HOST to your Windows host IP:"
  echo "  CC_NOTIFY_HOST=\$(awk '/^nameserver/{print \$2}' /etc/resolv.conf)"
else
  HOST="localhost"
  echo "Native Linux detected. Using localhost."
fi

# ── Retrieve the webhook auth token ───────────────────────────────────────────

if [[ -n "${CC_NOTIFY_TOKEN:-}" ]]; then
  TOKEN="$CC_NOTIFY_TOKEN"
  echo "Token: using CC_NOTIFY_TOKEN env var"
else
  # Attempt to read the token from the Windows state.json via PowerShell.
  # This only works inside WSL2 where powershell.exe is reachable.
  TOKEN=""
  if command -v powershell.exe &>/dev/null; then
    RAW_PATH="$(powershell.exe -NoProfile -Command \
      'Write-Output "$env:APPDATA\cc-notify\state.json"' 2>/dev/null | tr -d '\r\n')" || true
    if [[ -n "$RAW_PATH" ]]; then
      WSL_PATH="$(wslpath "$RAW_PATH" 2>/dev/null)" || true
      if [[ -f "${WSL_PATH:-}" ]]; then
        TOKEN="$(python3 -c "
import json, sys
try:
    d = json.load(open('$WSL_PATH', encoding='utf-8'))
    print(d.get('webhook_token', ''), end='')
except Exception:
    pass
" 2>/dev/null)" || true
      fi
    fi
  fi

  if [[ -n "$TOKEN" ]]; then
    echo "Token: read from Windows state.json"
  else
    echo ""
    echo "ERROR: Could not read the webhook token from cc-notify's state file."
    echo "       Start cc-notify.exe first (it generates the token on launch),"
    echo "       then use the in-app 'Setup Claude Code Hooks...' menu item, or"
    echo "       pass the token explicitly:"
    echo "         CC_NOTIFY_TOKEN=<value> bash scripts/setup-hooks.sh"
    echo "       The token is in %APPDATA%\\cc-notify\\state.json on Windows."
    exit 1
  fi
fi

WEBHOOK_URL="http://${HOST}:${PORT}/webhook?token=${TOKEN}"
echo "Webhook URL: http://${HOST}:${PORT}/webhook?token=<redacted>"
echo "Settings   : $SETTINGS"

if $DRY_RUN; then
  echo ""
  echo "[dry-run] Would write the above URL to: $SETTINGS"
  echo "[dry-run] No files were modified."
  exit 0
fi

# ── Merge into settings.json using Python (avoids jq dependency) ──────────────

mkdir -p "$(dirname "$SETTINGS")"

python3 - "$SETTINGS" "$WEBHOOK_URL" <<'PYEOF'
import json, os, sys

settings_path = sys.argv[1]
webhook_url   = sys.argv[2]

print(f"target: {settings_path}")
# Don't print the full URL — it contains the auth token.
print(f"url:    http://localhost:<port>/webhook?token=<redacted>")

# Load existing settings, if any
settings = {}
if os.path.exists(settings_path):
    print("file exists, reading...")
    try:
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
        existing_hooks = list(settings.get("hooks", {}).keys())
        print(f"current hooks: {existing_hooks if existing_hooks else '(none)'}")
    except json.JSONDecodeError as exc:
        print(f"warning: malformed JSON ({exc}) — starting fresh")
        settings = {}
    except OSError as exc:
        print(f"warning: cannot read file ({exc}) — starting fresh")
        settings = {}
else:
    print("file not found — will create new settings.json")

# Build and merge hook entries
hook_entry = {"type": "http", "url": webhook_url, "async": True}
hook_group = {"hooks": [hook_entry]}

target_events = ["Notification", "Stop", "PermissionRequest"]
if "hooks" not in settings:
    settings["hooks"] = {}

for event in target_events:
    action = "overwriting" if event in settings["hooks"] else "adding"
    print(f"{action}: '{event}' hook")
    settings["hooks"][event] = [hook_group]

# Write back
try:
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    print(f"written: {settings_path}")
    print(f"hooks set: {list(settings['hooks'].keys())}")
except OSError as exc:
    print(f"error: cannot write {settings_path}: {exc}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo ""
echo "✅  Claude Code hooks configured."
echo "    Webhook URL : http://${HOST}:${PORT}/webhook?token=<redacted>"
echo "    Events      : Notification, Stop, PermissionRequest"
echo ""
echo "    Restart Claude Code for changes to take effect."

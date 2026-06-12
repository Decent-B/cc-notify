#!/usr/bin/env bash
# setup-hooks.sh — Configure Claude Code hooks from inside WSL2.
#
# Run this script from WITHIN your WSL2 distro after cc-notify.exe is running
# on the Windows side. It detects the Windows host IP automatically and writes
# the webhook URL into ~/.claude/settings.json.
#
# Usage:
#   bash scripts/setup-hooks.sh               # auto-detect host IP, port 9876
#   CC_NOTIFY_PORT=9999 bash setup-hooks.sh   # custom port
#   bash setup-hooks.sh --dry-run             # print config without writing

set -euo pipefail

PORT="${CC_NOTIFY_PORT:-9876}"
DRY_RUN=false

for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
done

SETTINGS="$HOME/.claude/settings.json"

# ── Detect the Windows host IP ────────────────────────────────────────────────

detect_windows_host() {
  # 1. Try host.docker.internal — available on Windows 11 WSL2 with mirrored
  #    networking or Docker Desktop installed.
  if getent hosts host.docker.internal &>/dev/null; then
    echo "host.docker.internal"
    return
  fi

  # 2. Fall back to the DNS nameserver from /etc/resolv.conf — the WSL2
  #    virtual gateway always points to the Windows host.
  awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf
}

if grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
  HOST_IP=$(detect_windows_host)
  WEBHOOK_URL="http://${HOST_IP}:${PORT}/webhook"
  echo "WSL2 detected. Windows host: ${HOST_IP}"
else
  WEBHOOK_URL="http://localhost:${PORT}/webhook"
  echo "Native Linux detected."
fi

echo "Webhook URL: ${WEBHOOK_URL}"

if $DRY_RUN; then
  echo ""
  echo "[dry-run] Would write to: ${SETTINGS}"
  echo "[dry-run] Webhook URL   : ${WEBHOOK_URL}"
  exit 0
fi

# ── Merge into settings.json using Python (avoids jq dependency) ─────────────

mkdir -p "$(dirname "$SETTINGS")"

python3 - "$SETTINGS" "$WEBHOOK_URL" <<'PYEOF'
import json, sys

settings_path = sys.argv[1]
webhook_url   = sys.argv[2]

try:
    with open(settings_path) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

hook_entry = {"type": "http", "url": webhook_url, "async": True}
hook_group = {"hooks": [hook_entry]}

new_hooks = {
    "Notification":      [hook_group],
    "Stop":              [hook_group],
    "PermissionRequest": [hook_group],
}

if "hooks" not in settings:
    settings["hooks"] = {}

for event, cfg in new_hooks.items():
    if event in settings["hooks"]:
        print(f"  (overwriting existing '{event}' hooks)")
    settings["hooks"][event] = cfg

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)

print(f"Settings written to {settings_path}")
PYEOF

echo ""
echo "✅  Claude Code hooks configured."
echo "    Webhook URL : ${WEBHOOK_URL}"
echo "    Events      : Notification, Stop, PermissionRequest"
echo ""
echo "    Restart Claude Code for changes to take effect."

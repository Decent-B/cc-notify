#!/usr/bin/env bash
# scripts/pre-push-check.sh — Full pre-push verification from WSL2.
#
# Runs every check needed before tagging a release in one command:
#   1. Build the Windows EXE (delegates to build-windows.sh)
#   2. Stop any running instance and launch the fresh EXE
#   3. Wait for the webhook server to become ready
#   4. Fire test payloads for every notification type
#   5. Confirm the working tree is clean
#
# Visual: watch the Windows Notification Center during step 4 —
# three distinct toasts should appear (Task Complete, Permission
# Required with alarm sound, and Waiting for Input).
#
# Usage:
#   bash scripts/pre-push-check.sh                  # run all steps
#   bash scripts/pre-push-check.sh --from-step 3    # skip build + launch
#   bash scripts/pre-push-check.sh -h               # show this help

set -euo pipefail

# ── Help ──────────────────────────────────────────────────────────────────────

usage() {
  cat <<'EOF'
Usage: bash scripts/pre-push-check.sh [--from-step N] [-h|--help]

Run the full pre-push verification checklist from inside WSL2.

Steps
  1  Build     Compile the Windows EXE via PowerShell interop
               (delegates to scripts/build-windows.sh)
  2  Launch    Stop any running cc-notify instance, copy the fresh
               EXE to %%TEMP%%, and start it
  3  Health    Poll http://<win-host>:9876/health until the webhook
               server is ready (15-second timeout)
  4  Webhooks  POST a test payload for every notification type and
               verify each returns HTTP 200
               (watch Windows Notification Center — three toasts
               should appear: Task Complete, Permission Required,
               Waiting for Input)
  5  Git       Confirm the working tree is clean before pushing

Options
  --from-step N   Start at step N (1–5), skipping all earlier steps.
                  Useful when the build is already fresh and you only
                  want to re-run the smoke tests, e.g. --from-step 3.

  -h, --help      Print this message and exit.

Examples
  bash scripts/pre-push-check.sh
      Full run: build → launch → health → webhooks → git check.

  bash scripts/pre-push-check.sh --from-step 2
      Skip the build; restart the EXE and run all remaining steps.

  bash scripts/pre-push-check.sh --from-step 3
      Assume cc-notify is already running; jump straight to the
      health check and everything after it.

  bash scripts/pre-push-check.sh --from-step 4
      Server is up; re-fire the webhook payloads and check git only.

  bash scripts/pre-push-check.sh --from-step 5
      Only verify the working tree is clean.

Notes
  - This script must be run from inside WSL2 (it uses powershell.exe
    via WSL2 interop to drive the Windows side of the build).
  - The script connects to the Windows host via localhost (WSL2 forwards
    localhost to Windows by default).  If your setup uses a separate
    virtual switch IP, override with: CC_NOTIFY_HOST=<ip> bash scripts/pre-push-check.sh
  - Requires curl on the WSL2 side.
EOF
}

# ── Argument parsing ──────────────────────────────────────────────────────────

FROM_STEP=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --from-step)
      if [[ -z "${2-}" || ! "${2}" =~ ^[1-5]$ ]]; then
        echo "error: --from-step requires a value between 1 and 5." >&2
        echo "       Run with --help for usage." >&2
        exit 1
      fi
      FROM_STEP="$2"
      shift 2
      ;;
    --from-step=*)
      val="${1#--from-step=}"
      if [[ ! "$val" =~ ^[1-5]$ ]]; then
        echo "error: --from-step requires a value between 1 and 5." >&2
        echo "       Run with --help for usage." >&2
        exit 1
      fi
      FROM_STEP="$val"
      shift
      ;;
    *)
      echo "error: unknown option '$1'." >&2
      echo "       Run with --help for usage." >&2
      exit 1
      ;;
  esac
done

# ── Guard: WSL2 only ──────────────────────────────────────────────────────────

if ! grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
  echo "error: this script is for WSL2 only." >&2
  exit 1
fi

# ── Setup ─────────────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WIN_PATH=$(wslpath -w "$REPO_ROOT")

# WSL2 forwards localhost to the Windows host by default (mirrored networking
# and localhostForwarding both work this way).  The /etc/resolv.conf nameserver
# approach is unreliable — it returns a VPN/Tailscale DNS IP when those are
# active, not the Windows host.  Override with CC_NOTIFY_HOST if needed.
WIN_HOST="${CC_NOTIFY_HOST:-localhost}"
BASE_URL="http://${WIN_HOST}:9876"

# ── Read the per-install webhook token from cc-notify's Windows state file ─────
# The token is stored in %APPDATA%\cc-notify\state.json and must be included
# as ?token=<value> in every POST to /webhook.

APPDATA_WIN="$(powershell.exe -NoProfile -Command 'Write-Output $env:APPDATA' \
  2>/dev/null | tr -d '\r\n')" || true
STATE_FILE="$(wslpath "${APPDATA_WIN}/cc-notify/state.json" 2>/dev/null)" || true
TOKEN=""
if [[ -f "${STATE_FILE:-}" ]]; then
  TOKEN="$(python3 -c "
import json, sys
try:
    d = json.load(open('$STATE_FILE', encoding='utf-8'))
    print(d.get('webhook_token', ''), end='')
except Exception:
    pass
" 2>/dev/null)" || true
fi

if [[ -z "$TOKEN" ]]; then
  echo "WARNING: Could not read webhook token from state.json."
  echo "  Webhook tests will fail (server requires a valid token)."
  echo "  Launch cc-notify.exe once to generate the token, then re-run."
fi

PASS=0
FAIL=0

# ── Output helpers ────────────────────────────────────────────────────────────

section() { echo ""; echo "── $* "; }
ok()      { echo "  ✓  $*"; PASS=$((PASS + 1)); }
fail()    { echo "  ✗  $*"; FAIL=$((FAIL + 1)); }

# Send a webhook payload and record pass/fail based on the HTTP status code.
webhook_test() {
  local label="$1"
  local payload="$2"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${BASE_URL}/webhook?token=${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$payload")
  if [[ "$status" == "200" ]]; then
    ok "${label}  [HTTP ${status}]"
  else
    fail "${label}  [HTTP ${status} — expected 200]"
  fi
}

[[ $FROM_STEP -gt 1 ]] && echo "  (skipping steps 1–$((FROM_STEP - 1)))"

# ── Step 1: Build ─────────────────────────────────────────────────────────────

if [[ $FROM_STEP -le 1 ]]; then
  section "1/5  Build"
  bash "${REPO_ROOT}/scripts/build-windows.sh"
fi

# ── Step 2: Launch ────────────────────────────────────────────────────────────

if [[ $FROM_STEP -le 2 ]]; then
  section "2/5  Launch"

  # Consolidate kill + launch into one PowerShell session to avoid the PS 5.1
  # exit-code trap: any cmdlet that touches a missing process sets $? = False,
  # and PowerShell -Command exits 1 when $? is False — killing bash's set -e.
  # Using an explicit if-conditional keeps $? True regardless of whether the
  # process exists.  We also copy the EXE to %TEMP% before launching because
  # Windows may refuse to start a process directly from a WSL2 UNC path
  # (\\wsl.localhost\...) due to security zone restrictions.
  powershell.exe -NoProfile -Command "
    \$p = Get-Process -Name 'cc-notify' -ErrorAction SilentlyContinue
    if (\$p) { \$p | Stop-Process }
    Start-Sleep -Seconds 1
    \$exe = \"\$env:TEMP\cc-notify.exe\"
    Copy-Item '${WIN_PATH}\dist\cc-notify.exe' \$exe -Force
    Start-Process \$exe
  "
  echo "  cc-notify.exe launched"
fi

# ── Step 3: Health ────────────────────────────────────────────────────────────

if [[ $FROM_STEP -le 3 ]]; then
  section "3/5  Health"
  printf "  Waiting for server"

  READY=false
  for i in $(seq 1 15); do
    if curl -sf "${BASE_URL}/health" >/dev/null 2>&1; then
      READY=true
      echo " — ready"
      break
    fi
    printf "."
    sleep 1
  done

  if ! $READY; then
    echo ""
    fail "Server did not become ready within 15 s"
    echo ""
    echo "  Cannot run webhook tests. Check that cc-notify.exe started"
    echo "  and that port 9876 is not in use by another process."
    exit 1
  fi

  ok "$(curl -s "${BASE_URL}/health")"
fi

# ── Step 4: Webhook tests ─────────────────────────────────────────────────────

if [[ $FROM_STEP -le 4 ]]; then
  section "4/5  Webhooks  (watch for toasts on screen)"

  webhook_test "Stop          → Task Complete toast" \
    '{"hook_event_name":"Stop","session_id":"test","cwd":"/home"}'

  webhook_test "PermissionRequest → Permission Required toast (alarm)" \
    '{"hook_event_name":"PermissionRequest","tool_name":"Bash","session_id":"test","cwd":"/home"}'

  webhook_test "Notification/idle_prompt → Waiting for Input toast" \
    '{"hook_event_name":"Notification","notification_type":"idle_prompt","message":"Waiting for your reply.","session_id":"test","cwd":"/home"}'
fi

# ── Step 5: Git status ────────────────────────────────────────────────────────

section "5/5  Git"
BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)
echo "  Branch: ${BRANCH}"

DIRTY=$(git -C "$REPO_ROOT" status --short)
if [[ -z "$DIRTY" ]]; then
  ok "Working tree is clean"
else
  echo "$DIRTY" | sed 's/^/    /'
  fail "Uncommitted changes — commit or stash before pushing"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

TOTAL=$((PASS + FAIL))
echo ""
echo "──────────────────────────────────────────────────"
if [[ $FAIL -eq 0 ]]; then
  echo "  ✓  All ${TOTAL} checks passed — ready to push."
else
  echo "  ✗  ${FAIL} of ${TOTAL} checks failed — fix before pushing."
  exit 1
fi

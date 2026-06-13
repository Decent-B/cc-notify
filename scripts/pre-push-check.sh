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
# Usage (from anywhere in the repo):
#   bash scripts/pre-push-check.sh

set -euo pipefail

# ── Guard: WSL2 only ──────────────────────────────────────────────────────────

if ! grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
  echo "error: this script is for WSL2 only." >&2
  exit 1
fi

# ── Setup ─────────────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WIN_PATH=$(wslpath -w "$REPO_ROOT")
WIN_HOST=$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf)
BASE_URL="http://${WIN_HOST}:9876"

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
    -X POST "${BASE_URL}/webhook" \
    -H "Content-Type: application/json" \
    -d "$payload")
  if [[ "$status" == "200" ]]; then
    ok "${label}  [HTTP ${status}]"
  else
    fail "${label}  [HTTP ${status} — expected 200]"
  fi
}

# ── Step 1: Build ─────────────────────────────────────────────────────────────

section "1/5  Build"
bash "${REPO_ROOT}/scripts/build-windows.sh"

# ── Step 2: Launch ────────────────────────────────────────────────────────────

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

# ── Step 3: Health ────────────────────────────────────────────────────────────

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

# ── Step 4: Webhook tests ─────────────────────────────────────────────────────

section "4/5  Webhooks  (watch for toasts on screen)"

webhook_test "Stop          → Task Complete toast" \
  '{"hook_event_name":"Stop","session_id":"test","cwd":"/home"}'

webhook_test "PermissionRequest → Permission Required toast (alarm)" \
  '{"hook_event_name":"PermissionRequest","tool_name":"Bash","session_id":"test","cwd":"/home"}'

webhook_test "Notification/idle_prompt → Waiting for Input toast" \
  '{"hook_event_name":"Notification","notification_type":"idle_prompt","message":"Waiting for your reply.","session_id":"test","cwd":"/home"}'

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

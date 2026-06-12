# Claude Code Hooks — Reference

Research notes on the Claude Code hooks system, compiled for the cc-notify
project. Covers the events cc-notify subscribes to plus the full event
catalogue for future extension.

---

## How Hooks Work

Claude Code hooks are shell commands or HTTP endpoints that fire at specific
lifecycle events. The hook configuration lives in
`~/.claude/settings.json` (user scope, all projects) or
`.claude/settings.json` (project scope).

```jsonc
{
  "hooks": {
    "<EventName>": [
      {
        "matcher": "<optional filter string>",
        "hooks": [
          {
            "type": "http",
            "url": "http://localhost:9876/webhook",
            "async": true
          }
        ]
      }
    ]
  }
}
```

For HTTP hooks:

- Method: `POST`
- Content-Type: `application/json`
- Body: the full event JSON payload (same format as stdin for command hooks)
- Default timeout: 600 seconds
- Non-2xx responses and connection failures are non-blocking errors — Claude
  Code logs them but continues execution.
- `async: true` means Claude Code fires the hook and does not wait for a
  response. This is what cc-notify uses for all events.

---

## Events cc-notify Uses

### `Notification`

Fires when Claude Code wants to surface a status update to the user.

**Payload fields relevant to cc-notify:**

```jsonc
{
  "hook_event_name": "Notification",
  "session_id": "...",
  "cwd": "/path/to/project",
  "notification_type": "permission_prompt | idle_prompt | auth_success | elicitation_dialog | elicitation_complete | elicitation_response",
  "message": "Descriptive text (human-readable)",
  "title": "Optional short title"
}
```

| `notification_type` | When it fires | cc-notify response |
|---|---|---|
| `permission_prompt` | Claude Code is paused waiting for the user to approve a tool call | Toast: "Permission Required" |
| `idle_prompt` | Claude Code is waiting for the user to type a follow-up | Toast: "Waiting for Input" |
| `auth_success` | API authentication succeeded | Toast (if `message` is non-empty) |
| `elicitation_dialog` | An MCP server is requesting structured user input | Toast (if `message` is non-empty) |
| `elicitation_complete` | An elicitation dialog was completed | Toast (if `message` is non-empty) |

**Matcher usage:** You can restrict this hook to specific types:
```json
{ "matcher": "permission_prompt|idle_prompt" }
```
cc-notify registers without a matcher and filters inside the server.

---

### `Stop`

Fires once per turn when Claude Code finishes generating a response.

**Payload:**
```jsonc
{
  "hook_event_name": "Stop",
  "session_id": "...",
  "cwd": "..."
}
```

No meaningful fields beyond session context — cc-notify uses this purely as a
"generation complete" signal and shows a fixed "Task Complete" notification.

**Can block Claude Code:** Returning `{"hookSpecificOutput": {"decision": "block", "additionalContext": "..."}}` from a synchronous hook tells Claude to keep going. cc-notify always uses `async: true`, so it never blocks.

---

### `PermissionRequest`

Fires when a tool call requires explicit user permission (distinct from the
`Notification[permission_prompt]` which is a UI-level event). Contains the
tool name and full input, making it more detailed.

**Payload:**
```jsonc
{
  "hook_event_name": "PermissionRequest",
  "session_id": "...",
  "cwd": "...",
  "tool_name": "Bash",
  "tool_input": { "command": "rm -rf /tmp/test" }
}
```

cc-notify formats this as: `"Bash is requesting permission. Switch to Claude Code to approve or deny."`

**Can auto-approve/deny:** A synchronous hook can return a decision. Because
cc-notify uses `async: true`, it never auto-approves — the user must still act
in the Claude Code interface.

---

## Full Event Catalogue

For completeness, all events exposed by Claude Code (as of 2026):

### Once Per Session
| Event | Fires when | Matcher values |
|---|---|---|
| `SessionStart` | Session begins or resumes | `startup`, `resume`, `clear`, `compact` |
| `SessionEnd` | Session terminates | — |

### Once Per Turn
| Event | Fires when |
|---|---|
| `UserPromptSubmit` | Before Claude processes user input |
| `Stop` | Claude finishes responding |
| `StopFailure` | Turn ends due to API error |

`StopFailure` matcher values: `rate_limit`, `authentication_failed`,
`billing_error`, `invalid_request`, `server_error`, `max_output_tokens`,
`unknown`.

### Per Tool Call
| Event | Fires when |
|---|---|
| `PreToolUse` | Before a tool executes (can block with exit code 2) |
| `PostToolUse` | After a tool succeeds |
| `PostToolUseFailure` | After a tool fails |

### Permission & Input
| Event | Fires when |
|---|---|
| `PermissionRequest` | Permission dialog would appear |
| `PermissionDenied` | An operation was denied |
| `Notification` | Status update for the user |
| `Elicitation` | MCP server requests structured input |
| `ElicitationResult` | User responds to elicitation |

### File & Config
| Event | Fires when |
|---|---|
| `FileChanged` | A watched file changes |
| `CwdChanged` | Working directory changes |
| `ConfigChange` | A settings file changes |
| `WorktreeCreate` | Git worktree created |
| `WorktreeRemove` | Git worktree removed |

### Task / Subagent
| Event | Fires when |
|---|---|
| `TaskCreated` | Background task spawned |
| `TaskCompleted` | Background task finishes |
| `SubagentStart` | Subagent initialises |
| `SubagentStop` | Subagent completes |

---

## Common Payload Fields (All Events)

```jsonc
{
  "session_id":       "string — unique per Claude Code session",
  "cwd":              "/absolute/path — current working directory",
  "hook_event_name":  "EventName",
  "transcript_path":  "/path/to/transcript.jsonl",
  "agent_id":         "string — present only inside a subagent",
  "agent_type":       "string — present only inside a subagent"
}
```

---

## Hook Exit Code Semantics (Command Hooks)

| Exit code | Meaning |
|---|---|
| `0` | Success — parse stdout JSON for decisions |
| `2` | Blocking error — deny / block the operation, ignore stderr |
| `1`, `3+` | Non-blocking error — log first line of stderr, continue |

HTTP hooks always succeed as long as they return 2xx; non-2xx is treated as a
non-blocking error.

---

## Configuration Locations (Priority Order)

1. `.claude/settings.local.json` (project, not committed)
2. `.claude/settings.json` (project, shareable)
3. `~/.claude/settings.json` (user, all projects) ← **cc-notify installs here**
4. Plugin `hooks/hooks.json` (when plugin is enabled)

---

## References

- [Hooks Reference — Anthropic Docs](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [Automate Actions with Hooks — Anthropic Docs](https://docs.anthropic.com/en/docs/claude-code/hooks-guide)
- [Agent SDK Hooks — Anthropic Docs](https://docs.anthropic.com/en/docs/claude-code/agent-sdk/hooks)

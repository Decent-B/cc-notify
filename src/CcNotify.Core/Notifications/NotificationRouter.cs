using CcNotify.Core.Settings;

namespace CcNotify.Core.Notifications;

/// <summary>Pure mapping from a Claude Code hook event to the notification to show (or null).</summary>
public sealed class NotificationRouter
{
    private static readonly Dictionary<string, string> FailureTitles = new()
    {
        ["rate_limit"] = "Claude Code — Rate Limited",
        ["authentication_failed"] = "Claude Code — Auth Failed",
        ["billing_error"] = "Claude Code — Billing Error",
        ["invalid_request"] = "Claude Code — Request Error",
        ["server_error"] = "Claude Code — Server Error",
        ["max_output_tokens"] = "Claude Code — Token Limit Reached",
    };

    private readonly IMessageCatalog _messages;

    public NotificationRouter(IMessageCatalog messages) => _messages = messages;

    public Notification? Route(HookEvent e, AppSettings s)
    {
        var cwd = string.IsNullOrEmpty(e.Cwd) ? null : e.Cwd;
        return e.Name switch
        {
            "Notification" => RouteNotification(e, s, cwd),
            "Stop" when s.NotifyOnStop =>
                Make(NotificationKind.TaskComplete, "Claude Code — Task Complete", cwd),
            "StopFailure" when s.NotifyOnStopFailure =>
                Make(NotificationKind.Failure,
                     FailureTitles.GetValueOrDefault(e.StopReason, "Claude Code — Something Went Wrong"), cwd),
            // PermissionRequest is deliberately ignored: it fires together with
            // Notification[permission_prompt] (one popup would become two), and also when auto
            // mode decides on its own without ever asking the user.
            _ => null,
        };
    }

    private Notification? RouteNotification(HookEvent e, AppSettings s, string? cwd) => e.NotificationType switch
    {
        "permission_prompt" when s.NotifyOnPermission =>
            Make(NotificationKind.Permission, "Claude Code — Permission Required", cwd),
        "idle_prompt" when s.NotifyOnIdle =>
            Make(NotificationKind.Idle, "Claude Code — Waiting for Input", cwd),
        // Low-priority status updates: shown only when Claude supplies a message, no VS Code focus.
        "auth_success" or "elicitation_dialog" or "elicitation_complete" when e.Message.Length > 0 =>
            new Notification(NotificationKind.Info, e.Title.Length > 0 ? e.Title : "Claude Code", e.Message),
        _ => null,
    };

    private Notification Make(NotificationKind kind, string title, string? cwd) =>
        new(kind, title, _messages.Pick(kind), cwd);
}

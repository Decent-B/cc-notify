namespace CcNotify.Core.Notifications;

public enum NotificationKind { Permission, Idle, TaskComplete, Failure, Info }

/// <summary>
/// A notification ready to be shown. <paramref name="Cwd"/> makes the popup focus the matching
/// VS Code window when clicked; <paramref name="OnClick"/> overrides that with a custom action.
/// </summary>
public sealed record Notification(
    NotificationKind Kind,
    string Title,
    string Body,
    string? Cwd = null,
    Action? OnClick = null);

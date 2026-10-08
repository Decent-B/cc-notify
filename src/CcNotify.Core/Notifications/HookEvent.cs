using System.Text.Json;

namespace CcNotify.Core.Notifications;

/// <summary>The subset of a Claude Code hook payload cc-notify cares about.</summary>
public sealed record HookEvent(
    string Name,
    string NotificationType = "",
    string Message = "",
    string Title = "",
    string Cwd = "",
    string StopReason = "",
    string ToolName = "")
{
    public static HookEvent Parse(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.ValueKind != JsonValueKind.Object) return new HookEvent("");
            var root = doc.RootElement;
            string S(string name) =>
                root.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "";
            return new HookEvent(
                S("hook_event_name"), S("notification_type"), S("message"),
                S("title"), S("cwd"), S("stop_reason"), S("tool_name"));
        }
        catch (JsonException)
        {
            return new HookEvent("");
        }
    }
}

using System.Text.Json;
using System.Text.Json.Nodes;

namespace CcNotify.Core.Hooks;

/// <summary>Merges cc-notify's hook entries into a Claude Code settings.json, keeping everything else.</summary>
public static class ClaudeSettingsMerger
{
    public static readonly string[] Events = ["Notification", "Stop", "StopFailure"];

    /// <summary>Events earlier versions registered; their cc-notify entries are removed on setup.</summary>
    private static readonly string[] Retired = ["PermissionRequest"];

    private static readonly JsonSerializerOptions Pretty = new() { WriteIndented = true };

    /// <param name="existingJson">Current file content, or null/blank when there is none.</param>
    /// <returns>The new content, and whether the existing content was unparseable (and so replaced).</returns>
    public static (string Json, bool ReplacedInvalid) Merge(string? existingJson, string webhookUrl)
    {
        JsonObject root = new();
        var replaced = false;
        if (!string.IsNullOrWhiteSpace(existingJson))
        {
            try { root = JsonNode.Parse(existingJson) as JsonObject ?? new JsonObject(); replaced = false; }
            catch (JsonException) { replaced = true; }
        }

        var hooks = root["hooks"] as JsonObject ?? new JsonObject();
        foreach (var name in Events)
        {
            hooks[name] = new JsonArray(new JsonObject
            {
                ["hooks"] = new JsonArray(new JsonObject
                {
                    ["type"] = "http",
                    ["url"] = webhookUrl,
                    ["async"] = true,
                }),
            });
        }
        foreach (var name in Retired)
            if (hooks[name] is JsonArray groups && groups.All(IsOurs)) hooks.Remove(name);
        root["hooks"] = hooks;
        return (root.ToJsonString(Pretty), replaced);
    }

    // Only remove what cc-notify wrote: every hook in the group is our token-carrying webhook.
    private static bool IsOurs(JsonNode? group) =>
        group?["hooks"] is JsonArray { Count: > 0 } hooks &&
        hooks.All(h => (string?)h?["url"] is { } url && url.Contains("/webhook?token=", StringComparison.Ordinal));
}

using System.Text.Json;

namespace CcNotify.Core.Notifications;

/// <summary>Source of the humorous notification bodies.</summary>
public interface IMessageCatalog
{
    string Pick(NotificationKind kind);
}

/// <summary>Messages loaded from the embedded messages.json (one list per kind).</summary>
public sealed class MessageCatalog : IMessageCatalog
{
    private readonly IReadOnlyDictionary<string, string[]> _pools;

    public MessageCatalog(IReadOnlyDictionary<string, string[]> pools) => _pools = pools;

    public static MessageCatalog LoadEmbedded()
    {
        using var stream = typeof(MessageCatalog).Assembly.GetManifestResourceStream("messages.json")
            ?? throw new InvalidOperationException("messages.json resource is missing");
        var pools = JsonSerializer.Deserialize<Dictionary<string, string[]>>(stream)
            ?? throw new InvalidOperationException("messages.json is empty");
        return new MessageCatalog(pools);
    }

    public string Pick(NotificationKind kind)
    {
        var key = kind switch
        {
            NotificationKind.Permission => "permission",
            NotificationKind.Idle => "idle",
            NotificationKind.TaskComplete => "task_complete",
            NotificationKind.Failure => "failure",
            _ => ""
        };
        return _pools.TryGetValue(key, out var pool) && pool.Length > 0
            ? pool[Random.Shared.Next(pool.Length)]
            : "";
    }
}

using System.Text.Json;
using System.Text.Json.Serialization;

namespace CcNotify.Core.Settings;

/// <summary>
/// A JSON document on disk. Keys are snake_case so files written by the earlier
/// Python release keep loading. Reads fall back to defaults; writes are atomic.
/// </summary>
internal sealed class JsonFile<T> where T : class, new()
{
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
    };

    private readonly string _path;

    public JsonFile(string path) => _path = path;

    public T Load()
    {
        try
        {
            return File.Exists(_path)
                ? JsonSerializer.Deserialize<T>(File.ReadAllText(_path), Options) ?? new T()
                : new T();
        }
        catch (Exception e) when (e is JsonException or IOException or UnauthorizedAccessException)
        {
            return new T();
        }
    }

    public void Save(T value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
        var tmp = _path + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(value, Options));
        File.Move(tmp, _path, overwrite: true);
    }
}

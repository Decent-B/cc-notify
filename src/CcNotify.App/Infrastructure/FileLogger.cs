using Microsoft.Extensions.Logging;

namespace CcNotify.Ui.Infrastructure;

/// <summary>Minimal append-only file logger — the app has no console, so this is how problems get diagnosed.</summary>
internal sealed class FileLogger : ILogger
{
    private const long MaxBytes = 1_000_000;
    private static readonly object Gate = new();
    private readonly string _path;

    public FileLogger(string path) => _path = path;

    public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
    public bool IsEnabled(LogLevel level) => level >= LogLevel.Information;

    public void Log<TState>(LogLevel level, EventId id, TState state, Exception? ex, Func<TState, Exception?, string> fmt)
    {
        if (!IsEnabled(level)) return;
        var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} [{level}] {fmt(state, ex)}{(ex is null ? "" : $"\n{ex}")}\n";
        lock (Gate)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
                if (File.Exists(_path) && new FileInfo(_path).Length > MaxBytes)
                    File.Move(_path, _path + ".old", overwrite: true);
                File.AppendAllText(_path, line);
            }
            catch (IOException) { /* logging must never throw */ }
        }
    }
}

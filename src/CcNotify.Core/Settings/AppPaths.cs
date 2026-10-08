namespace CcNotify.Core.Settings;

/// <summary>Where cc-notify keeps its files (%APPDATA%\cc-notify, writable without admin).</summary>
public sealed record AppPaths(string Root)
{
    /// <summary>%APPDATA%\cc-notify, or the folder in CC_NOTIFY_DATA_DIR (used to run a throwaway copy).</summary>
    public static AppPaths Default { get; } = new(
        Environment.GetEnvironmentVariable("CC_NOTIFY_DATA_DIR") is { Length: > 0 } dir
            ? dir
            : Path.Combine(Roaming(), "cc-notify"));

    // An empty result would silently turn our paths into relative ones, so fail loudly instead.
    private static string Roaming() =>
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) is { Length: > 0 } dir
            ? dir
            : throw new InvalidOperationException("Windows did not report the AppData folder");

    public string Config => Path.Combine(Root, "config.json");
    public string State => Path.Combine(Root, "state.json");
    public string Log => Path.Combine(Root, "cc-notify.log");
}

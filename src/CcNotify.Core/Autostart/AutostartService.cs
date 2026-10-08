using Microsoft.Win32;
using CcNotify.Core.Settings;

namespace CcNotify.Core.Autostart;

public enum AutostartStatus
{
    On,
    Off,
    /// <summary>Registered, but switched off in Windows Settings › Apps › Startup or Task Manager.
    /// An app must not override that choice — only the user turns it back on there.</summary>
    DisabledBySystem,
}

public interface IAutostartService
{
    AutostartStatus Status { get; }
    void SetEnabled(bool on);

    /// <summary>First run: turn it on once. Later runs: only repair a stale path. Never overrides the user.</summary>
    void Initialize();
}

/// <summary>
/// Start with Windows via the per-user <c>Run</c> key. Writes only HKCU, quotes the exe path, and
/// never touches <c>StartupApproved</c> (that value belongs to the user's Settings toggle).
/// </summary>
public sealed class AutostartService : IAutostartService
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string ApprovedKey = @"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run";

    private readonly ISettingsStore _settings;
    private readonly string _valueName;
    private readonly string _runKey;
    private readonly string _approvedKey;
    private readonly string _command;

    public AutostartService(ISettingsStore settings, string exePath,
        string valueName = "Claude Code Notifier", string runKey = RunKey, string approvedKey = ApprovedKey)
    {
        _settings = settings;
        _valueName = valueName;
        _runKey = runKey;
        _approvedKey = approvedKey;
        // Quoted: unquoted, a path with spaces makes Windows guess where the program name ends.
        _command = $"\"{exePath}\"";
    }

    public AutostartStatus Status =>
        Registered() is null ? AutostartStatus.Off
        : DisabledByUser() ? AutostartStatus.DisabledBySystem
        : AutostartStatus.On;

    public void SetEnabled(bool on)
    {
        using var key = Registry.CurrentUser.CreateSubKey(_runKey);
        if (on) key.SetValue(_valueName, _command, RegistryValueKind.String);
        else key.DeleteValue(_valueName, throwOnMissingValue: false);
    }

    public void Initialize()
    {
        if (!_settings.Current.AutostartInitialized)
        {
            if (Status == AutostartStatus.Off) SetEnabled(true);
            _settings.Update(s => s with { AutostartInitialized = true });
        }
        else if (Registered() is { } current && current != _command)
        {
            SetEnabled(true); // the exe moved: point the entry at it
        }
    }

    private string? Registered()
    {
        using var key = Registry.CurrentUser.OpenSubKey(_runKey);
        return key?.GetValue(_valueName) as string;
    }

    /// <summary>StartupApproved holds 12 bytes per entry; an odd first byte means the user turned it off.
    /// No value means never touched, i.e. enabled.</summary>
    private bool DisabledByUser()
    {
        using var key = Registry.CurrentUser.OpenSubKey(_approvedKey);
        return key?.GetValue(_valueName) is byte[] { Length: > 0 } v && (v[0] & 1) == 1;
    }
}

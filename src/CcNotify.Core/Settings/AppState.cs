using System.Security.Cryptography;

namespace CcNotify.Core.Settings;

/// <summary>Machine-written runtime state (state.json): not meant to be edited by hand.</summary>
public sealed class AppStateData
{
    /// <summary>256-bit secret embedded in every hook URL so the server can reject unsolicited requests.</summary>
    public string? WebhookToken { get; set; }

    /// <summary>App version that last configured Claude Code hooks; a mismatch re-runs setup.</summary>
    public string? HooksConfiguredForVersion { get; set; }
}

public interface IAppState
{
    string WebhookToken { get; }
    string? HooksConfiguredForVersion { get; set; }
}

public sealed class AppState : IAppState
{
    private readonly JsonFile<AppStateData> _file;
    private readonly AppStateData _data;
    private readonly object _gate = new();

    public AppState(AppPaths paths)
    {
        _file = new JsonFile<AppStateData>(paths.State);
        _data = _file.Load();
        if (string.IsNullOrEmpty(_data.WebhookToken))
        {
            _data.WebhookToken = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
            _file.Save(_data);
        }
    }

    public string WebhookToken => _data.WebhookToken!;

    public string? HooksConfiguredForVersion
    {
        get { lock (_gate) return _data.HooksConfiguredForVersion; }
        set { lock (_gate) { _data.HooksConfiguredForVersion = value; _file.Save(_data); } }
    }
}

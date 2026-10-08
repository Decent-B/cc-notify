using CcNotify.Core.Settings;

namespace CcNotify.Core.Hooks;

public sealed record SetupResult(IReadOnlyList<InstallResult> Results, bool RequiredOk)
{
    public bool FullyOk => Results.All(r => r.Outcome != InstallOutcome.Failed);

    public string Summary() => string.Join("  |  ", Results.Select(r => r.Outcome switch
    {
        InstallOutcome.Configured => $"{r.Target} ✓",
        InstallOutcome.NotDetected => $"{r.Target} not detected",
        _ => $"{r.Target} ✗ — {r.Error ?? "unknown error"}",
    }));
}

/// <summary>Installs the webhook hooks into every Claude Code environment and remembers which version did.</summary>
public sealed class HookSetupService
{
    private readonly IEnumerable<IHookInstaller> _installers;
    private readonly ISettingsStore _settings;
    private readonly IAppState _state;
    private readonly string _version;

    public HookSetupService(IEnumerable<IHookInstaller> installers, ISettingsStore settings, IAppState state, string version)
    {
        _installers = installers;
        _settings = settings;
        _state = state;
        _version = version;
    }

    /// <summary>True on a fresh install or after an upgrade, i.e. when hooks should be (re)configured.</summary>
    public bool NeedsSetup => _state.HooksConfiguredForVersion != _version;

    public async Task<SetupResult> RunAsync()
    {
        var url = $"http://localhost:{_settings.Current.Port}/webhook?token={_state.WebhookToken}";
        var results = new List<InstallResult>();
        var requiredOk = true;
        foreach (var installer in _installers)
        {
            var r = await installer.InstallAsync(url);
            results.AddRange(r);
            if (installer.IsRequired && r.Any(x => x.Outcome == InstallOutcome.Failed)) requiredOk = false;
        }
        // Record the version once the required (Windows) side works; a flaky WSL must not re-run setup every launch.
        if (requiredOk) _state.HooksConfiguredForVersion = _version;
        return new SetupResult(results, requiredOk);
    }
}

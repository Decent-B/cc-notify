using System.Text;
using CcNotify.Core.VsCode;

namespace CcNotify.Core.Hooks;

public enum InstallOutcome { Configured, Failed, NotDetected }

public sealed record InstallResult(string Target, InstallOutcome Outcome, string? Error = null);

/// <summary>One place Claude Code can run (native Windows, a WSL distro, ...). Add a class to support another.</summary>
public interface IHookInstaller
{
    /// <summary>True for the target whose failure should count as a failed setup.</summary>
    bool IsRequired { get; }

    Task<IReadOnlyList<InstallResult>> InstallAsync(string webhookUrl);
}

public sealed class WindowsHookInstaller : IHookInstaller
{
    private readonly string _settingsPath;

    public WindowsHookInstaller(string? userProfile = null)
    {
        userProfile ??= Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (userProfile.Length == 0) throw new InvalidOperationException("Windows did not report the user profile folder");
        _settingsPath = Path.Combine(userProfile, ".claude", "settings.json");
    }

    public bool IsRequired => true;

    public Task<IReadOnlyList<InstallResult>> InstallAsync(string webhookUrl)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_settingsPath)!);
            var existing = File.Exists(_settingsPath) ? File.ReadAllText(_settingsPath) : null;
            var (json, replaced) = ClaudeSettingsMerger.Merge(existing, webhookUrl);
            if (replaced) File.Copy(_settingsPath, _settingsPath + ".bak", overwrite: true);
            File.WriteAllText(_settingsPath, json, new UTF8Encoding(false));
            return Result(new InstallResult("Windows", InstallOutcome.Configured));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            return Result(new InstallResult("Windows", InstallOutcome.Failed, e.Message));
        }
    }

    private static Task<IReadOnlyList<InstallResult>> Result(InstallResult r) =>
        Task.FromResult<IReadOnlyList<InstallResult>>([r]);
}

/// <summary>
/// Configures the default WSL distro by piping settings.json through <c>wsl --exec</c> — no
/// quoting hazards and no Python needed inside the distro. WSL forwards localhost to Windows.
/// </summary>
public sealed class WslHookInstaller : IHookInstaller
{
    private const string Path = "$HOME/.claude/settings.json";
    private readonly IWsl _wsl;

    public WslHookInstaller(IWsl wsl) => _wsl = wsl;

    public bool IsRequired => false;

    public async Task<IReadOnlyList<InstallResult>> InstallAsync(string webhookUrl)
    {
        var distros = await _wsl.GetDistrosAsync();
        if (distros.Count == 0) return [new InstallResult("WSL2", InstallOutcome.NotDetected)];

        // Only the default distro, like before; others can use scripts/setup-hooks.sh.
        var name = $"WSL2 ({distros[0]})";
        try
        {
            var read = await _wsl.ExecAsync(distros[0], ["sh", "-c", $"cat \"{Path}\" 2>/dev/null; true"]);
            var (json, replaced) = ClaudeSettingsMerger.Merge(read.StdOut, webhookUrl);
            var script = (replaced ? $"cp \"{Path}\" \"{Path}.bak\"; " : "")
                       + $"mkdir -p \"$HOME/.claude\" && cat > \"{Path}\"";
            var write = await _wsl.ExecAsync(distros[0], ["sh", "-c", script], json);
            return write.ExitCode == 0
                ? [new InstallResult(name, InstallOutcome.Configured)]
                : [new InstallResult(name, InstallOutcome.Failed, write.StdErr.Trim())];
        }
        catch (Exception e) when (e is TimeoutException or InvalidOperationException)
        {
            return [new InstallResult(name, InstallOutcome.Failed, e.Message)];
        }
    }
}

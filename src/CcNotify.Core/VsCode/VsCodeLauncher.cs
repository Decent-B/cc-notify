using System.Diagnostics;
using System.Text.RegularExpressions;

namespace CcNotify.Core.VsCode;

public interface IVsCodeLauncher
{
    /// <summary>Focuses the VS Code window for <paramref name="cwd"/> and opens the folder there.</summary>
    Task FocusAsync(string cwd);
}

public sealed partial class VsCodeLauncher : IVsCodeLauncher
{
    private readonly IVsCodeWindows _windows;
    private readonly IWsl _wsl;
    private string? _defaultDistro;

    public VsCodeLauncher(IVsCodeWindows windows, IWsl wsl)
    {
        _windows = windows;
        _wsl = wsl;
    }

    public async Task FocusAsync(string cwd)
    {
        // Activate first: the click that got us here grants foreground rights, which
        // vscode:// IPC forwarding would not.
        if (_windows.Find(cwd) is { } hwnd) _windows.Activate(hwnd);

        var uri = BuildUri(cwd, await GetDefaultDistroAsync(cwd));
        if (uri is not null)
            Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
    }

    /// <summary>
    /// vscode:// target for <paramref name="cwd"/>, or null for anything that is not an absolute
    /// path (so a crafted cwd can never reach VS Code as a CLI flag). Linux paths need a WSL distro.
    /// </summary>
    internal static string? BuildUri(string cwd, string? wslDistro)
    {
        if (cwd.StartsWith('/'))
            return wslDistro is null
                ? null
                : $"vscode://vscode-remote/wsl+{Uri.EscapeDataString(wslDistro)}{EscapePath(cwd)}";

        return WindowsPath().IsMatch(cwd)
            ? $"vscode://file/{EscapePath(cwd.Replace('\\', '/'))}"
            : null;
    }

    // Escape each segment but keep '/' and the drive colon readable.
    private static string EscapePath(string path) =>
        string.Join('/', path.Split('/').Select((s, i) =>
            i == 0 && s.EndsWith(':') ? s : Uri.EscapeDataString(s)));

    private async Task<string?> GetDefaultDistroAsync(string cwd)
    {
        if (!cwd.StartsWith('/')) return null;
        return _defaultDistro ??= (await _wsl.GetDistrosAsync()).FirstOrDefault();
    }

    [GeneratedRegex(@"^[A-Za-z]:[\\/]")]
    private static partial Regex WindowsPath();
}

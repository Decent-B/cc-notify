using System.Diagnostics;
using System.Net.Http.Headers;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace CcNotify.Core.Updates;

public sealed record ReleaseInfo(string Tag, string DownloadUrl);

/// <summary>
/// Self-update from GitHub Releases: find a newer cc-notify.exe, download it, and let a detached
/// PowerShell helper swap the exe once this process exits and start the new one.
/// </summary>
public sealed class UpdateService
{
    private const string LatestUrl = "https://api.github.com/repos/Decent-B/cc-notify/releases/latest";

    private readonly HttpClient _http;
    private readonly string _currentVersion;
    private readonly string _exePath;
    private readonly ILogger _log;

    public UpdateService(HttpClient http, string currentVersion, string exePath, ILogger log)
    {
        _http = http;
        _currentVersion = currentVersion;
        _exePath = exePath;
        _log = log;
        _http.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("cc-notify", currentVersion));
    }

    /// <summary>The newest release found by the last check, if it is newer than this build.</summary>
    public ReleaseInfo? Pending { get; private set; }

    /// <summary>Queries GitHub. Null when up to date. Throws on network/parse errors.</summary>
    public async Task<ReleaseInfo?> CheckAsync()
    {
        using var doc = JsonDocument.Parse(await _http.GetStringAsync(LatestUrl));
        var root = doc.RootElement;
        var tag = root.TryGetProperty("tag_name", out var t) ? t.GetString()?.Trim() : null;
        if (string.IsNullOrEmpty(tag)) throw new InvalidDataException("GitHub response contained no tag_name");

        if (!IsNewer(tag, _currentVersion)) { Pending = null; return null; }

        foreach (var asset in root.GetProperty("assets").EnumerateArray())
        {
            if (IsExeAsset(asset.GetProperty("name").GetString()))
                return Pending = new ReleaseInfo(tag, asset.GetProperty("browser_download_url").GetString()!);
        }
        _log.LogWarning("Release {Tag} has no cc-notify exe asset — skipping", tag);
        return null;
    }

    /// <summary>Release assets are named like cc-notify-0.2.0-windows-x64.exe.</summary>
    internal static bool IsExeAsset(string? name) =>
        name is not null &&
        name.StartsWith("cc-notify", StringComparison.OrdinalIgnoreCase) &&
        name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase);

    internal static bool IsNewer(string tag, string current) =>
        Version.TryParse(tag.TrimStart('v'), out var a) &&
        Version.TryParse(current.TrimStart('v'), out var b) && a > b;

    /// <summary>Downloads the release and launches the swap helper. The caller must exit afterwards.</summary>
    public async Task StartInstallAsync(ReleaseInfo release)
    {
        var temp = Path.GetTempPath();
        var download = Path.Combine(temp, "cc-notify-update.exe");
        var script = Path.Combine(temp, "cc-notify-update.ps1");

        _log.LogInformation("Downloading {Url}", release.DownloadUrl);
        await using (var src = await _http.GetStreamAsync(release.DownloadUrl))
        await using (var dst = File.Create(download))
            await src.CopyToAsync(dst);

        await File.WriteAllTextAsync(script, BuildSwapScript(Environment.ProcessId, _exePath, download));
        Process.Start(new ProcessStartInfo("powershell.exe",
            ["-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script])
        { UseShellExecute = false, CreateNoWindow = true });
    }

    internal static string BuildSwapScript(int pid, string oldExe, string newExe)
    {
        static string Q(string s) => s.Replace("'", "''");
        return $$"""
            $oldPid = {{pid}}
            $oldExe = '{{Q(oldExe)}}'
            $newExe = '{{Q(newExe)}}'
            $deadline = (Get-Date).AddSeconds(15)
            while ((Get-Process -Id $oldPid -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
                Start-Sleep -Milliseconds 300
            }
            Start-Sleep -Seconds 1
            try {
                Copy-Item $newExe $oldExe -Force -ErrorAction Stop
            } catch {
                $backup = "$oldExe.old"
                Move-Item $oldExe $backup -Force -ErrorAction SilentlyContinue
                Copy-Item $newExe $oldExe -Force
                Remove-Item $backup -Force -ErrorAction SilentlyContinue
            }
            Start-Process $oldExe
            Remove-Item $newExe -Force -ErrorAction SilentlyContinue
            Remove-Item $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue

            """;
    }
}

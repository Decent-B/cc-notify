using Microsoft.Win32;
using CcNotify.Core.Autostart;
using CcNotify.Core.Settings;
using CcNotify.Core.Updates;
using CcNotify.Core.VsCode;
using Xunit;

namespace CcNotify.Core.Tests;

public class VsCodeUriTests
{
    [Fact]
    public void Windows_path() =>
        Assert.Equal("vscode://file/C:/my%20proj/app", VsCodeLauncher.BuildUri(@"C:\my proj\app", null));

    [Fact]
    public void Wsl_path_needs_a_distro()
    {
        Assert.Null(VsCodeLauncher.BuildUri("/home/u/p", null));
        Assert.Equal("vscode://vscode-remote/wsl+Ubuntu-24.04/home/u/p", VsCodeLauncher.BuildUri("/home/u/p", "Ubuntu-24.04"));
    }

    [Theory]
    [InlineData("")]
    [InlineData("--reuse-window")]
    [InlineData("relative/path")]
    public void Non_absolute_paths_are_rejected(string cwd) => Assert.Null(VsCodeLauncher.BuildUri(cwd, "Ubuntu"));

    [Theory]
    [InlineData(@"C:\a\proj\", "proj")]
    [InlineData("/home/u/proj", "proj")]
    [InlineData("", null)]
    public void Leaf_name(string path, string? leaf) => Assert.Equal(leaf, VsCodeWindows.LeafName(path));
}

public class UpdateTests
{
    [Theory]
    [InlineData("v0.2.1", "0.2.0", true)]
    [InlineData("v0.10.0", "0.9.0", true)]
    [InlineData("v0.2.0", "0.2.0", false)]
    [InlineData("garbage", "0.2.0", false)]
    public void IsNewer(string tag, string current, bool expected) =>
        Assert.Equal(expected, UpdateService.IsNewer(tag, current));

    [Theory]
    [InlineData("cc-notify.exe", true)]
    [InlineData("cc-notify-0.2.0-windows-x64.exe", true)]
    [InlineData("SHA256SUMS.txt", false)]
    [InlineData(null, false)]
    public void Picks_the_exe_asset(string? name, bool expected) => Assert.Equal(expected, UpdateService.IsExeAsset(name));

    [Fact]
    public void Swap_script_escapes_single_quotes()
    {
        var s = UpdateService.BuildSwapScript(42, @"C:\Users\O'Neil\cc-notify.exe", @"C:\t\n.exe");
        Assert.Contains(@"$oldExe = 'C:\Users\O''Neil\cc-notify.exe'", s);
        Assert.Contains("$oldPid = 42", s);
    }
}

public class SettingsTests
{
    private static AppPaths TempPaths() => new(Directory.CreateTempSubdirectory().FullName);

    [Fact]
    public void Loads_python_era_config_and_persists_changes()
    {
        var paths = TempPaths();
        File.WriteAllText(paths.Config, """{"port": 1234, "sound_enabled": false, "unknown": 1}""");
        var store = new SettingsStore(paths);
        Assert.Equal(1234, store.Current.Port);
        Assert.False(store.Current.SoundEnabled);

        store.Update(s => s with { Monitor = MonitorTarget.Primary });
        var reloaded = new SettingsStore(paths).Current;
        Assert.Equal(MonitorTarget.Primary, reloaded.Monitor);
        Assert.Contains("\"monitor\": \"primary\"", File.ReadAllText(paths.Config));
    }

    [Fact]
    public void Corrupt_config_falls_back_to_defaults()
    {
        var paths = TempPaths();
        File.WriteAllText(paths.Config, "{ nope");
        Assert.Equal(new AppSettings(), new SettingsStore(paths).Current);
    }

    [Fact]
    public void Token_is_generated_once_and_reuses_python_era_state()
    {
        var paths = TempPaths();
        File.WriteAllText(paths.State, """{"webhook_token":"keepme","hooks_configured_for_version":"0.1.7"}""");
        var state = new AppState(paths);
        Assert.Equal("keepme", state.WebhookToken);
        Assert.Equal("0.1.7", state.HooksConfiguredForVersion);

        var fresh = TempPaths();
        Assert.Equal(64, new AppState(fresh).WebhookToken.Length);
        Assert.Equal(new AppState(fresh).WebhookToken, new AppState(fresh).WebhookToken);
    }
}

public sealed class AutostartTests : IDisposable
{
    private readonly string _run = $@"Software\cc-notify-tests\{Guid.NewGuid():N}\Run";
    private readonly string _approved = $@"Software\cc-notify-tests\{Guid.NewGuid():N}\Approved";
    private readonly SettingsStore _settings = new(new AppPaths(Directory.CreateTempSubdirectory().FullName));

    private AutostartService Make(string exe = @"C:\Program Files\cc notify\cc-notify.exe") =>
        new(_settings, exe, "test", _run, _approved);

    [Fact]
    public void First_run_enables_with_quoted_path_then_respects_the_user()
    {
        var a = Make();
        Assert.Equal(AutostartStatus.Off, a.Status);
        a.Initialize();
        Assert.Equal(AutostartStatus.On, a.Status);
        Assert.Equal("\"C:\\Program Files\\cc notify\\cc-notify.exe\"",
            Registry.CurrentUser.OpenSubKey(_run)!.GetValue("test"));

        a.SetEnabled(false);
        a.Initialize(); // already initialised: must not turn it back on
        Assert.Equal(AutostartStatus.Off, a.Status);
    }

    [Fact]
    public void Windows_disabling_it_is_reported_and_not_overridden()
    {
        var a = Make();
        a.Initialize();
        using (var k = Registry.CurrentUser.CreateSubKey(_approved))
            k.SetValue("test", new byte[] { 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 }, RegistryValueKind.Binary);
        Assert.Equal(AutostartStatus.DisabledBySystem, a.Status);
        a.Initialize();
        Assert.Equal(AutostartStatus.DisabledBySystem, a.Status);
    }

    [Fact]
    public void Moved_exe_is_repaired()
    {
        Make(@"C:\old\cc-notify.exe").Initialize();
        Make(@"C:\new\cc-notify.exe").Initialize();
        Assert.Equal("\"C:\\new\\cc-notify.exe\"", Registry.CurrentUser.OpenSubKey(_run)!.GetValue("test"));
    }

    public void Dispose() => Registry.CurrentUser.DeleteSubKeyTree(@"Software\cc-notify-tests", throwOnMissingSubKey: false);
}

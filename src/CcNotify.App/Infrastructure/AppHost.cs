using System.Diagnostics;
using System.Net;
using System.Reflection;
using CcNotify.Ui.Tray;
using CcNotify.Ui.Views;
using CcNotify.Core.Autostart;
using CcNotify.Core.Displays;
using CcNotify.Core.Hooks;
using CcNotify.Core.Notifications;
using CcNotify.Core.Server;
using CcNotify.Core.Settings;
using CcNotify.Core.Updates;
using CcNotify.Core.VsCode;
using Microsoft.Extensions.Logging;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;

namespace CcNotify.Ui.Infrastructure;

/// <summary>
/// Composition root and lifetime owner: wires the Core services to the WinUI views, starts the
/// webhook server and tray icon, and implements what the settings window may ask for.
/// </summary>
internal sealed class AppHost : ISettingsActions, IDisposable
{
    private const string GitHubUrl = "https://github.com/Decent-B/cc-notify";

    private readonly DispatcherQueue _ui;
    private readonly string _version;
    private readonly ISettingsStore _settings;
    private readonly IAutostartService _autostart;
    private readonly IDisplayProvider _displays = new DisplayProvider();
    private readonly NotificationService _notifications;
    private readonly HookSetupService _hooks;
    private readonly UpdateService _updates;
    private readonly WebhookServer _server;
    private readonly string _iconPath = Path.Combine(AppContext.BaseDirectory, "Assets", "icon.ico");
    private TrayIcon? _tray;
    private SettingsWindow? _settingsWindow;

    public ILogger Log { get; }

    public AppHost(DispatcherQueue ui)
    {
        _ui = ui;
        var paths = AppPaths.Default;
        Log = new FileLogger(paths.Log);
        _version = ReadVersion();

        _settings = new SettingsStore(paths);
        var state = new AppState(paths);
        var runner = new ProcessRunner();
        var wsl = new Wsl(runner);
        var vsCodeWindows = new VsCodeWindows();

        var exe = Environment.ProcessPath ?? throw new InvalidOperationException("Unknown process path");
        _autostart = new AutostartService(_settings, exe);

        _notifications = new NotificationService(
            new NotificationRouter(MessageCatalog.LoadEmbedded()),
            _settings,
            new SystemSoundPlayer(),
            new DisplaySelector(_displays, vsCodeWindows, _settings),
            new VsCodeLauncher(vsCodeWindows, wsl),
            new ToastPresenter(ui, Path.Combine(AppContext.BaseDirectory, "Assets", "notification_images"), Log),
            Log);

        _hooks = new HookSetupService(CreateHookInstallers(paths, wsl), _settings, state, _version);
        _updates = new UpdateService(new HttpClient { Timeout = TimeSpan.FromMinutes(2) }, _version, exe, Log);
        _server = new WebhookServer(_settings.Current.Port, state.WebhookToken, _notifications.Handle, Log);
    }

    public void Start()
    {
        Log.LogInformation("cc-notify {Version} starting", _version);
        Guard("autostart", _autostart.Initialize);

        _tray = new TrayIcon(_settings.Current.Port, _iconPath, new TrayIcon.Actions(
            OpenSettings,
            () => _ = SetupHooksAsync(auto: false),
            () => _ = CheckForUpdatesAsync(),
            InstallUpdate,
            () => Process.Start(new ProcessStartInfo(GitHubUrl) { UseShellExecute = true }),
            Exit), Log);

        SingleInstance.ListenForSecondLaunch(() => _ui.TryEnqueue(OpenSettings));
        _ = StartServerAsync();

        // First launch or first launch after an update: (re)configure Claude Code in the background.
        if (_hooks.NeedsSetup) _ = SetupHooksAsync(auto: true);
    }

    // ── ISettingsActions ──────────────────────────────────────────────────────

    public string VersionText => $"Version {_version}  ·  listening on 127.0.0.1:{_settings.Current.Port}";

    public bool UpdatePending => _updates.Pending is not null;

    public void SendTestNotification() =>
        _notifications.ShowInfo("cc-notify — Test", "Notifications will appear here.");

    public async Task<string> SetupHooksAsync() => await SetupHooksAsync(auto: false);

    public async Task<string> CheckForUpdatesAsync()
    {
        try
        {
            var release = await _updates.CheckAsync();
            _ui.TryEnqueue(() => _tray?.SetPendingUpdate(_updates.Pending?.Tag));
            if (release is null)
            {
                var upToDate = $"You are running the latest version ({_version}).";
                _notifications.ShowInfo("cc-notify — Up to date", upToDate);
                return upToDate;
            }
            var message = $"Version {release.Tag} is available. Click to install automatically.";
            _notifications.ShowInfo("cc-notify — Update available", message, InstallUpdate);
            return message;
        }
        catch (Exception e)
        {
            Log.LogWarning(e, "Update check failed");
            _notifications.ShowInfo("cc-notify — Update check failed", e.Message);
            return $"Update check failed: {e.Message}";
        }
    }

    public async void InstallUpdate()
    {
        if (_updates.Pending is not { } release) return;
        try
        {
            _notifications.ShowInfo("cc-notify — Downloading update…", $"Fetching version {release.Tag}, please wait.");
            await _updates.StartInstallAsync(release);
            _ui.TryEnqueue(Exit); // the helper script swaps the exe and restarts us
        }
        catch (Exception e)
        {
            Log.LogError(e, "Update install failed");
            _notifications.ShowInfo("cc-notify — Update failed", e.Message);
        }
    }

    // ── Internals ─────────────────────────────────────────────────────────────

    private void OpenSettings()
    {
        try
        {
            if (_settingsWindow is null)
            {
                _settingsWindow = new SettingsWindow(_settings, _autostart, _displays, this);
                _settingsWindow.Closed += (_, _) => _settingsWindow = null;
            }
            _settingsWindow.Activate();
        }
        catch (Exception e)
        {
            _settingsWindow = null;
            Log.LogError(e, "Could not open the settings window");
        }
    }

    private async Task StartServerAsync()
    {
        // After a self-update the old process may not have released the port yet: retry briefly.
        for (var attempt = 1; ; attempt++)
        {
            try { _server.Start(); return; }
            catch (HttpListenerException e) when (attempt < 4)
            {
                Log.LogInformation("Port {Port} busy ({Msg}), retrying…", _settings.Current.Port, e.Message);
                await Task.Delay(1000);
            }
            catch (HttpListenerException e)
            {
                Log.LogError(e, "Port {Port} unavailable", _settings.Current.Port);
                _notifications.ShowInfo("cc-notify — Port busy",
                    $"Port {_settings.Current.Port} is in use, so Claude Code events cannot be received.");
                return;
            }
        }
    }

    /// <summary>One popup with the result; setup takes a few seconds, a "working…" popup would only add noise.</summary>
    private async Task<string> SetupHooksAsync(bool auto)
    {
        Log.LogInformation("Hook setup started ({Mode})", auto ? "automatic" : "manual");
        try
        {
            var result = await _hooks.RunAsync();
            _notifications.ShowInfo(
                result.FullyOk ? "Hooks configured — restart Claude Code" : "Hook setup completed with issues",
                result.Summary());
            return result.Summary();
        }
        catch (Exception e)
        {
            Log.LogError(e, "Hook setup crashed");
            _notifications.ShowInfo("Hook setup failed", e.Message);
            return $"Hook setup failed: {e.Message}";
        }
    }

    /// <summary>With CC_NOTIFY_DATA_DIR set (a throwaway copy) hooks go to a fake home, never the real Claude Code.</summary>
    private static IHookInstaller[] CreateHookInstallers(AppPaths paths, IWsl wsl) =>
        Environment.GetEnvironmentVariable("CC_NOTIFY_DATA_DIR") is { Length: > 0 }
            ? [new WindowsHookInstaller(Path.Combine(paths.Root, "home"))]
            : [new WindowsHookInstaller(), new WslHookInstaller(wsl)];

    private void Exit()
    {
        Dispose();
        Application.Current.Exit();
        Environment.Exit(0); // listener/helper threads must not keep the process alive
    }

    private void Guard(string what, Action action)
    {
        try { action(); }
        catch (Exception e) { Log.LogWarning(e, "{What} failed", what); }
    }

    private static string ReadVersion() =>
        (Assembly.GetExecutingAssembly().GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion ?? "0.0.0")
        .Split('+')[0];

    public void Dispose()
    {
        _tray?.Dispose();
        _server.Dispose();
    }
}

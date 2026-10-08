using System.Diagnostics;
using CcNotify.Ui.Infrastructure;
using CcNotify.Core.Autostart;
using CcNotify.Core.Displays;
using CcNotify.Core.Settings;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Graphics;

namespace CcNotify.Ui.Views;

/// <summary>What the settings window can ask the app to do (implemented by <see cref="AppHost"/>).</summary>
internal interface ISettingsActions
{
    string VersionText { get; }
    bool UpdatePending { get; }
    Task<string> SetupHooksAsync();
    Task<string> CheckForUpdatesAsync();
    void InstallUpdate();
    void SendTestNotification();
}

internal sealed partial class SettingsWindow : Window
{
    private sealed record DisplayChoice(MonitorTarget Target, string? Device, string Label)
    {
        public override string ToString() => Label;
    }

    private readonly ISettingsStore _settings;
    private readonly IAutostartService _autostart;
    private readonly IDisplayProvider _displays;
    private readonly ISettingsActions _actions;
    private bool _loading;

    public SettingsWindow(ISettingsStore settings, IAutostartService autostart, IDisplayProvider displays, ISettingsActions actions)
    {
        _settings = settings;
        _autostart = autostart;
        _displays = displays;
        _actions = actions;

        InitializeComponent();
        Title = "cc-notify settings";
        SystemBackdrop = new Microsoft.UI.Xaml.Media.MicaBackdrop();
        VersionText.Text = actions.VersionText;
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "icon.ico"));
        AppWindow.Resize(new SizeInt32((int)(600 * this.Scale()), (int)(780 * this.Scale())));

        Activated += (_, _) => Refresh(); // the user may have changed Windows Settings meanwhile
        Refresh();
    }

    /// <summary>Re-reads everything from the services; the controls never hold state of their own.</summary>
    public void Refresh()
    {
        _loading = true;
        try
        {
            var s = _settings.Current;
            var status = _autostart.Status;
            AutostartSwitch.IsOn = status == AutostartStatus.On;
            AutostartBlockedBar.IsOpen = status == AutostartStatus.DisabledBySystem;
            SoundSwitch.IsOn = s.SoundEnabled;
            StopBox.IsChecked = s.NotifyOnStop;
            PermissionBox.IsChecked = s.NotifyOnPermission;
            IdleBox.IsChecked = s.NotifyOnIdle;
            FailureBox.IsChecked = s.NotifyOnStopFailure;
            InstallButton.Visibility = _actions.UpdatePending ? Visibility.Visible : Visibility.Collapsed;
            LoadDisplayChoices(s);
        }
        finally { _loading = false; }
    }

    private void LoadDisplayChoices(AppSettings s)
    {
        var choices = new List<DisplayChoice>
        {
            new(MonitorTarget.FollowVsCode, null, "Follow VS Code (recommended)"),
            new(MonitorTarget.FollowCursor, null, "Follow the mouse cursor"),
            new(MonitorTarget.Primary, null, "Always the primary display"),
        };
        var all = _displays.GetAll();
        for (var i = 0; i < all.Count; i++)
            choices.Add(new(MonitorTarget.Specific, all[i].DeviceName, all[i].Label(i)));

        DisplayBox.ItemsSource = choices;
        DisplayBox.SelectedItem =
            choices.FirstOrDefault(c => c.Target == s.Monitor && c.Device == (s.Monitor == MonitorTarget.Specific ? s.MonitorDeviceName : null))
            ?? choices[0];
    }

    private void OnAutostartToggled(object s, RoutedEventArgs e)
    {
        if (_loading) return;
        _autostart.SetEnabled(AutostartSwitch.IsOn);
        Refresh();
    }

    private void OnOpenStartupSettings(object s, RoutedEventArgs e) =>
        Process.Start(new ProcessStartInfo("ms-settings:startupapps") { UseShellExecute = true });

    private void OnSoundToggled(object s, RoutedEventArgs e)
    {
        if (!_loading) _settings.Update(x => x with { SoundEnabled = SoundSwitch.IsOn });
    }

    private void OnEventToggled(object s, RoutedEventArgs e) =>
        _settings.Update(x => x with
        {
            NotifyOnStop = StopBox.IsChecked == true,
            NotifyOnPermission = PermissionBox.IsChecked == true,
            NotifyOnIdle = IdleBox.IsChecked == true,
            NotifyOnStopFailure = FailureBox.IsChecked == true,
        });

    private void OnDisplayChanged(object s, SelectionChangedEventArgs e)
    {
        if (_loading || DisplayBox.SelectedItem is not DisplayChoice c) return;
        _settings.Update(x => x with { Monitor = c.Target, MonitorDeviceName = c.Device });
    }

    private void OnTestNotification(object s, RoutedEventArgs e) => _actions.SendTestNotification();

    private async void OnSetupHooks(object s, RoutedEventArgs e) =>
        await RunBusy(HooksButton, "Setting up hooks…", _actions.SetupHooksAsync);

    private async void OnCheckUpdates(object s, RoutedEventArgs e)
    {
        await RunBusy(UpdateButton, "Checking for updates…", _actions.CheckForUpdatesAsync);
        Refresh();
    }

    private void OnInstallUpdate(object s, RoutedEventArgs e) => _actions.InstallUpdate();

    private async Task RunBusy(Button button, string busyText, Func<Task<string>> work)
    {
        button.IsEnabled = false;
        StatusText.Text = busyText;
        try { StatusText.Text = await work(); }
        finally { button.IsEnabled = true; }
    }
}

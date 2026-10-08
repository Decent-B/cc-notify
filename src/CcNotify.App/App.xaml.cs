using CcNotify.Ui.Infrastructure;
using Microsoft.Extensions.Logging;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;

namespace CcNotify.Ui;

/// <summary>A tray-only app: no main window, everything hangs off <see cref="AppHost"/>.</summary>
public partial class App : Application
{
    private AppHost? _host;

    public App()
    {
        InitializeComponent();
        UnhandledException += (_, e) =>
        {
            _host?.Log.LogError(e.Exception, "Unhandled exception");
            e.Handled = true;
        };
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        // Application.Start defaults to exiting when the last XAML window closes. Our windows are
        // short-lived popups, so the tray app would quit ~10 s after the first one; only Exit stops us.
        DispatcherShutdownMode = DispatcherShutdownMode.OnExplicitShutdown;
        _host = new AppHost(DispatcherQueue.GetForCurrentThread());
        _host.Start();
    }
}

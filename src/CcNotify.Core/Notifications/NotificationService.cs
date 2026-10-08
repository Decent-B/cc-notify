using CcNotify.Core.Displays;
using CcNotify.Core.Settings;
using CcNotify.Core.VsCode;
using Microsoft.Extensions.Logging;

namespace CcNotify.Core.Notifications;

/// <summary>Draws a notification popup on the given display. Implemented by the UI layer.</summary>
public interface IToastPresenter
{
    /// <summary>May be called from any thread. <paramref name="display"/> is null when no display could be resolved.</summary>
    void Show(Notification notification, DisplayInfo? display);
}

/// <summary>
/// The notification pipeline: hook event → router → sound → target display → popup.
/// Each step is an injected collaborator, so the UI layer only has to draw.
/// </summary>
public sealed class NotificationService
{
    private readonly NotificationRouter _router;
    private readonly ISettingsStore _settings;
    private readonly ISoundPlayer _sound;
    private readonly DisplaySelector _displays;
    private readonly IVsCodeLauncher _vsCode;
    private readonly IToastPresenter _presenter;
    private readonly ILogger _log;

    public NotificationService(NotificationRouter router, ISettingsStore settings, ISoundPlayer sound,
        DisplaySelector displays, IVsCodeLauncher vsCode, IToastPresenter presenter, ILogger log)
    {
        _router = router;
        _settings = settings;
        _sound = sound;
        _displays = displays;
        _vsCode = vsCode;
        _presenter = presenter;
        _log = log;
    }

    public void Handle(HookEvent e)
    {
        if (_router.Route(e, _settings.Current) is { } n) Show(n);
    }

    /// <summary>For app-originated messages (setup results, updates, test popup).</summary>
    public void ShowInfo(string title, string body, Action? onClick = null) =>
        Show(new Notification(NotificationKind.Info, title, body, OnClick: onClick));

    private void Show(Notification n)
    {
        try
        {
            if (n.OnClick is null && n.Cwd is { } cwd)
                n = n with { OnClick = () => _ = FocusAsync(cwd) };
            if (_settings.Current.SoundEnabled) _sound.Play(n.Kind);
            _presenter.Show(n, _displays.Select(n.Cwd));
        }
        catch (Exception ex)
        {
            // A broken popup must never take down the webhook server.
            _log.LogWarning(ex, "Failed to show notification {Title}", n.Title);
        }
    }

    private async Task FocusAsync(string cwd)
    {
        try { await _vsCode.FocusAsync(cwd); }
        catch (Exception ex) { _log.LogWarning(ex, "Could not focus VS Code for {Cwd}", cwd); }
    }
}

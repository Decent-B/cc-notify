using CcNotify.Core.Settings;
using CcNotify.Core.VsCode;

namespace CcNotify.Core.Displays;

/// <summary>Decides which display a popup appears on, from the user's <see cref="MonitorTarget"/> setting.</summary>
public sealed class DisplaySelector
{
    private readonly IDisplayProvider _displays;
    private readonly IVsCodeWindows _vsCode;
    private readonly ISettingsStore _settings;

    public DisplaySelector(IDisplayProvider displays, IVsCodeWindows vsCode, ISettingsStore settings)
    {
        _displays = displays;
        _vsCode = vsCode;
        _settings = settings;
    }

    public DisplayInfo? Select(string? cwd)
    {
        var s = _settings.Current;
        var all = _displays.GetAll();
        var primary = all.FirstOrDefault(d => d.IsPrimary) ?? all.FirstOrDefault();

        var picked = s.Monitor switch
        {
            MonitorTarget.Primary => primary,
            MonitorTarget.FollowCursor => _displays.FromCursor(),
            MonitorTarget.Specific => all.FirstOrDefault(d => d.DeviceName == s.MonitorDeviceName),
            _ => FromVsCode(cwd) ?? _displays.FromCursor(),
        };
        // A saved monitor can be unplugged; never fail to show a notification because of it.
        return picked ?? _displays.FromCursor() ?? primary;
    }

    private DisplayInfo? FromVsCode(string? cwd) =>
        _vsCode.Find(cwd) is { } hwnd ? _displays.FromWindow(hwnd) : null;
}

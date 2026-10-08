using CcNotify.Core.Native;

namespace CcNotify.Core.Displays;

public interface IDisplayProvider
{
    IReadOnlyList<DisplayInfo> GetAll();
    DisplayInfo? FromWindow(IntPtr hwnd);
    DisplayInfo? FromCursor();
}

/// <summary>Enumerates monitors through Win32 (per-monitor DPI aware).</summary>
public sealed class DisplayProvider : IDisplayProvider
{
    public IReadOnlyList<DisplayInfo> GetAll()
    {
        var list = new List<DisplayInfo>();
        NativeMethods.EnumDisplayMonitors(IntPtr.Zero, IntPtr.Zero, (m, _, _, _) =>
        {
            if (Describe(m) is { } d) list.Add(d);
            return true;
        }, IntPtr.Zero);
        // Primary first, then left-to-right, so the picker order is stable and predictable.
        return list.OrderByDescending(d => d.IsPrimary).ThenBy(d => d.Bounds.X).ToList();
    }

    public DisplayInfo? FromWindow(IntPtr hwnd) =>
        Describe(NativeMethods.MonitorFromWindow(hwnd, NativeMethods.MonitorDefaultToNearest));

    public DisplayInfo? FromCursor() =>
        NativeMethods.GetCursorPos(out var p)
            ? Describe(NativeMethods.MonitorFromPoint(p, NativeMethods.MonitorDefaultToNearest))
            : null;

    private static DisplayInfo? Describe(IntPtr monitor)
    {
        if (monitor == IntPtr.Zero) return null;
        var info = new MonitorInfoEx { Size = System.Runtime.InteropServices.Marshal.SizeOf<MonitorInfoEx>() };
        if (!NativeMethods.GetMonitorInfoW(monitor, ref info)) return null;
        // 0 = MDT_EFFECTIVE_DPI; fall back to 96 if the call fails.
        uint dpi = NativeMethods.GetDpiForMonitor(monitor, 0, out var x, out _) == 0 ? x : 96;
        return new DisplayInfo(
            info.DeviceName, ToRect(info.Monitor), ToRect(info.Work),
            (info.Flags & NativeMethods.MonitorInfoPrimary) != 0, dpi);
    }

    private static PixelRect ToRect(NativeRect r) => new(r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top);
}

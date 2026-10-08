using System.Diagnostics;
using CcNotify.Core.Native;

namespace CcNotify.Core.VsCode;

public interface IVsCodeWindows
{
    /// <summary>Topmost visible VS Code window, preferring one whose title mentions the project folder.</summary>
    IntPtr? Find(string? cwd);

    /// <summary>Brings the window forward, un-minimising it. Windows 11 also switches virtual desktop.</summary>
    void Activate(IntPtr hwnd);
}

public sealed class VsCodeWindows : IVsCodeWindows
{
    private const string TitleMarker = "Visual Studio Code";

    public IntPtr? Find(string? cwd)
    {
        var folder = LeafName(cwd);
        IntPtr? any = null, match = null;

        NativeMethods.EnumWindows((hwnd, _) =>
        {
            if (!NativeMethods.IsWindowVisible(hwnd)) return true;
            var title = Title(hwnd);
            if (!title.Contains(TitleMarker, StringComparison.Ordinal)) return true;
            any ??= hwnd;
            if (folder is not null && title.Contains(folder, StringComparison.OrdinalIgnoreCase))
            {
                match = hwnd;
                return false;
            }
            return true; // EnumWindows is Z-ordered; keep looking for a better match
        }, IntPtr.Zero);

        return match ?? any;
    }

    public void Activate(IntPtr hwnd)
    {
        if (NativeMethods.IsIconic(hwnd)) NativeMethods.ShowWindow(hwnd, NativeMethods.ShowRestore);
        NativeMethods.SetForegroundWindow(hwnd);
    }

    internal static string? LeafName(string? path)
    {
        if (string.IsNullOrWhiteSpace(path)) return null;
        var leaf = path.TrimEnd('/', '\\').Split('/', '\\').LastOrDefault();
        return string.IsNullOrEmpty(leaf) ? null : leaf;
    }

    private static string Title(IntPtr hwnd)
    {
        var len = NativeMethods.GetWindowTextLengthW(hwnd);
        if (len == 0) return "";
        var buf = new char[len + 1];
        return new string(buf, 0, NativeMethods.GetWindowTextW(hwnd, buf, buf.Length));
    }
}

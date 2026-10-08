using System.Runtime.InteropServices;
using Microsoft.UI.Xaml;
using WinRT.Interop;

namespace CcNotify.Ui.Infrastructure;

internal static class WindowHelpers
{
    private const int GwlExStyle = -20;
    private const long WsExToolWindow = 0x80, WsExNoActivate = 0x08000000;

    [DllImport("user32.dll")] private static extern uint GetDpiForWindow(IntPtr hwnd);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] private static extern IntPtr GetWindowLongPtr(IntPtr hwnd, int index);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] private static extern IntPtr SetWindowLongPtr(IntPtr hwnd, int index, IntPtr value);

    public static IntPtr Handle(this Window window) => WindowNative.GetWindowHandle(window);

    public static double Scale(this Window window) => GetDpiForWindow(window.Handle()) / 96.0;

    /// <summary>Hides the window from Alt-Tab/taskbar and stops clicks from stealing focus from what the user is typing in.</summary>
    public static void MakeNonActivatingOverlay(this Window window)
    {
        var hwnd = window.Handle();
        var style = GetWindowLongPtr(hwnd, GwlExStyle).ToInt64();
        SetWindowLongPtr(hwnd, GwlExStyle, (IntPtr)(style | WsExToolWindow | WsExNoActivate));
    }
}

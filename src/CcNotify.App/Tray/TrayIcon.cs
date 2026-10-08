using System.Runtime.InteropServices;
using Microsoft.Extensions.Logging;

namespace CcNotify.Ui.Tray;

/// <summary>
/// The system tray icon and its context menu, on plain Win32 <c>Shell_NotifyIcon</c>.
/// Owns a hidden window (created on the UI thread, whose message loop drives it) that receives
/// the icon's mouse messages and Explorer's "TaskbarCreated" broadcast, so the icon comes back
/// after Explorer restarts. Pure UI: every menu entry calls back into the app.
/// </summary>
internal sealed class TrayIcon : IDisposable
{
    public sealed record Actions(
        Action OpenSettings, Action SetupHooks, Action CheckUpdates, Action InstallUpdate, Action OpenGitHub, Action Exit);

    private const uint CallbackMessage = 0x8000 + 1; // WM_APP + 1
    private const string WindowClass = "cc-notify.tray";

    private readonly Actions _actions;
    private readonly ILogger _log;
    private readonly string _tooltip;
    private readonly string _portLabel;
    private readonly IntPtr _hwnd;
    private readonly IntPtr _icon;
    private readonly uint _taskbarCreated;
    private readonly WndProc _wndProc; // must stay referenced: the OS calls it through a function pointer
    private string? _pendingUpdateTag;
    private bool _added;

    public TrayIcon(int port, string iconPath, Actions actions, ILogger log)
    {
        _actions = actions;
        _log = log;
        _tooltip = $"Claude Code Notifier  |  :{port}";
        _portLabel = $"Listening on :{port}";
        _wndProc = OnMessage;
        _taskbarCreated = RegisterWindowMessageW("TaskbarCreated");

        var wc = new WndClassEx
        {
            Size = (uint)Marshal.SizeOf<WndClassEx>(),
            WndProc = Marshal.GetFunctionPointerForDelegate(_wndProc),
            Instance = GetModuleHandleW(null),
            ClassName = WindowClass,
        };
        if (RegisterClassExW(ref wc) == 0) throw new System.ComponentModel.Win32Exception();
        // A hidden top-level window, not a message-only one: only top-level windows get TaskbarCreated.
        _hwnd = CreateWindowExW(0, WindowClass, WindowClass, 0, 0, 0, 0, 0, IntPtr.Zero, IntPtr.Zero, wc.Instance, IntPtr.Zero);
        if (_hwnd == IntPtr.Zero) throw new System.ComponentModel.Win32Exception();
        _icon = LoadImageW(IntPtr.Zero, iconPath, ImageIcon, GetSystemMetrics(SmCxSmIcon), GetSystemMetrics(SmCySmIcon), LrLoadFromFile);
        Add();
    }

    /// <summary>Shows an "Install update" entry in the menu (null removes it).</summary>
    public void SetPendingUpdate(string? tag) => _pendingUpdateTag = tag;

    private void Add()
    {
        var data = Data(NifMessage | NifIcon | NifTip);
        _added = Shell_NotifyIconW(NimAdd, ref data);
        _log.LogInformation("Tray icon {Result}", _added ? "added" : "could not be added");
    }

    private NotifyIconData Data(uint flags) => new()
    {
        Size = (uint)Marshal.SizeOf<NotifyIconData>(),
        Hwnd = _hwnd,
        Id = 1,
        Flags = flags,
        CallbackMessage = CallbackMessage,
        Icon = _icon,
        Tip = _tooltip,
    };

    private IntPtr OnMessage(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam)
    {
        if (msg == CallbackMessage)
        {
            _log.LogDebug("Tray event 0x{Event:X}", (uint)lParam.ToInt64());
            switch ((uint)lParam.ToInt64())
            {
                case WmLButtonUp: _actions.OpenSettings(); break;
                case WmRButtonUp: ShowMenu(); break;
            }
            return IntPtr.Zero;
        }
        if (msg == _taskbarCreated) Add(); // Explorer restarted: our icon is gone, add it again
        return DefWindowProcW(hwnd, msg, wParam, lParam);
    }

    private void ShowMenu()
    {
        var items = new List<(string Text, Action? Run)>
        {
            ("Claude Code Notifier", null),
            (_portLabel, null),
            ("-", null),
        };
        if (_pendingUpdateTag is { } tag) items.AddRange([($"Install update {tag}", _actions.InstallUpdate), ("-", null)]);
        items.AddRange([
            ("Settings…", _actions.OpenSettings),
            ("Set up Claude Code hooks…", _actions.SetupHooks),
            ("Check for updates", _actions.CheckUpdates),
            ("-", null),
            ("Open GitHub", _actions.OpenGitHub),
            ("-", null),
            ("Exit", _actions.Exit),
        ]);

        var menu = CreatePopupMenu();
        for (var i = 0; i < items.Count; i++)
        {
            var (text, run) = items[i];
            if (text == "-") AppendMenuW(menu, MfSeparator, 0, null);
            else AppendMenuW(menu, run is null ? MfGrayed : MfString, (uint)(i + 1), text);
        }

        GetCursorPos(out var pt);
        // Required so the menu closes when the user clicks elsewhere (documented TrackPopupMenu quirk).
        SetForegroundWindow(_hwnd);
        var chosen = TrackPopupMenu(menu, TpmReturnCmd | TpmRightButton, pt.X, pt.Y, 0, _hwnd, IntPtr.Zero);
        PostMessageW(_hwnd, 0, IntPtr.Zero, IntPtr.Zero);
        _log.LogInformation("Tray menu closed, choice {Choice}", chosen);
        DestroyMenu(menu);

        if (chosen > 0) items[chosen - 1].Run?.Invoke();
    }

    public void Dispose()
    {
        if (_added)
        {
            var data = Data(0);
            Shell_NotifyIconW(NimDelete, ref data);
            _added = false;
        }
        if (_icon != IntPtr.Zero) DestroyIcon(_icon);
        DestroyWindow(_hwnd);
    }

    // ── Win32 ────────────────────────────────────────────────────────────────

    private const uint NimAdd = 0, NimDelete = 2;
    private const uint NifMessage = 1, NifIcon = 2, NifTip = 4;
    private const uint WmLButtonUp = 0x0202, WmRButtonUp = 0x0205;
    private const uint MfString = 0, MfGrayed = 1, MfSeparator = 0x800;
    private const uint TpmRightButton = 0x2, TpmReturnCmd = 0x100;
    private const uint ImageIcon = 1, LrLoadFromFile = 0x10;
    private const int SmCxSmIcon = 49, SmCySmIcon = 50;

    private delegate IntPtr WndProc(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WndClassEx
    {
        public uint Size, Style;
        public IntPtr WndProc;
        public int ClsExtra, WndExtra;
        public IntPtr Instance, Icon, Cursor, Background;
        public string? MenuName;
        public string ClassName;
        public IntPtr IconSmall;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct NotifyIconData
    {
        public uint Size;
        public IntPtr Hwnd;
        public uint Id, Flags, CallbackMessage;
        public IntPtr Icon;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Tip;
        public uint State, StateMask;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string Info;
        public uint TimeoutOrVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string InfoTitle;
        public uint InfoFlags;
        public Guid Guid;
        public IntPtr BalloonIcon;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Point { public int X, Y; }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)] private static extern bool Shell_NotifyIconW(uint message, ref NotifyIconData data);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern ushort RegisterClassExW(ref WndClassEx wc);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern IntPtr CreateWindowExW(uint exStyle, string cls, string name, uint style, int x, int y, int w, int h, IntPtr parent, IntPtr menu, IntPtr instance, IntPtr param);
    [DllImport("user32.dll")] private static extern bool DestroyWindow(IntPtr hwnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr DefWindowProcW(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern uint RegisterWindowMessageW(string name);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr LoadImageW(IntPtr instance, string name, uint type, int cx, int cy, uint flags);
    [DllImport("user32.dll")] private static extern bool DestroyIcon(IntPtr icon);
    [DllImport("user32.dll")] private static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")] private static extern IntPtr CreatePopupMenu();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern bool AppendMenuW(IntPtr menu, uint flags, uint id, string? text);
    [DllImport("user32.dll")] private static extern int TrackPopupMenu(IntPtr menu, uint flags, int x, int y, int reserved, IntPtr hwnd, IntPtr rect);
    [DllImport("user32.dll")] private static extern bool DestroyMenu(IntPtr menu);
    [DllImport("user32.dll")] private static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern bool PostMessageW(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr GetModuleHandleW(string? name);
}

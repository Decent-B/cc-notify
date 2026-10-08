using System.Runtime.InteropServices;

namespace CcNotify.Ui.Infrastructure;

/// <summary>Named mutex for "am I the only instance", named event for "second launch → wake the first".</summary>
internal static class SingleInstance
{
    private const string MutexName = @"Local\cc-notify.instance";
    private const string EventName = @"Local\cc-notify.show-settings";

    private static Mutex? _mutex;

    public static bool TryBecomePrimary()
    {
        _mutex = new Mutex(initiallyOwned: true, MutexName, out var created);
        return created;
    }

    [DllImport("user32.dll")] private static extern bool AllowSetForegroundWindow(int processId);

    public static void NotifyPrimary()
    {
        // This process was just started by the user, so it may hand foreground rights to the
        // running instance; otherwise Windows would only flash the settings window's taskbar button.
        AllowSetForegroundWindow(-1); // ASFW_ANY
        using var evt = new EventWaitHandle(false, EventResetMode.AutoReset, EventName);
        evt.Set();
    }

    /// <summary>Runs <paramref name="onSecondLaunch"/> (on a worker thread) whenever another instance is started.</summary>
    public static void ListenForSecondLaunch(Action onSecondLaunch)
    {
        var evt = new EventWaitHandle(false, EventResetMode.AutoReset, EventName);
        new Thread(() => { while (evt.WaitOne()) onSecondLaunch(); })
        { IsBackground = true, Name = "single-instance" }.Start();
    }
}

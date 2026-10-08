using CcNotify.Core.Native;

namespace CcNotify.Core.Notifications;

public interface ISoundPlayer { void Play(NotificationKind kind); }

/// <summary>Plays the user's own Windows system sounds (respects their sound scheme).</summary>
public sealed class SystemSoundPlayer : ISoundPlayer
{
    private const uint Alias = 0x10000, Async = 0x1;

    public void Play(NotificationKind kind)
    {
        var alias = kind is NotificationKind.Permission or NotificationKind.Failure
            ? "SystemExclamation"
            : "SystemAsterisk";
        NativeMethods.PlaySoundW(alias, IntPtr.Zero, Alias | Async);
    }
}

namespace CcNotify.Core.Settings;

/// <summary>Which display a notification popup appears on.</summary>
public enum MonitorTarget
{
    /// <summary>The display holding the VS Code window; falls back to the cursor's display.</summary>
    FollowVsCode,
    FollowCursor,
    Primary,
    /// <summary>The display named by <see cref="AppSettings.MonitorDeviceName"/>.</summary>
    Specific,
}

/// <summary>User-editable settings (config.json). Immutable; change with <c>with</c>.</summary>
public sealed record AppSettings
{
    public int Port { get; init; } = 9876;
    public bool SoundEnabled { get; init; } = true;
    public bool NotifyOnStop { get; init; } = true;
    public bool NotifyOnStopFailure { get; init; } = true;
    public bool NotifyOnPermission { get; init; } = true;
    public bool NotifyOnIdle { get; init; } = true;
    public MonitorTarget Monitor { get; init; } = MonitorTarget.FollowVsCode;
    public string? MonitorDeviceName { get; init; }

    /// <summary>Set once the start-with-Windows default has been applied, so the user's choice sticks.</summary>
    public bool AutostartInitialized { get; init; }
}

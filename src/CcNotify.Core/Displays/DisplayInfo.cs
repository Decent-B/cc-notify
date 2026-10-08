namespace CcNotify.Core.Displays;

public readonly record struct PixelRect(int X, int Y, int Width, int Height);

/// <summary>A monitor as the OS reports it, in physical pixels.</summary>
public sealed record DisplayInfo(string DeviceName, PixelRect Bounds, PixelRect WorkArea, bool IsPrimary, uint Dpi)
{
    public double Scale => Dpi / 96.0;

    /// <summary>Human readable label for the settings picker, e.g. "Display 2 (1920×1080)".</summary>
    public string Label(int index) =>
        $"Display {index + 1}{(IsPrimary ? " — primary" : "")} ({Bounds.Width}×{Bounds.Height})";
}

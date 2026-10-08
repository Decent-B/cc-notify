using CcNotify.Ui.Infrastructure;
using CcNotify.Core.Displays;
using CcNotify.Core.Notifications;
using Microsoft.Extensions.Logging;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Windowing;
using Windows.Graphics;

namespace CcNotify.Ui.Views;

/// <summary>Stacks toasts in the bottom-right corner of whichever display they were routed to.</summary>
internal sealed class ToastPresenter : IToastPresenter
{
    private const int MaxPerDisplay = 4;
    private const double MarginDip = 16, GapDip = 10;

    private readonly DispatcherQueue _ui;
    private readonly string _imageDir;
    private readonly ILogger _log;
    private readonly Dictionary<string, Stack> _stacks = new();

    private sealed class Stack
    {
        public DisplayInfo Display = null!;
        public readonly List<ToastWindow> Toasts = new();
    }

    public ToastPresenter(DispatcherQueue ui, string imageDir, ILogger log)
    {
        _log = log;
        _ui = ui;
        _imageDir = imageDir;
    }

    public void Show(Notification notification, DisplayInfo? display) =>
        _ui.TryEnqueue(() => ShowOnUi(notification, display ?? PrimaryFallback()));

    private void ShowOnUi(Notification n, DisplayInfo display)
    {
        if (!_stacks.TryGetValue(display.DeviceName, out var stack))
            _stacks[display.DeviceName] = stack = new Stack();
        stack.Display = display;

        if (stack.Toasts.Count >= MaxPerDisplay) stack.Toasts[0].Dismiss();

        var toast = new ToastWindow(n, RandomImage());
        stack.Toasts.Add(toast);
        toast.Dismissed += (_, _) => { stack.Toasts.Remove(toast); Layout(stack); };
        Layout(stack);
    }

    /// <summary>Newest toast sits in the corner; older ones are pushed up.</summary>
    private void Layout(Stack stack)
    {
        var d = stack.Display;
        var scale = d.Scale;
        var width = (int)Math.Round(ToastWindow.WidthDip * scale);
        var margin = (int)Math.Round(MarginDip * scale);
        var gap = (int)Math.Round(GapDip * scale);

        var x = d.WorkArea.X + d.WorkArea.Width - width - margin;
        var bottom = d.WorkArea.Y + d.WorkArea.Height - margin;
        for (var i = stack.Toasts.Count - 1; i >= 0; i--)
        {
            var toast = stack.Toasts[i];
            var height = (int)Math.Round(toast.MeasureHeightDip() * scale);
            bottom -= height;
            _log.LogInformation("toast {Index}/{Count} on {Display} at {X},{Y} {W}x{H}", i, stack.Toasts.Count, d.DeviceName, x, bottom, width, height);
            toast.Place(new RectInt32(x, bottom, width, height));
            bottom -= gap;
        }
    }

    private string? RandomImage()
    {
        try
        {
            var files = Directory.GetFiles(_imageDir, "*.png");
            return files.Length == 0 ? null : files[Random.Shared.Next(files.Length)];
        }
        catch (IOException) { return null; }
        catch (UnauthorizedAccessException) { return null; }
    }

    private static DisplayInfo PrimaryFallback()
    {
        var a = DisplayArea.Primary;
        static PixelRect R(RectInt32 r) => new(r.X, r.Y, r.Width, r.Height);
        return new DisplayInfo("primary", R(a.OuterBounds), R(a.WorkArea), true, 96);
    }
}

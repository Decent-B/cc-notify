using CcNotify.Ui.Infrastructure;
using CcNotify.Core.Notifications;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Foundation;
using Windows.Graphics;
using Windows.UI;

namespace CcNotify.Ui.Views;

/// <summary>
/// One borderless, always-on-top, non-activating popup. It is placed (and re-placed as other toasts
/// come and go) by <see cref="ToastPresenter"/>; clicking it runs the notification's action.
/// </summary>
internal sealed partial class ToastWindow : Window
{
    public const double WidthDip = 380;
    private static readonly TimeSpan Lifetime = TimeSpan.FromSeconds(10);

    private readonly DispatcherTimer _timer = new() { Interval = Lifetime };
    private readonly Action? _onClick;
    private RectInt32 _target;
    private bool _shown;

    public ToastWindow(Notification n, string? heroImagePath)
    {
        InitializeComponent();
        _onClick = n.OnClick;

        TitleText.Text = n.Title;
        BodyText.Text = n.Body;
        AccentBar.Background = new SolidColorBrush(AccentFor(n.Kind));
        if (heroImagePath is not null)
        {
            Hero.Source = new BitmapImage(new Uri(heroImagePath)) { DecodePixelWidth = 760 };
            Hero.Visibility = Visibility.Visible;
        }

        var presenter = OverlappedPresenter.Create();
        presenter.SetBorderAndTitleBar(false, false);
        presenter.IsResizable = false;
        presenter.IsMaximizable = false;
        presenter.IsMinimizable = false;
        presenter.IsAlwaysOnTop = true;
        AppWindow.SetPresenter(presenter);
        AppWindow.IsShownInSwitchers = false;
        SystemBackdrop = new DesktopAcrylicBackdrop();
        this.MakeNonActivatingOverlay();

        _timer.Tick += (_, _) => Dismiss();
        Closed += (_, _) => { _timer.Stop(); Dismissed?.Invoke(this, EventArgs.Empty); };
    }

    public event EventHandler? Dismissed;

    /// <summary>Height in device-independent pixels at the fixed toast width.</summary>
    public double MeasureHeightDip()
    {
        var root = (FrameworkElement)Content;
        root.Measure(new Size(WidthDip, double.PositiveInfinity));
        return Math.Ceiling(root.DesiredSize.Height);
    }

    /// <summary>Moves/resizes in physical pixels; the first call also shows the window without taking focus.</summary>
    public void Place(RectInt32 rect)
    {
        _target = rect;
        AppWindow.MoveAndResize(rect);
        if (_shown) return;
        _shown = true;
        AppWindow.Show(activateWindow: false);
        _timer.Start();
        // Crossing onto a monitor with a different DPI can rescale the window; settle it once more
        // (using the latest target, which may have moved on in the meantime).
        DispatcherQueue.TryEnqueue(() => AppWindow.MoveAndResize(_target));
    }

    public void Dismiss() => Close();

    private void OnPointerEntered(object s, PointerRoutedEventArgs e) => _timer.Stop();
    private void OnPointerExited(object s, PointerRoutedEventArgs e) => _timer.Start();

    private void OnTapped(object s, TappedRoutedEventArgs e)
    {
        try { _onClick?.Invoke(); }
        finally { Dismiss(); }
    }

    private void OnCloseTapped(object s, TappedRoutedEventArgs e) => e.Handled = true;
    private void OnCloseClick(object s, RoutedEventArgs e) => Dismiss();

    private static Color AccentFor(NotificationKind kind) => kind switch
    {
        NotificationKind.Permission => Color.FromArgb(255, 255, 185, 0),
        NotificationKind.Failure => Color.FromArgb(255, 232, 17, 35),
        NotificationKind.Idle => Color.FromArgb(255, 0, 120, 212),
        NotificationKind.TaskComplete => Color.FromArgb(255, 16, 124, 16),
        _ => Color.FromArgb(255, 134, 94, 212),
    };
}

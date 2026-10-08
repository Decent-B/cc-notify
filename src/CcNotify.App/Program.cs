using CcNotify.Ui.Infrastructure;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;

namespace CcNotify.Ui;

public static class Program
{
    [STAThread]
    private static void Main()
    {
        WinRT.ComWrappersSupport.InitializeComWrappers();

        // A second launch just asks the running instance to open Settings.
        if (!SingleInstance.TryBecomePrimary())
        {
            SingleInstance.NotifyPrimary();
            return;
        }

        Application.Start(callback =>
        {
            SynchronizationContext.SetSynchronizationContext(
                new DispatcherQueueSynchronizationContext(DispatcherQueue.GetForCurrentThread()));
            _ = new App();
        });
    }
}

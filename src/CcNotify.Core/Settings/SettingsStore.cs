namespace CcNotify.Core.Settings;

public interface ISettingsStore
{
    AppSettings Current { get; }
    event Action<AppSettings>? Changed;
    void Update(Func<AppSettings, AppSettings> change);
}

public sealed class SettingsStore : ISettingsStore
{
    private readonly JsonFile<AppSettings> _file;
    private readonly object _gate = new();
    private AppSettings _current;

    public SettingsStore(AppPaths paths)
    {
        _file = new JsonFile<AppSettings>(paths.Config);
        _current = _file.Load();
    }

    public AppSettings Current { get { lock (_gate) return _current; } }

    public event Action<AppSettings>? Changed;

    public void Update(Func<AppSettings, AppSettings> change)
    {
        AppSettings next;
        lock (_gate)
        {
            next = change(_current);
            if (next == _current) return;
            _current = next;
            _file.Save(next);
        }
        Changed?.Invoke(next);
    }
}

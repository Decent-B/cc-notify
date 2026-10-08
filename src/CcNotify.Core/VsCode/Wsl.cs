using System.Text;

namespace CcNotify.Core.VsCode;

public interface IWsl
{
    /// <summary>Installed distro names (default first); empty when WSL is unavailable.</summary>
    Task<IReadOnlyList<string>> GetDistrosAsync();

    /// <summary>Runs a command inside a distro without a shell (<c>wsl --exec</c>).</summary>
    Task<ProcessResult> ExecAsync(string distro, IEnumerable<string> command, string? stdin = null);
}

public sealed class Wsl : IWsl
{
    private readonly IProcessRunner _runner;

    public Wsl(IProcessRunner runner) => _runner = runner;

    public async Task<IReadOnlyList<string>> GetDistrosAsync()
    {
        try
        {
            // wsl.exe prints UTF-16 LE.
            var r = await _runner.RunAsync("wsl.exe", ["--list", "--quiet"],
                stdoutEncoding: Encoding.Unicode, timeout: TimeSpan.FromSeconds(10));
            if (r.ExitCode != 0) return [];
            return r.StdOut.Split('\n')
                .Select(l => l.Replace("\0", "").Trim())
                .Where(l => l.Length > 0)
                .ToList();
        }
        catch (Exception e) when (e is System.ComponentModel.Win32Exception or TimeoutException or InvalidOperationException)
        {
            return [];
        }
    }

    public Task<ProcessResult> ExecAsync(string distro, IEnumerable<string> command, string? stdin = null) =>
        _runner.RunAsync("wsl.exe", ["--distribution", distro, "--exec", .. command], stdin);
}

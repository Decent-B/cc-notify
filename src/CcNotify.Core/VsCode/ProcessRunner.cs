using System.Diagnostics;
using System.Text;

namespace CcNotify.Core.VsCode;

public sealed record ProcessResult(int ExitCode, string StdOut, string StdErr);

public interface IProcessRunner
{
    Task<ProcessResult> RunAsync(string file, IEnumerable<string> args, string? stdin = null,
        Encoding? stdoutEncoding = null, TimeSpan? timeout = null);
}

/// <summary>Runs a hidden child process and captures its output.</summary>
public sealed class ProcessRunner : IProcessRunner
{
    public async Task<ProcessResult> RunAsync(string file, IEnumerable<string> args, string? stdin = null,
        Encoding? stdoutEncoding = null, TimeSpan? timeout = null)
    {
        var psi = new ProcessStartInfo(file)
        {
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = stdoutEncoding ?? Encoding.UTF8,
            StandardErrorEncoding = stdoutEncoding ?? Encoding.UTF8,
            CreateNoWindow = true,
            UseShellExecute = false,
        };
        foreach (var a in args) psi.ArgumentList.Add(a);

        using var p = Process.Start(psi) ?? throw new InvalidOperationException($"Could not start {file}");
        var stdout = p.StandardOutput.ReadToEndAsync();
        var stderr = p.StandardError.ReadToEndAsync();
        if (stdin is not null) await p.StandardInput.WriteAsync(stdin);
        p.StandardInput.Close();

        using var cts = new CancellationTokenSource(timeout ?? TimeSpan.FromSeconds(30));
        try { await p.WaitForExitAsync(cts.Token); }
        catch (OperationCanceledException)
        {
            try { p.Kill(entireProcessTree: true); } catch { /* already gone */ }
            throw new TimeoutException($"{file} timed out");
        }
        return new ProcessResult(p.ExitCode, await stdout, await stderr);
    }
}

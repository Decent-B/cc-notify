using System.Net;
using System.Security.Cryptography;
using System.Text;
using CcNotify.Core.Notifications;
using Microsoft.Extensions.Logging;

namespace CcNotify.Core.Server;

/// <summary>
/// Loopback HTTP endpoint Claude Code hooks post to. Every request except /health must carry the
/// per-install token (?token=); hooks are fire-and-forget so we always answer 200 immediately.
/// </summary>
public sealed class WebhookServer : IDisposable
{
    private readonly HttpListener _listener = new();
    private readonly int _port;
    private readonly string _token;
    private readonly Action<HookEvent> _onEvent;
    private readonly ILogger _log;

    public WebhookServer(int port, string token, Action<HookEvent> onEvent, ILogger log)
    {
        _port = port;
        _token = token;
        _onEvent = onEvent;
        _log = log;
        // Loopback only: Claude Code on Windows and WSL2 both reach it via localhost.
        _listener.Prefixes.Add($"http://127.0.0.1:{port}/");
    }

    /// <exception cref="HttpListenerException">The port is already taken.</exception>
    public void Start()
    {
        _listener.Start();
        _log.LogInformation("Webhook server listening on 127.0.0.1:{Port}", _port);
        _ = Task.Run(AcceptLoop);
    }

    private async Task AcceptLoop()
    {
        while (_listener.IsListening)
        {
            HttpListenerContext ctx;
            try { ctx = await _listener.GetContextAsync(); }
            catch (Exception e) when (e is HttpListenerException or ObjectDisposedException) { return; }

            try { await Handle(ctx); }
            catch (Exception e) { _log.LogWarning(e, "Webhook request failed"); }
            finally { ctx.Response.Close(); }
        }
    }

    private async Task Handle(HttpListenerContext ctx)
    {
        var req = ctx.Request;
        var path = req.Url?.AbsolutePath;

        if (req.HttpMethod == "GET" && path == "/health")
        {
            await Json(ctx, 200, $"{{\"status\":\"ok\",\"port\":{_port}}}");
            return;
        }
        if (req.HttpMethod != "POST" || path != "/webhook")
        {
            await Json(ctx, 404, "{\"error\":\"not found\"}");
            return;
        }
        if (!TokenValid(req.QueryString["token"]))
        {
            _log.LogWarning("Rejected /webhook request with invalid or missing token");
            await Json(ctx, 403, "{\"error\":\"unauthorized\"}");
            return;
        }

        using var reader = new StreamReader(req.InputStream, Encoding.UTF8);
        var ev = HookEvent.Parse(await reader.ReadToEndAsync());
        _log.LogDebug("hook received: {Event} {Type} cwd={Cwd}", ev.Name, ev.NotificationType, ev.Cwd);
        _onEvent(ev);
        await Json(ctx, 200, "{}");
    }

    // Constant-time comparison so response timing cannot leak the token.
    private bool TokenValid(string? provided) =>
        !string.IsNullOrEmpty(provided) &&
        CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(provided), Encoding.UTF8.GetBytes(_token));

    private static async Task Json(HttpListenerContext ctx, int status, string body)
    {
        ctx.Response.StatusCode = status;
        ctx.Response.ContentType = "application/json";
        var bytes = Encoding.UTF8.GetBytes(body);
        await ctx.Response.OutputStream.WriteAsync(bytes);
    }

    public void Dispose() => _listener.Close();
}

using CcNotify.Core.Notifications;
using CcNotify.Core.Settings;
using Xunit;

namespace CcNotify.Core.Tests;

public class NotificationRouterTests
{
    private sealed class FixedMessages : IMessageCatalog { public string Pick(NotificationKind k) => $"msg-{k}"; }

    private static readonly NotificationRouter Router = new(new FixedMessages());
    private static readonly AppSettings Defaults = new();

    [Fact]
    public void Stop_becomes_task_complete_with_cwd()
    {
        var n = Router.Route(new HookEvent("Stop", Cwd: @"C:\proj"), Defaults);
        Assert.Equal(NotificationKind.TaskComplete, n!.Kind);
        Assert.Equal(@"C:\proj", n.Cwd);
        Assert.Equal("msg-TaskComplete", n.Body);
    }

    [Fact]
    public void Disabled_event_is_dropped()
    {
        Assert.Null(Router.Route(new HookEvent("Stop"), Defaults with { NotifyOnStop = false }));
        Assert.Null(Router.Route(new HookEvent("Notification", NotificationType: "permission_prompt"), Defaults with { NotifyOnPermission = false }));
    }

    [Fact]
    public void PermissionRequest_is_ignored_so_a_prompt_gives_one_popup_not_two() =>
        Assert.Null(Router.Route(new HookEvent("PermissionRequest", ToolName: "Bash"), Defaults));

    [Theory]
    [InlineData("rate_limit", "Claude Code — Rate Limited")]
    [InlineData("server_error", "Claude Code — Server Error")]
    [InlineData("???", "Claude Code — Something Went Wrong")]
    public void StopFailure_title_depends_on_reason(string reason, string title)
    {
        var n = Router.Route(new HookEvent("StopFailure", StopReason: reason), Defaults);
        Assert.Equal(title, n!.Title);
        Assert.Equal(NotificationKind.Failure, n.Kind);
    }

    [Theory]
    [InlineData("permission_prompt", NotificationKind.Permission)]
    [InlineData("idle_prompt", NotificationKind.Idle)]
    public void Notification_types_map_to_kinds(string type, NotificationKind kind) =>
        Assert.Equal(kind, Router.Route(new HookEvent("Notification", NotificationType: type), Defaults)!.Kind);

    [Fact]
    public void Status_updates_need_a_message_and_never_focus_vscode()
    {
        Assert.Null(Router.Route(new HookEvent("Notification", NotificationType: "auth_success"), Defaults));
        var n = Router.Route(new HookEvent("Notification", NotificationType: "auth_success", Message: "hi", Cwd: "/x"), Defaults);
        Assert.Equal("Claude Code", n!.Title);
        Assert.Null(n.Cwd);
    }

    [Fact]
    public void Unknown_event_is_ignored() => Assert.Null(Router.Route(new HookEvent("SessionStart"), Defaults));

    [Fact]
    public void Embedded_catalog_has_messages_for_every_kind()
    {
        var catalog = MessageCatalog.LoadEmbedded();
        foreach (var kind in new[] { NotificationKind.Permission, NotificationKind.Idle, NotificationKind.TaskComplete, NotificationKind.Failure })
            Assert.NotEmpty(catalog.Pick(kind));
    }

    [Fact]
    public void HookEvent_parses_payload_and_tolerates_garbage()
    {
        var e = HookEvent.Parse("""{"hook_event_name":"Stop","cwd":"C:\\p","stop_reason":"x","extra":1}""");
        Assert.Equal("Stop", e.Name);
        Assert.Equal(@"C:\p", e.Cwd);
        Assert.Equal("", HookEvent.Parse("not json").Name);
        Assert.Equal("", HookEvent.Parse("[1]").Name);
    }
}

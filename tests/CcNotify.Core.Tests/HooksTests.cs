using System.Text.Json.Nodes;
using CcNotify.Core.Hooks;
using Xunit;

namespace CcNotify.Core.Tests;

public class HooksTests
{
    private const string Url = "http://localhost:9876/webhook?token=abc";

    [Fact]
    public void Merge_adds_all_events_and_keeps_unrelated_settings()
    {
        var (json, replaced) = ClaudeSettingsMerger.Merge("""{"model":"x","hooks":{"PreToolUse":[1]}}""", Url);
        var root = JsonNode.Parse(json)!;
        Assert.False(replaced);
        Assert.Equal("x", (string?)root["model"]);
        Assert.NotNull(root["hooks"]!["PreToolUse"]);
        foreach (var e in ClaudeSettingsMerger.Events)
        {
            var hook = root["hooks"]![e]![0]!["hooks"]![0]!;
            Assert.Equal("http", (string?)hook["type"]);
            Assert.Equal(Url, (string?)hook["url"]);
            Assert.True((bool)hook["async"]!);
        }
    }

    [Fact]
    public void Merge_removes_our_old_PermissionRequest_hook_but_keeps_the_users()
    {
        var ours = """{"hooks":{"PermissionRequest":[{"hooks":[{"type":"http","url":"http://localhost:9876/webhook?token=old","async":true}]}]}}""";
        Assert.Null(JsonNode.Parse(ClaudeSettingsMerger.Merge(ours, Url).Json)!["hooks"]!["PermissionRequest"]);

        var theirs = """{"hooks":{"PermissionRequest":[{"hooks":[{"type":"command","command":"my-script"}]}]}}""";
        Assert.NotNull(JsonNode.Parse(ClaudeSettingsMerger.Merge(theirs, Url).Json)!["hooks"]!["PermissionRequest"]);
    }

    [Theory]
    [InlineData(null, false)]
    [InlineData("", false)]
    [InlineData("{ broken", true)]
    public void Merge_handles_missing_or_invalid_input(string? existing, bool replaced)
    {
        var (json, r) = ClaudeSettingsMerger.Merge(existing, Url);
        Assert.Equal(replaced, r);
        Assert.NotNull(JsonNode.Parse(json)!["hooks"]!["Stop"]);
    }

    [Fact]
    public async Task Windows_installer_writes_settings_file()
    {
        var home = Directory.CreateTempSubdirectory().FullName;
        var result = await new WindowsHookInstaller(home).InstallAsync(Url);
        Assert.Equal(InstallOutcome.Configured, result.Single().Outcome);
        Assert.Contains(Url, File.ReadAllText(Path.Combine(home, ".claude", "settings.json")));
    }
}

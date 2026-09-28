---
description: 查看、初始化或启动本机 Claude Code／Codex 协作消息运行时
allowed-tools: Bash, Read
---

本命令只负责显式启用、诊断和清理。日常加入、查看消息、发现联系人或按名称发消息时，改用 `collab`
skill；Claude Code 用户可从 slash／skill 菜单选择它，不需要手工填写下文的注册字段。

这是本机 Agent 通讯录的操作入口，不是项目组、任务调度器、Issue 工具或 Git 写入口。先定位已安装的
Spec Guard 根目录并只读检查运行时：

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}"
[ -n "$ROOT" ] && [ -d "$ROOT" ] || { echo "spec-guard 插件根目录不可用" >&2; exit 2; }
python3 -B "$ROOT/hooks/collaboration_runtime.py" status --format json
```

- `absent`：说明尚未启用。解释它会创建 `~/.spec-guard/collaboration/` 的私有 token 和配置；只有用户
  明确要求初始化后，才运行 `... collaboration_runtime.py init`。
- `valid`：配置安全但不表示服务正在运行。用户明确要求启动后，才运行 `... collaboration_runtime.py start`；
  随后运行 `... collaboration_runtime.py health --format json`。只有 `daemon: running` 才报告可用。
- `invalid`：原样说明诊断；不得删除、覆盖或放宽目录／token 权限。

用户明确要求让服务在交互式终端结束后仍保持可用时，才运行
`... collaboration_runtime.py service-enable`。它只会在当前用户的 `~/Library/LaunchAgents/` 写入受管
服务；随后用 `service-status --format json` 确认状态。不得把此动作当作安装、项目打开或 Claude/Codex
启动时的隐式副作用。用户明确要求停用时，才运行 `... collaboration_runtime.py service-disable`；它只删除
经验证属于 Spec Guard 的服务。

只有用户明确指定要清理某一条**临时／陈旧通讯录身份**，并已给出精确 UUID 时，才运行
`... collaboration_runtime.py remove-agent --agent-id <UUID>`。它调用上游的按 ID registry 删除接口，只删除
该身份行，不终止进程、不删除消息；不得根据名字猜测 UUID，也不得将它用于真实、仍在工作的会话。

初始化与启动不会创建 GitHub/GitLab Issue、改项目文件、操作分支或替其他任务注册身份。守护进程可用后，
仍需按 `references/collaboration-runtime.md` 为 Claude 或 Codex 选择相应的无 secret MCP 接入方式。若用户
明确要求为 Codex 进行一次性用户配置，可运行
`python3 -B "$ROOT/hooks/collaboration_adapters.py" install-codex`；它拒绝覆盖同名表。不要将 token
复制进 `.mcp.json`、`config.toml`、日志或命令参数。

若用户明确要求让**未来新开的** Claude Code 正常会话也自动获得消息工具，可运行
`python3 -B "$ROOT/hooks/collaboration_adapters.py" install-claude --claude-bin "$(command -v claude)"`。
它通过 `claude mcp add --scope user` 写入一个无 secret 的 stdio 启动器，并拒绝替换既有同名服务器；当前已经
运行的 Claude Code 会话必须重启后才会加载。该命令需要已可用的 `npx`，用于执行固定版开源 MCP bridge；不得
将 token 作为 `--env`、`--header` 或任意 Claude 配置值传给 `claude mcp add`。

用户明确要求移除时，`uninstall-claude --confirm-uninstall` 与 `uninstall-codex --confirm-uninstall` 只删除
Spec Guard 安装的条目；被用户改过的 Codex 表会被拒绝并给出需手动删除的行号。切换到 native 或回退时，按
`references/collaboration-runtime.md` 的检查清单逐步执行，包括停用服务、移除另一后端的条目和退役已结束的
native 身份。

用户询问 Claude Code CLI 主动唤醒时，先读 `references/collaboration-runtime.md` 的
“Claude Code CLI 主动唤醒的预览边界”。Spec Guard 已移除 channel 唤醒入口，不要通过开发预览开关加载
下载的第三方 Channel，也不要声称原生 Claude/Codex Desktop 获得主动唤醒。
Codex Desktop 和 ChatGPT in Chrome 配置不变。

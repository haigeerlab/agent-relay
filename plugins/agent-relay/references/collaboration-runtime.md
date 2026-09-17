# Collaboration runtime（第一期）

本参考定义受管本机消息运行时的安全前置条件和显式操作命令。它不写宿主配置，也不让 Agent
获得 Git、Issue 或 Ticket 写权限。

## 固定上游与范围

- Runtime：`cross-agent-teams-mcp@0.8.6`，MIT；禁止用 `@latest` 或未记录的版本替换。
- 范围：同一台 Mac、`127.0.0.1`，默认端口 `9100`；不支持公网、LAN、Tailscale 或跨设备模式。
- 上游 daemon 的 host、port、token、db、pid-file 参数见其官方 README：
  <https://github.com/jtianling/cross-agent-teams-mcp#1-start-the-daemon>。
- Codex 的 bearer token 环境变量方式见同一 README 的 Codex CLI 配置段：
  <https://github.com/jtianling/cross-agent-teams-mcp#codex-cli>。
- Codex 官方 MCP 文档确认 `http_headers_helper` 可由本机命令动态输出 HTTP 请求头：
  <https://developers.openai.com/codex/mcp/>。
- Claude Code 官方文档确认 HTTP MCP 的 `headers` 可展开环境变量：
  <https://docs.anthropic.com/en/docs/claude-code/mcp>。

上游文档的 `npx …@latest` 是其通用快速开始示例，不是 Spec Guard 的安装方法。Spec Guard
将只接受上述固定版本；启动／升级动作须另有明确用户确认。

## 私有配置合同

默认位置为 `~/.spec-guard/collaboration/`，可通过诊断命令的 `--config-dir` 指向测试目录。

```text
~/.spec-guard/collaboration/       mode 0700（或更严）
├── runtime.json                   非秘密配置
└── token                          mode 0600，非空 bearer token
```

`runtime.json` 必须只有以下字段：

```json
{
  "host": "127.0.0.1",
  "port": 9100,
  "package": "cross-agent-teams-mcp",
  "packageVersion": "0.8.6",
  "tokenFile": "token"
}
```

运行时目录不能是符号链接；token 必须是该目录内的普通文件，且文件名不得包含路径。诊断只报告
host、port、包名和版本，绝不读取或打印 token 值。

## 当前可用的只读诊断

```bash
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py status --format json
```

结果是：

- `absent`：尚未配置；这是安全的初始状态，命令不会创建文件。
- `valid`：配置符合固定版本、loopback 和私有文件权限要求。
- `invalid`：配置存在但不安全或不完整；必须先修正，不能降级为无认证服务。

## 显式初始化、启动与健康检查

下列命令会修改**用户私有**运行时目录或启动本机进程，只有用户／Agent 明确执行时才发生；插件安装、
项目打开和诊断都不会自动触发它们。

```bash
# 仅首次：创建 0700 目录、0600 token 与固定版 runtime.json；拒绝覆盖既有目录。
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py init

# 以固定的 XATS 0.8.6 启动守护进程；token 仅进入子进程环境，不在 argv。
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py start

# 读取 XATS /health；只有其已知协议响应才报告 running。
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py health --format json
```

SQLite 数据与 PID 文件都位于该私有目录。首次启动时 `npx` 可能仍在安装固定版本；此时 `start` 返回
`starting`，不是“已可投递”。必须由 `health` 返回 `daemon: running` 后，才可把它作为可用消息运行时。
若已有别的进程占用端口或 XATS 异常退出，`health` 会报告 `offline`，而不是伪报服务正常。

## 可选的用户级后台服务

交互式终端结束后不保证其后台子进程仍会存活。若用户明确希望跨终端、跨重启地维持本机消息服务，可在
初始化成功后显式启用当前 macOS 用户的 LaunchAgent：

```bash
# 创建或更新 ~/Library/LaunchAgents/com.specguard.collaboration.plist，并 bootstrap 当前 gui/<uid>。
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py service-enable

# 只读诊断：区分未启用、路径陈旧、已加载但离线和健康服务。
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py service-status --format json

# 仅在用户明确要求停用时执行：bootout 并删除经校验属于 Spec Guard 的 plist。
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py service-disable
```

启用操作只创建当前用户的 `~/Library/LaunchAgents/com.specguard.collaboration.plist`，不需要管理员权限，
不写 `/Library/LaunchAgents`，也不修改 Claude/Codex Desktop 的启动方式。plist 只记录 Python、插件运行时和
`npx` 的绝对路径；token 由其 `serve` 子进程从私有 `0600` 文件读取，只存在于该子进程环境。标准输出和错误
日志预创建在私有运行时目录且权限为 `0600`。未知或结构不符的同名 plist 会拒绝覆盖或删除。

插件升级后应重新执行一次 `service-enable`，使 plist 更新到新版运行时路径。该后台服务不会启用 Codex
受管 app-server，因此不影响 ChatGPT in Chrome。

## 显式清理一个陈旧通讯录身份

XATS 的 agent 注册与消息数据分离。若一个**已确认是测试或陈旧**的身份因其原会话已不存在而无法自行
`unregister_self`，用户可按通讯录返回的精确 UUID 显式清理：

```bash
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py remove-agent \
  --agent-id 01234567-89ab-cdef-0123-456789abcdef
```

该命令只调用固定 loopback runtime 的 `DELETE /api/agents/<agent_id>`，并要求上游返回 `deleted: true`；它不
停止进程、不删除该身份已收到的消息，也不能按显示名模糊删除。它不是常规会话退出路径，正常会话仍应调用
`unregister_self`。未知 ID 或连接失败都不会被报告为“已清理”。

## 宿主配置合同

`collaboration_adapters.py` 只根据一个已验证的私有运行时生成**无 secret**配置片段：

```bash
python3 -B plugins/spec-guard/hooks/collaboration_adapters.py codex
python3 -B plugins/spec-guard/hooks/collaboration_adapters.py claude
```

Codex 片段使用 `collaboration_auth_header.py` 作为 `http_headers_helper`。该助手每次只向 Codex
输出一份 JSON `Authorization` 头；它重新检查 token 的普通文件类型、`0600` 权限和无控制字符要求，
不向诊断、日志或配置输出 token。

在用户明确确认后，可一次性把**无 secret**的表追加到其 Codex 用户配置（默认
`~/.codex/config.toml`）：

```bash
python3 -B plugins/spec-guard/hooks/collaboration_adapters.py install-codex
```

它保留已有配置、使用原子替换，并在同名 MCP 表已存在时拒绝覆盖。完成后重启 Codex／ChatGPT desktop
app 使 MCP 目录重新加载。Codex 的本地客户端共享该配置，因此不是“每个项目再安装一次”。

Claude 的普通 HTTP 配置无法像 Codex 一样调用动态 header helper。推荐的用户级接入使用固定版
[`mcp-remote@0.1.38`](https://github.com/punkpeye/mcp-remote)（MIT）作为 stdio→loopback HTTP bridge。
它官方支持在 header 参数中展开子进程环境变量，因此可由 Spec Guard 的私有启动器在子进程环境设置 token，
而 Claude 用户配置、bridge argv 和项目文件只保存变量名：

```bash
# 仅在用户明确选择为未来 Claude Code 会话启用时执行；拒绝覆盖同名 MCP server。
python3 -B plugins/spec-guard/hooks/collaboration_adapters.py install-claude \
  --claude-bin "$(command -v claude)"
```

该操作等价于受控的 `claude mcp add --scope user`：写入的是 `collaboration_claude_stdio.py`、私有运行时
目录和当前 `npx` 的绝对路径，不含 token。每个未来 Claude Code 会话启动时，stdio helper 验证私有 runtime，
读取 `0600` token，并将完整 `Bearer` 值仅放入 `mcp-remote` 的子进程环境；参数仍是字面
`Authorization:${SPEC_GUARD_COLLABORATION_AUTH_HEADER}`。`mcp-remote` 的固定版本和许可证见其
[package metadata](https://github.com/punkpeye/mcp-remote/blob/main/package.json)。

该用户级配置不会让一个已经运行的 Claude Code Desktop 会话即时出现新工具；需要关闭并新开该会话。若
Node/npx 主版本路径变化，重新执行一次 `install-claude` 即可，但它会先拒绝同名条目，需先由用户显式移除或
人工核对现有配置，绝不静默覆盖。

`collaboration_claude.py` 保留为一次性受管启动包装器：它临时设置 HTTP MCP 所需环境变量，并以私有、
进程退出后删除的 `--mcp-config` 文件启动 Claude Code：

```bash
python3 -B plugins/spec-guard/hooks/collaboration_claude.py -- --continue
```

不要把生成片段中的占位符手工替换为 token，也不要把 token 写入 `.mcp.json`、`settings.json` 或仓库。
包装器拒绝调用者额外传入 `--mcp-config`，以免悄悄覆盖本次连接的安全配置。

传入 `--include-channel` 时，Claude 片段还会生成固定版本的 channel 唤醒条目。这是开发预览增强，
只有明确传入 `--enable-channel-wake` 才会由包装器开启 Claude Code 的 channel loader；未开启时仅使用
收件箱式投递。

## Codex Desktop 的两种接入级别

默认的原生 Desktop 接入不改变 App 启动方式：注册时使用 XATS 的 `custom` 终端类型
`codex-desktop-native`。它已经覆盖持久邮箱、跨项目寻址和下次协作工具调用时的收件箱读取，但没有
主动唤醒。

上游的 Codex 主动唤醒需要受管 app-server。CLI 需要通过 `--remote` 连接本机 `8799`；Desktop 则需要
通过隔离的 `8800` app-server 启动。Desktop 受管模式会影响既有 App 运行方式，并且当前不能使用
ChatGPT in Chrome，因此不属于 `start` 或 `install-codex` 的隐式副作用，必须由用户另行明确选择。

消息收发、内部本机命名空间与“邮件已入箱”和“已唤醒”的区别，见
`references/collaboration-protocol.md`。

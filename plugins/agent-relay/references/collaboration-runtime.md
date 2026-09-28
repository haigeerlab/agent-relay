# Collaboration runtime（第一期）

本参考定义受管本机消息运行时的安全前置条件和显式操作命令。诊断命令只读；写入宿主配置（Claude、
Codex 的 MCP 条目与 LaunchAgent）只在用户明确要求时由下文对应的命令执行，每一项都有对应的移除命令。
它不让 Agent 获得 Git、Issue 或 Ticket 写权限。

## 实验性 native 后端（默认未切换，可显式选择）

固定源码提交为 `8f12c880cfdba73812b6ab7bc0f373fc467e0343`。仅在用户明确选择安装时，
`native_collaboration_runtime.py install` 才会把它放到私有目录；普通插件安装和 `collab`
都不运行这个动作。未写入私有选择标记的安装仍默认使用下文的 XATS；一次经批准的实机验收
已在单台 Mac 上选择 native，但不构成面向所有安装者的默认切换。

```bash
# 只读查看固定版本、目录和权限；不会启动服务。
python3 -B plugins/spec-guard/hooks/native_collaboration_runtime.py status

# 显式用临时邮箱启动固定版 MCP，验证握手和基础收件工具后删除临时数据。
# 不打开真实邮箱，也不修改 Claude、Codex 或 Chrome 配置。
python3 -B plugins/spec-guard/hooks/native_collaboration_runtime.py probe
```

安装后的 `mailbox/bridge.sqlite` 与 `mailbox/backups/` 均在同一个私有运行时目录中，
不在项目 worktree。备份目录必须为 `0700`，现有的上游 `bridge-*.sqlite` 备份文件必须为
`0600`；否则 `status` 拒绝视为就绪。固定版上游在迁移数据库前备份，并在运行期间保留
每日备份；探测使用临时邮箱且禁用其每日备份，不碰真实消息。`probe` 的成功仅证明该构建
在隔离环境能启动，不能证明宿主 MCP 已安装、当前会话可唤醒或可以切换邮箱。

受控切换另有 `native_collaboration_activate.py`，它不是日常 `collab` 命令。操作员须先确认
旧会话均已结束、XATS 已停止，并使用私有归档命令生成且核验只读备份；激活命令重新核对
归档 SHA-256、完整性、已登记身份数、未读投递数及与当前 XATS 数据库一致的逻辑内容，
且只在私有目录
原子创建一次 `transport.json`。`--confirm-xats-stopped` 和
`--confirm-old-sessions-closed` 是操作员断言，**命令不能独立证明进程已退出**；沙箱里的
离线探测也不能代替实机确认。任何一步失败均不应手工补写标记。首次受控试验因 Claude Code
账号访问失败而回退；获批的第二次试验完成双向唤醒后在该测试主机保持 native。其他主机切换
仍需各自重新核对会话、归档与操作授权。

回退使用独立的 `native_collaboration_rollback.py`，也不是日常命令。操作员先停止原生后端的
新发送，确认其会话已结束、XATS 服务已运行，并检查原生未确认投递。命令要求
`--confirm-native-sessions-stopped` 与 `--confirm-xats-running` 两项显式断言，随后核实私有
选择标记、XATS 邮箱可读，以及原生邮箱无已登记会话、无未确认直发或广播投递；通过后仅删除
`transport.json`，保留原生邮箱历史。两项服务断言仍由操作员负责，命令无法自行证明。
该命令只在经过单独批准的实机切换后使用；它已在首次受控试验的回退中运行，原生邮箱历史
保留。随后获批的第二次试验通过 Claude Code ↔ Codex 双向空闲唤醒及两种 Chrome 功能验收，
当前测试主机保持 native；历史试验中的“XATS 已恢复”不是当前主机状态。

### 切换与回退检查清单

激活只写选择标记，不会停掉另一个后端。激活成功后，若不按顺序收尾，XATS 的 LaunchAgent 会在下次登录时
重新启动，宿主里也会同时留着两个协作 MCP，新会话会看到两套工具。以下每一步都需要用户明确要求：

1. `collaboration_runtime.py service-disable`：bootout 并删除受管 LaunchAgent plist。
2. `collaboration_adapters.py uninstall-claude --confirm-uninstall` 与
   `collaboration_adapters.py uninstall-codex --confirm-uninstall`：移除 XATS 的 MCP 条目。Codex 表只有与
   安装时生成的内容逐字一致才会删除；若它由另一份源码安装，传入当时的 `--header-helper` 路径，否则命令拒绝
   并给出需要手动删除的行号。
3. `native_collaboration_adapters.py install-claude` 与 `install-codex`：接入 native。
4. 重启客户端，确认新会话只加载 `spec-guard-native-collaboration`。

回退要求所有 native 身份都已退役且没有未确认投递。Agent 无法调用被拒绝的 `bridge_retire`，而它默认会把
未读消息标记为已处理；因此由操作员逐个退役已结束会话的身份：

```bash
# 只退役一个精确名称；保留其消息，仍有未确认的直发或广播投递时拒绝。
python3 -B plugins/spec-guard/hooks/native_collaboration_retire.py --name "<精确名称>" --confirm-retire
```

`--confirm-retire` 是“该会话已结束”的操作员断言。全部退役后运行上面的回退命令，再用
`native_collaboration_adapters.py uninstall-claude --confirm-uninstall` 与 `uninstall-codex --confirm-uninstall`
移除 native 条目（Claude 的拒绝规则保留，它们只拒绝本服务的工具），最后按需重新启用 XATS 服务与条目。

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
Node/npx 主版本路径变化，需要重新接入：`install-claude` 会拒绝同名条目，先在用户明确要求下运行
`uninstall-claude --confirm-uninstall` 再安装，绝不静默覆盖。

`collaboration_claude.py` 保留为一次性受管启动包装器：它临时设置 HTTP MCP 所需环境变量，并以私有、
进程退出后删除的 `--mcp-config` 文件启动 Claude Code：

```bash
python3 -B plugins/spec-guard/hooks/collaboration_claude.py -- --continue
```

需要 Claude Code in Chrome 时，可显式传入 `--chrome`；包装器会原样转交给 Claude，不会替用户
启用或配置浏览器扩展：

```bash
python3 -B plugins/spec-guard/hooks/collaboration_claude.py -- --chrome
```

不要把生成片段中的占位符手工替换为 token，也不要把 token 写入 `.mcp.json`、`settings.json` 或仓库。
包装器拒绝调用者额外传入 `--mcp-config`，以免悄悄覆盖本次连接的安全配置。

传入 `--include-channel` 时，Claude 片段还会生成固定版本的 channel 唤醒条目。这是开发预览增强，
只有明确传入 `--enable-channel-wake` 才会由包装器开启 Claude Code 的 channel loader；未开启时仅使用
收件箱式投递。

### Claude Code CLI 主动唤醒的预览边界

Claude Channels 尚处研究预览。源码已有显式 `--enable-channel-wake` 实验开关，但它不是
普通用户的推荐启用方式。真实 CLI 验收停在 Anthropic 的开发通道确认页：该页明确警告不要用
`--dangerously-load-development-channels` 运行从互联网下载的 Channel；目前固定版 XATS
Channel 正是下载的第三方包，因此未代用户确认，也未观察到实际唤醒。

普通 Claude MCP 邮箱仍可用。仅运行时健康、MCP 工具连接或发送端 `send_message` 成功，
都不能证明目标会话被唤醒。等待适用的官方批准路径或单独的安全裁决，再进行新 CLI 的主动
唤醒实验；即使未来可试，也须在目标会话**没有手工查看收件箱**时观察到消息和回复，才算
验证通过。不得为此启用权限绕过或权限中继。原生 Desktop／编辑器内 Claude 会话不在本
CLI 验收范围内。Codex Desktop 启动方式不变，ChatGPT in Chrome 保持可用。

官方说明：[Claude Channels](https://code.claude.com/docs/en/channels)、
[自定义 Channel 测试与通知语义](https://code.claude.com/docs/en/channels-reference)。

### Claude Code CLI 可选 tmux 提醒

对于**新启动**的 Claude Code CLI 会话，用户可以显式选择本机 tmux 提醒，而不启用第三方
Channel 开发开关。本机需安装 tmux，消息服务需已就绪。在想工作的项目目录运行一条命令：

```bash
python3 -B "$ROOT/hooks/collaboration_claude.py" --tmux-wake
```

若同时使用 Claude Code in Chrome，可在末尾加 `-- --chrome`。这只确认启动参数传递；浏览器扩展
与协作唤醒能否在真实主机上同时工作，仍需单独验收。

`$ROOT` 是已安装 Spec Guard 插件的根目录，由操作入口解析；不是让用户再安装一个插件。命令会
附着到一个新建的、名字唯一的 tmux 会话并启动 Claude。若已经处于 tmux pane，则直接在当前
pane 启动，不再嵌套。退出 Claude 后，新建的 tmux 会话随之结束。普通启动不受影响。
启动后在 Claude 中说一次“加入本机联调”（或 `collab [可选别名]`）。当前 Claude 会话自己
调用 `register_agent` 并从本会话的 `$PPID` 提供 `ui_pid`；XATS 验证 PID、TTY 与 pane 后才
绑定。无需向用户索取 pane、PID、项目组或通信地址。另一个已加入的 Agent 按名称发消息时，
XATS 尝试向该 pane 输入**短提示**，让 Claude 调用 `get_inbox` 读取正文；不把正文直接输入终端。

若用户使用已启用的 LaunchAgent，本插件生成其配置时会把找到的 tmux 可执行文件目录加入 XATS
的 PATH；未安装 tmux 时仍保留邮箱服务。**升级源码不会改动正在运行的后台服务**。若旧服务报告
`spawn tmux ENOENT`，先只读检查 `service-status` 和现有 plist 的 PATH，取得用户对服务刷新
的明确同意后，才重新运行 `service-enable`。这会替换并重启该用户级服务；普通 `collab`
不做这件事。tmux 会话启动器的退出码只表示外层 tmux 是否正常结束，不能替代对内部 Claude
启动与注册的观察。

该方式只适用于 Claude Code CLI 的 tmux 会话，不适用于已在运行且不在 tmux 内的会话，也不
承诺 Claude Desktop／编辑器宿主主动唤醒。tmux 提示可能因目标忙碌、pane 绑定失败或终端状态
而跳过；发送端的“消息入箱”或“提示已写入终端”都**不能证明** Claude 已经阅读和回复。
若未观察到目标会话自行调用 `get_inbox`，请按普通邮箱模式手动说“查看联调消息”。消息和提示
均不传递操作授权，Claude 的正常权限确认仍然有效；不得启用权限绕过。Codex Desktop 仍是
原生邮箱模式，ChatGPT in Chrome 不受影响。

上游机制：[XATS](https://github.com/jtianling/cross-agent-teams-mcp)、
[tmux 手册](https://man.openbsd.org/tmux)。

## Codex Desktop 的两种接入级别

默认的原生 Desktop 接入不改变 App 启动方式：注册时使用 XATS 的 `custom` 终端类型
`codex-desktop-native`。它已经覆盖持久邮箱、跨项目寻址和下次协作工具调用时的收件箱读取，但没有
主动唤醒。

上游的 Codex 主动唤醒需要受管 app-server。CLI 需要通过 `--remote` 连接本机 `8799`；Desktop 则需要
通过隔离的 `8800` app-server 启动。Desktop 受管模式会影响既有 App 运行方式，并且当前不能使用
ChatGPT in Chrome，因此不属于 `start` 或 `install-codex` 的隐式副作用，必须由用户另行明确选择。

消息收发、内部本机命名空间与“邮件已入箱”和“已唤醒”的区别，见
`references/collaboration-protocol.md`。

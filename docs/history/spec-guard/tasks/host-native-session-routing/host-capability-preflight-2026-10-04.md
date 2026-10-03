# host-native-session-routing host capability preflight — 2026-10-04

本记录裁决 Plan Task 1 的当前宿主能力门槛。测试只创建了名称带 `sg-native-*` 的两个 Claude
background 会话和一个标题带 `host-native-routing` 的 Codex task；没有读取或联系其他真实会话，
没有读写项目文件，没有修改全局 Claude/Codex 配置，没有传 Codex model，也没有切换 Spec Guard
bridge。完整内部 session/thread ID 不写入本记录。

## 版本与权威来源

| 项目 | 证据 | 结果 |
|---|---|---|
| Claude Code | `claude --version` → `2.1.288` | 通过 |
| Claude 同机消息契约 | Claude Code 官方文档：[`cross-session-messaging`](https://code.claude.com/docs/en/cross-session-messaging) | 通过 |
| Codex PATH | `codex --version` → `0.154.0`；只作为旧 PATH 事实，不用于实现或验收 | 通过 |
| Codex App 管理版本 | `~/.codex/packages/app-server-daemon/current/codex --version` → `0.160.0` | 通过 |
| Codex thread/turn 契约 | OpenAI 官方文档：[`codex-app-server`](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server) | 通过 |

Claude 官方契约明确说明：同机消息经每会话 socket，不经过 Anthropic 服务器；`/list-agents`
列出可达会话，`ListAgents`/`SendMessage` 负责查找和投递；接收端独立产生 delivered、held 或
refused，收到的消息带回复地址；空闲接收端会被消息启动一个新 turn。当前版本高于 macOS
最低版本 2.1.224。实现只调用宿主工具，不直接打开官方文档描述的 socket。

OpenAI 官方 app-server 契约明确区分 `thread/start`、`turn/start`、`thread/resume` 与终态事件。
当前 Codex App 还实际暴露只读/调度工具 `list_threads`、`read_thread`、`send_message_to_thread`
和 `wait_threads`。这些 task 工具是 Codex 同宿主路径；它们不是 Claude 式 peer socket。

## Claude Code ↔ Claude Code 实测

两个临时会话都使用：

- `--safe-mode`，禁用项目和用户自定义插件、hook、MCP 与指令；
- 临时 `--settings`，仅将 `crossSessionInbound` 设为 `accept` 并允许 `SendMessage`、`ListAgents`；
- `--tools SendMessage,ListAgents`，不开放文件、Shell、配置或其他会话工具；
- `dontAsk` + `permission-prompts none`，未允许的工具直接拒绝，不等待无人处理的 prompt。

| 验收项 | 实际证据 | 结果 |
|---|---|---|
| 精确目录解析 | A 用 `ListAgents` 只解析唯一名称 `sg-native-b-20261004` | 通过 |
| A → B | `SendMessage` 返回 sent；B 收到唯一 ping token 并自动开始新 turn | 通过 |
| B → A 回复 | B 使用来信自带的 sender/reply address 回送唯一 pong token | 通过 |
| A 处理回复 | A 收到 `Message from` 预览并输出预期 received token | 通过 |
| bridge 副本 | 测试未加载 Spec Guard 插件或 MCP，消息不经过 bridge | 通过 |
| held/refuse | 官方契约与状态存在；本次临时会话固定 `accept`，未重复制造拒绝测试 | 未运行 |
| 清理 | 两个精确 background ID 均 `claude stop` 成功，随后状态均为 `stopped` | 通过 |

因此 Claude 同宿主可以提供真正的双向 peer 消息、原生 wake/reply address 和独立接收控制。
插件应复用 `ListAgents`/`SendMessage`，不得用 Python 重写 socket 协议。

## Codex ↔ Codex 实测

当前 Codex App 对本机 task 目录的读取成功，并返回 host、project、status、title 和更新时间等
公开目录事实。随后创建一个隔离 task；其 prompt 禁止读文件、运行命令、修改配置或创建子任务。

| 验收项 | 实际证据 | 结果 |
|---|---|---|
| task 目录 | 当前 App 的 `list_threads` 返回可访问 task 及真实 status | 通过 |
| 创建与等待 | `create_thread` 返回精确 task；`wait_threads` 观察到 turn completed/idle | 通过 |
| 当前会话 → 目标第二轮 | `send_message_to_thread` 投递固定 follow-up；目标精确回复，`wait_threads` 读回 | 通过 |
| 目标主动向来源 task 发送 | 目标尝试 `send_message_to_thread` 时，宿主拒绝转述授权并要求目标 task 自己取得人类授权 | 失败（授权条件未满足） |
| 普通回复 | 目标在收到的 turn 内返回 assistant reply，来源用 `wait_threads` 取得；不需要目标另发跨 task 消息 | 通过 |
| 清理 | 测试 task 以精确 ID 归档；没有删除项目 | 通过 |

Codex 的双向用户体验应建模为“来源向精确 task 启动 turn，目标在该 turn 回复，来源 wait/read
结果”。当人类位于另一个 task 并直接要求反向联系时，方向自然反转。插件不能要求目标 task 把
另一会话转述的授权当成人类授权，也不能把 Claude 的 peer-message 语义强加给 Codex。

## 可证明状态矩阵

| 状态事实 | Claude 原生 | Codex 原生 |
|---|---|---|
| directory visibility | `ListAgents` / `/list-agents` | `list_threads` |
| dispatch accepted | `SendMessage` 成功/拒绝结果 | `send_message_to_thread` 接受或 app-server `turn/start` 结果 |
| wake | idle session 新 turn；可报告 delivered/held/refused | `wait_threads`/task status；没有 Claude 等价 peer wake 承诺 |
| receipt/read | delivered 只表示交给目标 Claude；不得伪造用户已读 | turn/task 状态；没有独立“用户已读”事实 |
| response | 来信 reply address 上的新消息 | 目标 turn 的 assistant result，经 wait/read 取得 |
| busy/offline | 官方目录与 inbound outcome；本次未覆盖全部负例 | task status/timeout；未把 timeout 当失败 |
| cancel | background session 精确 stop（委派生命周期） | interrupt/archive（委派生命周期） |

## Task 1 判决

**通过，可以进入 Task 2。** 两个宿主都有受支持且已实测的同机路径，但抽象必须保留不对称：

1. Claude 是 peer directory + message + reply address；
2. Codex 是 task directory + turn + wait/read；
3. Codex 的跨 task 主动发送仍受每个发送 task 的直接人类授权约束；
4. 任一能力不可用时只报告 unavailable 或进入 Spec 允许的显式 bridge fallback；
5. 不开发私有 IPC、全局配置写入、`--model` 绕过或 A10 transport 转正逻辑。

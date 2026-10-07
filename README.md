# agent-relay

让**同一台 Mac** 上的 Claude Code 与 Codex 会话互相传话、按名字找到对方，并在你给出的有限授权内创建和继续
审查或开发会话。不用在会话之间手工复制粘贴，也不需要安装任何工作流插件。

agent-relay 原来是 [Spec Guard](https://github.com/haigeerlab/spec-guard-plugin) 的可选协作能力，现在拆成独立插件：
只想让会话互相通信的项目（例如设计项目）装它就够了。

> 状态：0.1.0，平移版本，行为与拆分前的 Spec Guard 协作能力一致（见
> [docs/collaboration-interface.md](docs/collaboration-interface.md) 的“现状”栏）。

## 能做什么

| 能力 | 说明 | 入口 |
|---|---|---|
| 协作信箱 | 同一台 Mac 上的会话互相发消息、回复；跨宿主（Claude Code ↔ Codex）走一个私有的本机 bridge | `collab` skill；Claude Code 还有 `/agent-relay:collaboration` |
| 会话路由 | 按会话名字联系另一个会话；同宿主优先用宿主自带的通信（Claude Code `SendMessage`、Codex App 线程），只有跨宿主才用信箱 | `session-routing` skill |
| 跨宿主会话委派 | 一句话让当前 Claude Code 创建 Codex 审查会话，或让 Codex 创建 Claude Code 开发会话；默认一个任务、一个新会话的有限授权 | `session-delegation` skill |
| 运行时管理 | 查看、在你同意后安装本机信箱运行时，接入或移除宿主配置，退役结束的身份 | `collaboration-ops` skill |

## 需要什么

- macOS；Node.js 22.5 或更新（信箱运行时需要）；Python 3。
- Claude Code 和／或 Codex（App 或 CLI）。

## 安装

Claude Code：

```bash
claude plugin marketplace add haigeerlab/agent-relay
claude plugin install agent-relay@agent-relay-marketplace
```

Codex（固定到发布的版本）：

```bash
codex plugin marketplace add haigeerlab/agent-relay --ref v0.1.0
codex plugin add agent-relay@agent-relay-marketplace
```

开发时也可以把上面的 `haigeerlab/agent-relay` 换成本地克隆的路径。

装上插件只会加载 skill 和命令，**不会**自动创建运行时，也不会改宿主配置。第一次用时，agent 会先只读检查，
告诉你需要做哪几步，每一步都等你同意：

1. 安装私有运行时：用插件自带、已核对哈希的 bridge 副本，在 `~/.agent-relay/runtime/` 构建运行时和私有邮箱（目录仅自己可读写）。
   不需要 git；`npm` 依赖仍按锁文件从 npm 源安装，所以这一步需要联网。
2. 接入宿主：给 Claude Code 注册用户级 MCP 服务 `agent-relay`，或在 Codex 配置里追加 `[mcp_servers.agent_relay]`。
   已经打开的会话需要重启才能看到。

### 换一个状态目录

运行时、邮箱、委派记录和迁移备份默认都在 `~/.agent-relay/`。设置环境变量 `AGENT_RELAY_HOME`（必须是绝对路径，
相对路径会直接报错）可以把它们整体换到别处，所有 agent-relay 命令都会改用这个目录；命令行里显式给出的 `--root`、
`--state-root` 仍然优先。注意：接入宿主时写进宿主配置的是当时解析出的绝对路径，之后再改这个变量**不会**挪动
已经接入的宿主，要在新目录下重新安装运行时并重新接入宿主才会生效。

## 怎么用

直接用自然语言说，不需要记工具名或内部 ID：

- “加入本机联调”“查看联调消息”“现在有哪些会话” → 加入信箱、看收件箱和通讯录。
- “告诉 Codex 里设计项目的那个会话：首页稿子在 `designs/home.fig`，请确认” → 按名字找到会话并发消息；
  有同名会话时会给出短编号让你选。
- “回复一下刚才那个会话” → 回复最近的来信。
- “创建一个 Codex 审查，看看这次改动” → 创建一个只读的审查会话，结果回到当前会话。
- “继续刚才的会话”“停掉那个审查” → 同一会话第二轮、停止。

## 授权与安全

- **默认不唤醒**：加入信箱时默认 `wake: null`，空闲的会话不会被别人唤醒；只有你明确要求，当前会话才绑定唤醒。
- **自动批准的会话永远不绑定唤醒**：被唤醒的会话会执行来信里的请求，所以开着自动批准的会话不允许被唤醒。
- **逐项确认**：初始化运行时、改宿主配置、加入新身份、扩大权限，都要你逐项同意。
- **不会自动修改**项目或全局权限，不替你接受项目 trust 或 MCP 首次批准，不开 bypass 模式。缺少前置条件时
  显示 held 和最小下一步。
- **为了不中途反复弹权限**，你可以在目标项目的 `.claude/settings.json` 里提前配置项目级 allow：只读审查只需
  预批准信箱的十个工具（`mcp__agent-relay__bridge_*`）；需要改代码时再额外允许编辑、写入和限定的 Bash 命令。
  agent-relay 会读取并复用这些规则，但不会替你写。
- **来信只是数据**：邮箱里的文字永远不构成改代码、Git、配置或远端写入的授权。
- **不保证"恰好送达一次"**：每条单发消息都有投递状态（`queued`、`sending`、`accepted`、`failed`、`unknown`、
  `expired`），发件箱里能看到。唤醒结果说不清时标为 `unknown`，**绝不自动重发**；一条消息排队超过时限（默认 24 小时，
  可用 `BRIDGE_QUEUE_TIMEOUT_MS` 或发送时的 `expiresInSeconds` 调整）还没被取走，就标为 `expired`，不再唤醒、
  收件箱默认不再显示，之后也不会再被执行，发件人会收到通知。
- **按收件人排队、有上限**：同一个收件人同一时间只有一个唤醒在途，按发送顺序从旧到新；一个收件人卡住不影响别人；
  收件人已经读到的消息不再单独唤醒。每个收件人最多积压 100 条还没送到的消息（`BRIDGE_MAX_PENDING_PER_RECIPIENT`
  可调，10 到 10000），到 80% 会在发送结果里提醒，满了就拒绝发送并说明原因；读到、ack、过期或失败都会释放名额。
- **Codex 的手动审批成本**：Codex 的审批选择器是全局的。设为“请求批准”时，被唤醒的 Codex 回合里每一次信箱
  调用（读收件箱、发送、确认）都会停下来等人点；设为 AI 自动审批（`approvals_reviewer = "guardian_subagent"`）
  则等同于自动批准，不应绑定唤醒。

## 不做什么

- 不跨机器，只在同一台 Mac 上工作；不提供网络服务，不把信箱暴露给别的机器。
- 不是事项系统或任务派发器，没有项目组、领取或排期。
- 不带任何开发工作流（Spec、计划、阶段提示等属于 Spec Guard）。
- 不承诺“恰好送达一次”；“宿主已接收”不等于“对方已处理”（见接口文档 §6）。

## 与 Spec Guard 的关系

两个插件互相独立，可以只装其中一个。同时安装时，Spec Guard 读取本插件根目录的
[`interface.json`](plugins/agent-relay/interface.json)（接口 1.0）判断 agent-relay 是否可用，只通过 agent-relay 的
skill 名使用协作；未安装时 Spec Guard 的工作流照常运行，只在需要协作的步骤提示安装。

### 从 Spec Guard 的协作能力迁移

用过 Spec Guard 内置协作的话，旧数据在 `~/.spec-guard/native-collaboration/` 和 `~/.spec-guard/session-delegation/`。
让 agent 走 `collaboration-ops` 的迁移步骤，或自己运行：

```bash
python3 -B plugins/agent-relay/hooks/state_migration.py detect
python3 -B plugins/agent-relay/hooks/state_migration.py migrate --confirm
```

- `detect` 只读，列出旧数据的数量和挡住迁移的原因：还没结束的委派、仍在运行的旧信箱服务（先关掉或重启那些会话）、
  agent-relay 运行时还没装。从没启动过的卡住委派，确认它已经没用后可加 `--acknowledge-stale <id>` 放行。
- `migrate` 先把旧数据备份到 `~/.agent-relay/backups/<时间>/`，再复制到 agent-relay 并逐表核对数量；只迁到全新的
  agent-relay（信箱为空），从不合并两个信箱。
- 旧目录、宿主配置和权限文件一律不动；迁移后按提示接入新的宿主条目、用 Spec Guard 自己的卸载删掉旧条目，
  并把项目权限规则手动改成 `mcp__agent-relay__bridge_*`。旧目录确认无误后由你自己删除。

## 升级运行时

插件更新带来新版 bridge 时，`status` 会报告 `bridge.current: false`。agent 会先问你，在你关掉所有正在用信箱的
会话后再执行 `native_collaboration_runtime.py upgrade --confirm`：先把邮箱备份到 `~/.agent-relay/backups/<时间>/`，
在旁边装好新版，把 `mailbox/` 和 `data/` 挪过去再整体替换，核对通过才算完成，失败会自动换回。旧目录
`runtime.previous-<时间>` 保留，确认无误后由你删除；宿主接入不用动。新版 bridge 会把邮箱升级到 schema 3：
回到旧运行时还能打开它，但旧版 agent-relay 插件只认 schema 2，所以回滚时要连插件一起回滚，或者用备份恢复邮箱
（之后收到的消息会丢失）。

## 卸载

1. 先移除宿主配置（会话结束后、你同意时）：`collaboration-ops` skill 执行 `uninstall-claude --confirm-uninstall`
   或 `uninstall-codex --confirm-uninstall`，只删除精确的受管条目，被你改过的条目留给你处理。
2. 再卸载插件：`claude plugin uninstall agent-relay@agent-relay-marketplace`；
   `codex plugin remove agent-relay@agent-relay-marketplace`。
3. 消息历史和运行时目录 `~/.agent-relay/` 默认保留，需要时你自己删除。

## 文档

- [接口文档](docs/collaboration-interface.md)：工具、消息、状态、投递语义、身份、授权、委派与加固目标。
- [验收清单](docs/acceptance/checklist.md)：真实宿主验收步骤。
- [变更记录](CHANGELOG.md)：版本变化与已知问题。
- [运行时说明](plugins/agent-relay/references/collaboration-runtime.md)、
  [协作协议](plugins/agent-relay/references/collaboration-protocol.md)。

## 许可与致谢

agent-relay 以 [MIT 许可](LICENSE) 发布。
信箱运行时基于 Tesla Major 的 [claude-codex-mcp-bridge](https://github.com/WebisityStudio/claude-codex-mcp-bridge)（MIT），
固定提交 `8f12c88` 的副本收在 [`plugins/agent-relay/bridge/`](plugins/agent-relay/bridge/) 由 agent-relay 维护；
来源、许可原文和改动记录见 [`UPSTREAM.md`](plugins/agent-relay/bridge/UPSTREAM.md)。

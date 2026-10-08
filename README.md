# agent-relay

让**同一台 Mac** 上的 Claude Code 与 Codex 会话互相传话、按名字找到对方，并在你给出的有限授权内创建和继续
审查或开发会话。不用在会话之间手工复制粘贴，也不需要安装任何工作流插件。

agent-relay 原来是 [Spec Guard](https://github.com/haigeerlab/spec-guard-plugin) 的可选协作能力，现在拆成独立插件：
只想让会话互相通信的项目（例如设计项目）装它就够了。

> 状态：0.5.2（接口 1.4）。变化、升级步骤和已知问题见 [CHANGELOG.md](CHANGELOG.md)；
> 各项目标见 [docs/collaboration-interface.md](docs/collaboration-interface.md) 的“加固目标”栏。

## 能做什么

| 能力 | 说明 | 入口 |
|---|---|---|
| 协作信箱 | 同一台 Mac 上的会话互相发消息、回复；跨宿主（Claude Code ↔ Codex）走一个私有的本机 bridge | `collab` skill；Claude Code 还有 `/agent-relay:collaboration` |
| 会话路由 | 按会话名字联系另一个会话；同宿主优先用宿主自带的通信（Claude Code `SendMessage`、Codex App 线程），只有跨宿主才用信箱 | `session-routing` skill |
| 跨宿主会话委派 | 一句话让当前 Claude Code 创建 Codex 审查会话，或让 Codex 创建 Claude Code 开发会话；默认一个任务、一个新会话的有限授权 | `session-delegation` skill |
| 运行时管理 | 查看、在你同意后安装本机信箱运行时，接入或移除宿主配置，退役结束的身份 | `collaboration-ops` skill |

## 需要什么

- macOS；Node.js 22.5 或更新（信箱运行时用的内置 `node:sqlite` 从 22.5.0 起才有）；Python 3.9 到 3.14
  （macOS 自带的 `/usr/bin/python3` 3.9 可用，3.9、3.10、3.14 都跑过全部测试）。
- 委派控制器、`doctor`、运行时的 `install`／`upgrade`、身份退役和宿主适配器（`install-claude`／`install-codex`
  及打印配置）都用宿主条目里固定的 node（顺序：`--node` →
  Claude 条目 → Codex 条目 → PATH），不受当前 shell 的 PATH 影响；安装时 npm 也在这个 node 上运行，`--npm` 默认取它
  旁边的 npm。选中的 node 低于 22.5.0 时直接拒绝（`node-too-old`），不会动宿主，也不会开始构建。
- Claude Code 和／或 Codex（App 或 CLI）。

## 安装

Claude Code：

```bash
claude plugin marketplace add haigeerlab/agent-relay
claude plugin install agent-relay@agent-relay-marketplace
```

Codex（固定到发布的版本）：

```bash
codex plugin marketplace add haigeerlab/agent-relay --ref v0.5.2
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
- “我在信箱里是谁” → 本会话的身份、宿主、会话标题和项目（`bridge_sessions` 的 `whoami`）。
- “刚才那条消息怎么样了”“等它回复” → 按消息编号查状态，或一直等到它被确认、回复、失败或过期
  （`bridge_wake_status` / `bridge_wait` 带 `messageId`，等待时不替谁确认消息）。
- 长正文或带 `$`、反引号、引号的正文 → 先写进文件，再用 `bodyFile` 发，内容逐字节不变（绝对路径、自己的普通文件、
  不超过 256 KiB、UTF-8）。
- “检查一下 agent-relay 状态” → `native_collaboration_runtime.py doctor`：只读检查运行时、信箱、宿主接入、Codex
  审批模式和已绑定唤醒的会话（会话卡在等待输入时会提示），每项给出下一步；有 fail 时退出码为 1。

## 授权与安全

- **默认不唤醒**：加入信箱时默认 `wake: null`，空闲的会话不会被别人唤醒；只有你明确要求，当前会话才绑定唤醒。
- **被唤醒的 Codex 回合要你批准才能动手**：不管你平时用“帮我批准”还是“请求批准”，bridge 唤醒 Codex 的那一轮都单独
  改成“用户审批 + on-request + 只读沙箱、不联网”：它能读项目、读信箱、回复，但写文件、跑会改东西的命令、联网都会弹
  审批卡等你点；你自己的下一轮会恢复你原来的设置，`config.toml` 不会被改。`install-codex` 给 10 个信箱工具写了
  `approval_mode = "approve"`，所以读信、回复、确认不弹卡（已安装的用 `install-codex --approve-mailbox-tools` 补上）。
  门控只在确认能生效时才用：**真正挡住老版本的是事前的版本门槛**（ChatGPT 应用 26.930 或更新，否则唤醒挂起并通知你）；
  唤醒后再读该线程这一轮的记录核对（只是兜底），对不上就在信箱目录写 `codex-gate.off`、停用门控唤醒并通知你，你检查过
  再删掉这个文件。Claude 的权限模式 bridge 看不到，自动批准的 Claude 会话仍靠 skill 规则不绑定唤醒。
- **Codex 收不到时会通知你**：Codex 没开、被挂起、或身份没绑定唤醒时，bridge 立刻在这台 Mac 上弹一条通知，Codex 只是
  在忙则 10 分钟后仍未送达才通知；每条消息最多一次。通知的标题写发件会话，副标题写消息编号、收件身份和原因（需要你动手时
  写明怎么做），正文是**消息开头最多 60 字的单行预览**。预览会出现在锁屏和共享屏幕上（macOS 的“显示预览”设置可限制）；
  不想显示正文，就在信箱目录（`~/.agent-relay/runtime/mailbox/`）放一个 `notify-preview.off` 文件，退回只写编号的样式；
  完全不要通知就放 `notify.off`。
  **通道**：装了 Homebrew 的 terminal-notifier（只认 `/opt/homebrew/bin` 与 `/usr/local/bin`，不按 PATH 找）就用它，
  否则用 `osascript`。`osascript` 的通知记在“脚本编辑器”名下，而脚本编辑器从不申请通知权限，所以多数 Mac 上会被**悄悄
  丢掉**、系统设置里也找不到开关；想看到横幅就 `brew install terminal-notifier`（是否安装由你决定），第一次弹出时允许它。
  bridge 看不到 macOS 是否真的显示了，所以 wake 详情和发件方警告只写“已尝试通知”（attempted）。doctor 的
  `notifications` 检查按实际通道判断看起来是否允许，`doctor --test-notification` 走同一通道弹一条测试通知让你确认。
  一定看得到的地方是**等待列表**：在任一会话里问“有哪些等 Codex 处理的消息”，或跑 doctor 看 `codex-waiting`（只列数量、
  发件方和编号，不含正文）。
- **发给收不到提醒的身份时会提示发件方**：收件方既没绑定唤醒、bridge 也不知道它在哪个宿主（例如 Codex 以 `wake: null`
  注册）时，发件结果带一条警告：对方要自己查收件箱才会看到。这种情况不弹通知，因为不知道该提醒谁。
- **身份归属于注册它的会话**：发消息（`from`）、ack、自动确认的 `bridge_wait` 只能用本会话注册过的名字，否则拒绝并
  给出下一步。升级后每个会话先重新注册一次名字（记下所属会话）；之后 Claude 会话的名字在 bridge 重启后仍然有效，Codex 会话在 bridge 重启后要先用同一个线程 ID 重新注册。
  别的会话的名字或唤醒绑定，只有你同意后才能用 `takeover: true` 接管；会话只能为自己绑定唤醒。只有原消息的收件人能
  回复它（广播：除发送方外谁都可以；bridge 自动通知不能回复）。防的是误操作和串号，不是恶意本地进程。
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
- **重试 key 只对应一条消息**：用同一个 `idempotencyKey` 重发相同内容，返回原来那条（`duplicate: true`），不会再唤醒；
  同一个 key 换了收件人、正文、线程或回复对象会被拒绝，报错写明已存消息的编号并说明无需重发。回复可带
  `replyTo`（原消息编号），自动落在原消息的线程上，发件箱里能看到每条消息收到了哪些回复；对同一条消息发同样的回复
  只存一次，除非上一条最终失败或过期。
- **Codex 的审批选择器按轮生效**：App 里的选择器只管你自己发起的那一轮，不写进 `config.toml`；被唤醒的那一轮由
  bridge 单独加门控（见上），所以用“帮我批准”也可以绑定唤醒。

## 不做什么

- 不跨机器，只在同一台 Mac 上工作；不提供网络服务，不把信箱暴露给别的机器。
- 不是事项系统或任务派发器，没有项目组、领取或排期。
- 不带任何开发工作流（Spec、计划、阶段提示等属于 Spec Guard）。
- 不承诺“恰好送达一次”；“宿主已接收”不等于“对方已处理”（见接口文档 §6）。

## 与 Spec Guard 的关系

两个插件互相独立，可以只装其中一个。同时安装时，Spec Guard 读取本插件根目录的
[`interface.json`](plugins/agent-relay/interface.json)（接口 1.2）判断 agent-relay 是否可用，只通过 agent-relay 的
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
  agent-relay（信箱为空），从不合并两个信箱。同一时间只允许一次迁移；agent-relay 自己的信箱服务在运行时也会拒绝（先关掉
  所有会话）。所有内容先在旁边准备好、核对数量后再整体换上，任何一步出错都换回迁移前的样子，没换成的那份留在
  `~/.agent-relay/.state-migration-failed-<时间>` 供查看。
- 迁移中途被打断（进程被杀、断电）时，`detect` 报告 `interrupted`，`migrate` 拒绝执行；关掉所有会话后运行
  `state_migration.py recover --confirm`，一律回到迁移前的样子，然后可以再迁移一次。这些目录都不会自动删除。
- 迁移成功后，被换下来的目标目录（含迁移前的信箱）留在 `~/.agent-relay/.state-migration-<时间>-<随机>/previous-*`，
  路径见结果里的 `previous`；确认迁移无误后可以自己删掉整个目录。
- 旧目录、宿主配置和权限文件一律不动；迁移后按提示接入新的宿主条目、用 Spec Guard 自己的卸载删掉旧条目，
  并把项目权限规则手动改成 `mcp__agent-relay__bridge_*`。旧目录确认无误后由你自己删除。

## 升级运行时

插件更新带来新版 bridge 时，`status` 会报告 `bridge.current: false`。agent 会先问你，在你关掉所有正在用信箱的
会话后再执行 `native_collaboration_runtime.py upgrade --confirm`：先把邮箱备份到 `~/.agent-relay/backups/<时间>/`，
在旁边装好新版，把 `mailbox/` 和 `data/` 挪过去再整体替换，核对通过才算完成，失败会自动换回。旧目录
`runtime.previous-<时间>` 保留，确认无误后由你删除；宿主接入不用动。新版 bridge 会把邮箱升级到 schema 5（从 schema 2 一次升到位，升级前自动备份）：
回到旧运行时还能打开它，但旧版 agent-relay 插件只认 schema 2（到 4），所以回滚时要连插件一起回滚，或者用备份恢复邮箱
（之后收到的消息会丢失）。

停 bridge 有两种方式，升级前任选其一，然后在“终端”里用 `pgrep -fl "agent-relay/runtime/dist/server.js"` 确认没有输出：

- **退出应用**：关掉所有 Claude Code 会话，⌘Q 退出 ChatGPT 应用（Codex 的 bridge 由它启动）。升级完成后重新打开即可。
- **只结束 bridge 进程**：`pkill -TERM -f "[a]gent-relay/runtime/dist/server.js"`（方括号让它不会匹配到执行它的 shell
  自己）。升级完成后，Claude Code 会话重开即可；ChatGPT 应用要 ⌘Q 完全退出再打开，否则已经打开的 Codex 线程会一直报
  “Transport closed”。

- **回滚**：同样关掉所有会话后执行 `native_collaboration_runtime.py rollback --confirm`，回到最新的
  `runtime.previous-<时间>`，信箱和数据一起带过去；先备份信箱，当前版本保留为 `runtime.rolled-back-<时间>`。
- **中途被打断**：升级、重装或回滚半路停下（进程被杀、断电），`~/.agent-relay/runtime-swap.json` 会留下记录，`status` 报
  `interrupted`，doctor 判为 fail，其他命令拒绝执行。关掉所有会话后执行 `native_collaboration_runtime.py recover --confirm`：
  一律回到切换前的运行时（不往前补完），没换成的那份保留为 `.runtime-<类型>-failed-<时间>`。之后可以再升级一次。
- `runtime.previous-*`、`runtime.rolled-back-*`、`.runtime-*-failed-*` 都不会自动删除，确认无误后由你删。

## 卸载

完整卸载按下面的顺序做（`collaboration-ops` skill 会逐步先问你），消息历史默认保留：

1. 关掉所有正在用信箱的会话（Claude 这一步要关掉**所有** Claude Code 会话，见第 3 步）。
2. `native_collaboration_runtime.py doctor`：看清当前接入了哪些宿主。
3. 移除宿主配置：`native_collaboration_adapters.py uninstall-codex --confirm-uninstall` 和
   `uninstall-claude --confirm-uninstall`。
   - 每次写宿主配置（安装和卸载都算）之前，都会先把要改的文件复制到
     `~/.agent-relay/backups/<UTC 时间>/host-config/`，并打印路径。这些副本可能含 MCP 的 API key 等凭据，
     目录和文件只有你自己能读（0700 / 0600），用完请自行删除。
   - Codex：连同你选"始终允许"时 Codex 写入的工具审批子表（只有一行 `approval_mode`）一起移除；node 换了版本也能
     识别。别的差异会逐行指出（只写行号和键名，不打印值），留给你处理。
   - Claude：移除 MCP 条目；若这台机器是 0.4.0 或更早装的，还会移除当时写下的 7 条禁用规则（0.5.0 起服务只提供
     十个信箱工具，安装不再写这些规则），其他设置不动。还有任何 Claude Code 会话开着（或这个运行时的 bridge 还在跑）
     时，只移除条目、保留 7 条规则：开着的旧版会话会按新设置重新过滤它缓存的工具列表，规则一删就会露出已删除的
     worker 工具。所以这一步由你在**关掉所有 Claude Code 会话之后、在终端里**执行；从任何 Claude
     会话里跑（包括让 agent 代跑）都会保留规则，并打印可以照抄的终端命令。
4. 移除运行时：`native_collaboration_runtime.py uninstall --confirm`。只删构建产物，`mailbox/`（消息历史和备份）
   和 `data/` 保留；以后再 `install` 会围绕它们重建。
5. 卸载插件：`claude plugin uninstall agent-relay@agent-relay-marketplace`；
   `codex plugin remove agent-relay@agent-relay-marketplace`。
6. 再跑一次 `doctor`（卸载插件前跑也可以）：宿主未接入、运行时已卸载并给出历史所在路径。

不再需要消息历史时，删除 `~/.agent-relay/` 由你自己来做。

## 文档

- [接口文档](docs/collaboration-interface.md)：工具、消息、状态、投递语义、身份、授权、委派与加固目标。
- [验收清单](docs/acceptance/checklist.md)：真实宿主验收步骤。
- [变更记录](CHANGELOG.md)：版本变化与已知问题。
- [运行时说明](plugins/agent-relay/references/collaboration-runtime.md)、
  [协作协议](plugins/agent-relay/references/collaboration-protocol.md)。

## 开发与 CI

本地验证：`bash scripts/validate.sh`（先在 `plugins/agent-relay/bridge` 里 `npm ci`，否则 bridge 部分显示 skip）。
每个 PR 和推到 `main` 的提交都会在 GitHub Actions 的 `macos-15` 上跑同一套验证，组合为 Python 3.9（苹果命令行工具自带）
/ 3.14 × Node 22 / 24，日志里有 doctor 的 `toolchain` 一行，写明实际用的 Python 与 Node。要把它设为 `main` 的必需检查：
仓库 Settings → Branches（或 Rules → Rulesets）→ 为 `main` 勾选 “Require status checks to pass”，选上四个
`Python … / Node …` 检查。是否这样设由维护者决定。

## 许可与致谢

agent-relay 以 [MIT 许可](LICENSE) 发布。
信箱运行时基于 Tesla Major 的 [claude-codex-mcp-bridge](https://github.com/WebisityStudio/claude-codex-mcp-bridge)（MIT），
固定提交 `8f12c88` 的副本收在 [`plugins/agent-relay/bridge/`](plugins/agent-relay/bridge/) 由 agent-relay 维护；
来源、许可原文和改动记录见 [`UPSTREAM.md`](plugins/agent-relay/bridge/UPSTREAM.md)。

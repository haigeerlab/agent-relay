# agent-relay

简体中文 | [English](README.en.md)

让**同一台 Mac** 上的 Claude Code 与 Codex 会话互相传话、按名字找到对方，并在你给出的有限授权内创建和继续
审查或开发会话。不用在会话之间手工复制粘贴，也不需要安装任何工作流插件。

agent-relay 原来是 [Spec Guard](https://github.com/haigeerlab/spec-guard-plugin) 的可选协作能力，现在拆成独立插件：
只想让会话互相通信的项目（例如设计项目）装它就够了。

> 状态：0.9.4（接口 2.10；不依赖 Spec Guard，同时安装时 Spec Guard 要 0.56.0 或更新）。变化、升级步骤见
> [CHANGELOG.md](CHANGELOG.md)，现在仍有效的问题见下文“[已知问题](#已知问题)”；各项目标见
> [docs/collaboration-interface.md](docs/collaboration-interface.md) 的“加固目标”栏。
>
> 装好插件后，对任意会话说一句“**检查一下 agent-relay 状态**”，它会告诉你还差哪几步（见“[快速上手](#快速上手)”）。

## 能做什么

| 能力 | 说明 | 入口 |
|---|---|---|
| 协作信箱 | 同一台 Mac 上的会话互相发消息、回复；跨宿主（Claude Code ↔ Codex）走一个私有的本机 bridge | `collab` skill |
| 会话路由 | 按会话名字联系另一个会话；同宿主优先用宿主自带的通信（Claude Code `SendMessage`、Codex App 线程），只有跨宿主才用信箱 | `session-routing` skill |
| 跨宿主会话委派 | 一句话让当前 Claude Code 创建 Codex 审查会话，或让 Codex 创建 Claude Code 开发会话（只有这两个方向，不做同宿主委派）；默认一个任务、一个新会话的有限授权，结果自动回到发起的会话（见“[委派：从头到尾](#委派从头到尾)”）。Claude Code 里装了 delegate 插件时，“派给 Codex”交给它，这里只做后备 | `session-delegation` skill |
| 运行时管理 | 查看、在你同意后安装本机信箱运行时，接入或移除宿主配置，退役结束的身份 | `collaboration-ops` skill；Claude Code 还有斜杠命令 `/agent-relay:collaboration`：查看运行时状态，经你同意后安装运行时、接入或移除宿主 |

## 需要什么

- macOS；Node.js 22.5 或更新（信箱运行时用的内置 `node:sqlite` 从 22.5.0 起才有）；Python 3.9 到 3.14
  （macOS 自带的 `/usr/bin/python3` 3.9 可用，3.9、3.10、3.14 都跑过全部测试）。
- agent-relay 的命令用宿主条目里固定的那个 node，不受当前 shell 的 PATH 影响；它低于 22.5.0 时直接拒绝
  （`node-too-old`），不会动宿主。选取顺序见[运行时说明](plugins/agent-relay/references/collaboration-runtime.md)。
- Claude Code 和／或 Codex（App 或 CLI）。

## 快速上手

### 1. 安装插件

Claude Code：

```bash
claude plugin marketplace add haigeerlab/agent-relay
claude plugin install agent-relay@agent-relay-marketplace
```

Codex（固定到发布的版本）：

```bash
codex plugin marketplace add haigeerlab/agent-relay --ref v0.9.4
codex plugin add agent-relay@agent-relay-marketplace
```

开发时也可以把上面的 `haigeerlab/agent-relay` 换成本地克隆的路径。两个宿主都要互通时，两边都装上。

### 2. 初始化：对会话说“检查一下 agent-relay 状态”

装上插件只会加载 skill 和命令，**不会**自动创建运行时，也不会改宿主配置。说了这句话后，agent 先只读检查，
告诉你需要做哪几步，每一步都等你同意：

1. 安装私有运行时：用插件自带、已核对哈希的 bridge 副本，在 `~/.agent-relay/runtime/` 构建运行时和私有邮箱（目录仅自己可读写）。
   不需要 git；`npm` 依赖仍按锁文件从 npm 源安装，所以这一步需要联网。
2. 接入宿主：给 Claude Code 注册用户级 MCP 服务 `agent-relay`，或在 Codex 配置里追加 `[mcp_servers.agent_relay]`。
   Codex 接入时会给 10 个信箱工具写 `approval_mode = "approve"`（读信、回复、确认不弹卡），
   执行时会列出写进 `~/.codex/config.toml` 的这 10 张审批表（`[mcp_servers.agent_relay.tools.<工具>]`）；
   已安装的用 `install-codex --approve-mailbox-tools` 补上，补的时候只列补上的。

之后**重启已经打开的会话**才能看到信箱工具。再跑一次
`python3 -B <插件目录>/hooks/native_collaboration_runtime.py doctor`（插件目录见“[找到插件目录](#找到插件目录)”），
各项为 ok 即可；`warn` 会写明下一步，有 fail 时退出码为 1。

### 3. 每个项目一次：信任项目

- Claude Code：第一次打开项目时的信任弹窗**默认选中的是 “No, exit”**，直接回车会退出，要先选到 “Yes”。
- Codex：在 App 里添加项目时，选“信任此文件夹”。

### 4. 可选：Claude Code 免掉信箱工具的确认弹窗

Claude Code 里 10 个信箱工具默认每次调用都弹确认。想一次性放行，运行
`python3 -B <插件目录>/hooks/native_collaboration_adapters.py claude-allow-rules`，把它打印的 10 条精确规则加进
`~/.claude/settings.json` 的 `permissions.allow`。加不加由你决定，agent-relay 不会改这个文件；Codex 已在接入时预先放行。

### 5. 每个会话一句话：加入联调

对会话说“**加入本机联调并允许唤醒，名字用 X**”。

- 不说“允许唤醒”，别的会话发来消息时它不会被叫醒，要自己查收件箱。
- 任何权限模式都能加入，包括 Claude 的 auto 模式；例外是 **Bypass permissions**，它会把来信提醒扣到过期
  （见“[授权与安全](#授权与安全)”）。
- 名字被一个已经停止的旧会话占着时，换一个名字最省事。一定要用原名：先问“有哪些会话”，确认占着它的会话是 `stopped`，
  再说“接管这个名字”并明确同意，会话会带 `takeover: true` 重新注册；占着它的 Claude 会话还在运行时会被拒绝
  （`holder-still-running`），先关掉那个会话或换个名字。
- 之后不想再被唤醒：说“取消唤醒”，会话用 `wake: null` 重新注册，排着还没送出的提醒一起取消；身份和消息都保留。

### 6. 发出第一条消息后你应该看到什么

在 Claude Code 里说“告诉 Codex 里的 X：首页稿子在 `designs/home.fig`，请确认”：

1. 发件的会话按名字找到 X，发出消息，告诉你消息编号（`#编号`）和投递状态：一般先是 `queued`，送进对方后变成
   `accepted`。发给 Claude 会话的消息常常停在 `unknown`，直到对方读到才变成 `accepted`，这是正常情况，**不要重发**
   （见“[常见问题](#常见问题与故障处理)”）。
2. 对方会话绑定了唤醒时会被叫醒，读信、处理，处理完确认（ack）；你的消息是提问或派活时，它会带 `replyTo` 回复你。
3. 回复到了，发件的会话会被唤醒（它也绑定了唤醒时）或在你下次问“查看联调消息”时看到。
4. 发件结果里带警告时照着做：例如对方没绑定唤醒、对方会话已停止或在等授权。

同宿主之间（Claude ↔ Claude、Codex ↔ Codex）优先走宿主自带的通信，不经过信箱，所以不会有消息编号。

## 日常用法

直接用自然语言说，不需要记工具名或内部 ID：

- “加入本机联调”“查看联调消息”“现在有哪些会话” → 加入信箱、看收件箱和通讯录。
- “告诉 Codex 里设计项目的那个会话：首页稿子在 `designs/home.fig`，请确认” → 按名字找到会话并发消息；
  有同名会话时会给出短编号让你选。
- “回复一下刚才那个会话” → 回复最近的来信。
- “创建一个 Codex 审查，看看这次改动” → 创建一个只读的审查会话，结果回到当前会话（见“[委派：从头到尾](#委派从头到尾)”）。
- “继续刚才的会话”“停掉那个审查” → 同一会话第二轮、停止。
- “我发出的哪些还没人回”“我在等谁” → 列出经信箱发出、标了要回复（`expectsReply`）却还没收到回复的请求，最老的在前，
  每条写明已等多久和对方的状态（`bridge_outbox` 带 `awaitingReply`）；“谁欠回复”“别人在等我回复什么” → 每个会话被
  别人等着回复的请求数和最早一条的时间（`bridge_agents` 的 `owesReplies`）。提问或派活时会话自己会标上要回复，收到的
  会话处理完必须带 `replyTo` 回复，只 ack 不算；只是告知的消息不标，不会出现在这里。
- “我在信箱里是谁” → 本会话的身份、宿主、会话标题和项目（`bridge_sessions` 的 `whoami`）。
- “刚才那条消息怎么样了”“等它回复” → 按消息编号查状态，或一直等到它被确认、回复、失败或过期
  （`bridge_wake_status` / `bridge_wait` 带 `messageId`，等待时不替谁确认消息）。
- 长消息（`long-messages`）：发送结果只回编号和长度，不回显正文；收件方一页读不完时，结果里的 `continue` 行写明下一次
  `bridge_inbox` 的参数（`messageId`、`bodyOffset`），一段段读完即可，不需要 Bash。每页按大约 1.2 万个 token 控制，
  中文和英文都不会超过宿主的输出上限。
- 长正文或带 `$`、反引号、引号的正文 → 先写进文件，再用 `bodyFile` 发，内容逐字节不变（绝对路径、自己的普通文件、
  不超过 256 KiB、UTF-8）。
- “检查一下 agent-relay 状态” → `native_collaboration_runtime.py doctor`：只读检查运行时、信箱、宿主接入、Codex
  审批模式和已绑定唤醒的会话（会话卡在等待输入时会提示），每项给出下一步；有 fail 时退出码为 1。
- “退役 X 这个身份” → 用完的名字不再出现在通讯录里，历史保留。由你点名或确认清单后，agent 运行
  `python3 -B <插件目录>/hooks/native_collaboration_retire.py --name <名字> --confirm-retire`（可加 `--note <说明>`）；
  这个身份还有没确认（ack）的消息时拒绝执行（已过期的不算），要先读完并确认。会话自己不能退役身份。
- 想再用一个已退役的名字 → 注册会被拒绝；经你同意后，会话注册时带 `reactivate: true` 重新启用它，或者换个新名字。
- 自检和版本：`native_collaboration_runtime.py probe` 用一次性的临时数据启动运行时、确认它能正常应答，不碰真实信箱；
  `status` 只读报告运行时是否就绪；`~/.agent-relay/bin/agent-relay --version` 报运行时的版本。

### 10 个信箱工具

平时不用直接调用，agent 按你的话选用；在权限弹窗、`claude-allow-rules` 和发件结果里会看到这些名字
（Claude Code 里全名是 `mcp__agent-relay__<工具>`）。参数和返回值见[接口文档](docs/collaboration-interface.md) §2.1。

| 工具 | 作用 |
|---|---|
| `bridge_register` | 注册本会话的名字，可选绑定唤醒（`wake`）；接管别人的名字要 `takeover`，重新启用退役的名字要 `reactivate` |
| `bridge_send` | 发消息：`replyTo` 回复某条、`expectsReply` 标成要回复的请求、`idempotencyKey` 防重发、`bodyFile` 从文件读正文 |
| `bridge_inbox` | 读收件箱（从旧到新，长消息分页）；本人读到才记为已读 |
| `bridge_ack` | 标记已处理，历史保留 |
| `bridge_outbox` | 我发出的消息处理到哪一步；带 `awaitingReply` 只列还在等回复的请求 |
| `bridge_agents` | 通讯录：每个会话的状态、未处理消息、欠的回复 |
| `bridge_sessions` | 本机运行中的 Claude 会话，以及“我是谁”（`whoami`） |
| `bridge_wake_status` | 唤醒记录；带 `messageId` 查某条消息的进度 |
| `bridge_thread` | 按线程看整段对话 |
| `bridge_wait` | 在当前这一轮里等新消息，或等某条消息出结果 |

## 委派：从头到尾

委派是让一边新开一个受限会话去干活，只有 Claude Code → Codex 和 Codex → Claude Code 两个方向；同宿主委派会被拒绝
（`same-host-unsupported`），在同一个宿主里直接开新会话即可。

### 开始之前

- **发起委派的会话先加入联调并允许唤醒**，结果才能自动回到它这里。发起的会话没有绑定唤醒的身份（或绑了不止一个）时，
  委派照样能创建，但结果标为 `recipient-unavailable`，不会自动唤醒你，agent 会告诉你先加入。发起的会话处在 Bypass 模式时
  结果照样存进信箱，只是唤醒提醒会被 Claude Code 扣到过期（见“[授权与安全](#授权与安全)”）；说一句“查看联调消息”就能看到结果。
- **目标是 Claude Code 时**，目标项目要被信任过，并且项目的 `.claude/settings.json` 或 `.claude/settings.local.json`
  里要有 10 个信箱工具的 allow（`mcp__agent-relay__bridge_*`）。只在用户级 `~/.claude/settings.json` 里配不算，
  因为委派会话默认只读项目两层设置；除非用了下面的“加载用户环境”。只读审查不需要另外允许 `Read`／`Grep`／`Glob`；
  开发才需要 `Edit`、`Write` 和符合任务范围的 `Bash(...)`。agent-relay 会读取并复用这些项目级 allow，但不会替你写。
- 想先确认配够了没有，问一句“委派前检查一下权限”：agent 运行只读的 `permissions`，列出需要的 allow、实际读了哪些
  设置文件和还缺什么，不写任何文件。

### 一次委派的经过

1. 你说“创建一个 Codex 审查，看看这次改动”。这句话本身就是“一个会话、一个任务”的授权。
2. agent 显示一条**不阻塞的创建通知**：目标宿主、项目简称、baseline 短标识、权限（默认 `safe-review`，只读）、
   数量 1 和到期时间（默认 8 小时），然后直接创建，不再问你一遍。想每次都先问你，就说“每次启动前都问我”。
3. 目标会话在自己的宿主里干活；需要它自己的设置里没有的权限时，它照常弹窗找你。
4. 干完后，目标会话把简短结果经信箱发回发起的会话，发起的会话被唤醒并读到它。结果里的 `resultDelivery`
   为 `enqueued` 只表示已经写进信箱，不表示你这边已经读过；`pending`、`missing`、`unverified`、`recipient-unavailable`
   各有含义，agent 会原样告诉你。
5. 之后可以说“继续刚才的会话”（同一个会话第二轮）、“刚才那个审查怎么样了”或“停掉那个审查”。
   同名时 agent 给出短区分项让你选。

两种权限：默认 `safe-review` 只读所选项目、diff 并做本地只读验证；`bounded-development` 只在你选的干净独立 worktree 里
写源码和验证。push、merge、发布、远端事项写入、删除和全局配置都要另外授权。

### 被 held 了怎么办

缺前置条件时，委派不会启动一个半残的会话，而是显示 `held` 和一个最小的下一步。agent-relay 不会替你改设置、接受信任
或改成 bypass，补好之后再说一次即可。

| 显示 | 原因 | 怎么补 |
|---|---|---|
| `held/project-allow-rules` | 目标项目缺少信箱工具的 allow | 把它列出的规则加进目标项目的 `.claude/settings.json` 或 `.claude/settings.local.json` |
| `held/project-trust` | 你还没在 Claude Code 里信任目标项目 | 在 Claude Code 里打开这个项目，信任弹窗选 “Yes” |
| `held/mcp-project-approval` | 目标项目还没接受这次的临时 MCP | 按提示在 Claude Code 里批准 |
| `held/host-permission-prompt` | 宿主仍要人工做一个权限决定 | 按提示处理那个权限 |
| `held/identity-retired` | Codex 委派用的信箱身份已经退役，追问的结果回不来，所以没发出 | 新建一个委派，或由你决定恢复这个名字 |

### 可选项

- **只审某些文件**：说“只审 `src/` 和 `README.md`”，范围写进给会话的约束，结果末尾列出实际读过的文件。Claude Code
  会话另有钩子硬性拒绝范围外的读取；Codex 会话只靠约束。只用于只读审查。
- **加载用户环境**（只用于 Codex → Claude Code，默认关）：说“加载我的用户环境”，委派出来的 Claude Code 会话会带上你自己的
  设置、插件和 skill，这时用户级 allow 也算数，但要在 allow 里加上 `Skill`；缺了会在启动前显示 held 和要补的规则。
- **清理卡住的委派记录**：说“清理卡住的委派”，agent 先只读列出记录（名称、短编号、状态、宿主是否还在）给你看，你确认后
  才把选中的标为取消；只改记录，不删除，也不碰宿主。

## 常见问题与故障处理

**信箱工具报 `Transport closed`**
这个会话和信箱的连接断了，通常是运行时刚升级或 bridge 进程被结束，重试不会好转。Codex：用 ⌘Q 完全退出 ChatGPT
应用再打开；Claude Code：新开一个会话。连上之后先用原名重新登记一次再继续。

**消息一直是 `unknown`**
唤醒结果说不清时就标为 `unknown`，bridge **绝不自动重发**，你也不要重发。发给 Claude 会话时，对方没被扣住时
Claude Code 通常不给回执，消息会一直是 `unknown`，直到对方读到才变成 `accepted`，这是正常情况。想知道进展，问
“刚才那条消息怎么样了”或“等它回复”。

**发送报错**
`bridge_send` 报错就说明这条没有存下。存下之后的步骤失败（例如数据库忙）时不报错，而是返回已存的编号并附警告
“Saved as #编号; … Do not send it again.”，唤醒由后台稍后重试。

**发给 Claude 会话的提醒被扣（held）、最后过期**
对方处于 Bypass permissions 时，Claude Code 会把提醒扣下等你批准，桌面应用里没有批准入口。见“[授权与安全](#授权与安全)”
的第一条。会话刚启动时 Claude Code 也会把提醒扣住几秒再自动放行，这不是 Bypass；bridge 要扣满 90 秒才通知发信方，
扣住期间不要重发。

**委派显示 `held/...`**
见“[被 held 了怎么办](#被-held-了怎么办)”。

**Codex 会话显示 `not-loaded`**
ChatGPT 应用这次启动后还没打开过这个任务。在 ChatGPT 里点开它，消息就会送达；这不是连接或身份故障。ChatGPT 刚启动、
正在加载很多任务时，2 秒内没回应也会暂时显示为 `not-loaded`，下一次调用会纠正。

**发送或 ack 被拒，说名字不是本会话注册的、或记在一个 Codex 任务名下**
bridge 重启后（Codex 还包括 ChatGPT 重启或长时间闲置的任务重新打开后），会话要用原名重新登记一次，再重做刚才那一步。
不需要接管（takeover）。

**Claude 会话没在运行，消息送不进去**
Claude 桌面应用会在会话空闲时停掉它的进程。消息照旧排队，满 5 分钟会通知你；打开那个会话后消息就会送进去。发件方用
`bridge_outbox` 能看到 `pendingReason` 是 `offline`。

**会话在等你授权**
通讯录里会写明。Claude 会话卡在授权弹窗上时，这台 Mac 会弹一条通知；Codex 任务（ChatGPT 已加载的）在批准框或等你回答
时，通讯录报 `waiting-approval` 或 `waiting-input`，但不弹通知，要到 ChatGPT 应用里处理。

**升级后传新参数被拒（`expected boolean`）**
已经开着的会话拿到的还是旧的工具定义。Claude Code 新开会话，Codex 新开任务。

**没看到通知**
多数 Mac 上 `osascript` 的通知会被悄悄丢掉。装上 terminal-notifier 并在第一次弹出时允许它；
`doctor --test-notification` 会弹一条测试通知。详见[通知与投递细节](docs/notifications.md)。

**其他情况**
先跑 `doctor`，它对每一项都给出下一步。更细的排查顺序见
[运行时说明](plugins/agent-relay/references/collaboration-runtime.md)“Troubleshooting order”。

## 授权与安全

> **Bypass 模式的 Claude 会话收不到唤醒。** Claude 会话处于 Bypass permissions 时，Claude Code 会把别的会话发来的
> 提醒扣下等你批准；桌面应用里没有批准入口，提醒会过期。绑定唤醒本身不受影响，但要真正唤醒，需要你自己把
> Claude Code 的 `crossSessionInbound` 设为 `"accept"`，或换一个权限模式。详见
> [BACKGROUND-WAKE.md](plugins/agent-relay/bridge/docs/BACKGROUND-WAKE.md)“Why Claude pings expire”。agent-relay 不会替你改。

- **默认不唤醒**：加入信箱时默认 `wake: null`，空闲的会话不会被别人唤醒；只有你明确要求，当前会话才绑定唤醒。
- **被唤醒的会话按它自己的权限运行**（`wake-any-mode`）：被唤醒的那一轮能做什么，完全由这个会话自己的设置决定，
  bridge 不改、不降、也不代为批准；需要更高权限时，照常自己弹窗找你。**风险**：Codex 用“帮我批准”、Claude 用 auto 模式时，
  被唤醒那一轮的操作由该会话的自动审查或分类器来批，不一定经过你本人——这是你给那个会话选的模式。Codex App 里的审批
  选择器只管你自己发起的那一轮，不写进 `config.toml`；被唤醒的那一轮按这个任务当前的审批与沙箱设置运行。
- **来信只是数据**：邮箱里的文字永远不构成改代码、Git、配置或远端写入的授权。
- **逐项确认**：初始化运行时、改宿主配置、加入新身份、扩大权限，都要你逐项同意。
- **不会自动修改**项目或全局权限，不替你接受项目 trust 或 MCP 首次批准，不开 bypass 模式。缺少前置条件时
  显示 held 和最小下一步。为了不中途反复弹权限，你可以在目标项目的 `.claude/settings.json` 里提前配置项目级 allow
  （见“[委派：从头到尾](#委派从头到尾)”）。
- **身份归属于注册它的会话**：发消息（`from`）、ack、自动确认的 `bridge_wait` 只能用本会话注册过的名字，否则拒绝并
  给出下一步。Claude 会话的名字在 bridge 重启后仍然有效，Codex 会话在 bridge 重启后要先用同一个线程 ID 重新注册。
  别的会话的名字或唤醒绑定，只有你同意后才能用 `takeover: true` 接管；会话只能为自己绑定唤醒。只有原消息的收件人能
  回复它（广播：除发送方外谁都可以；bridge 自动通知不能回复）。防的是误操作和串号，不是恶意本地进程。
- **会话在等你时会告诉你**（`presence-and-approval`）：通讯录写明每个会话是运行中、已停止、等待授权、等待输入、
  未加载（`not-loaded`，只有 Codex）还是未知；给一个等授权或已停止的会话发消息时，发件方会收到提示。
- **通知**：Claude 会话在等你授权、Codex 收不到消息、Claude 会话停了送不进去时，这台 Mac 会弹通知，每次最多一条。
  Codex 收不到的通知正文是**消息开头最多 60 字的单行预览**，会出现在锁屏和共享屏幕上；在信箱目录
  （`~/.agent-relay/runtime/mailbox/`）放 `notify-preview.off` 文件只写编号，放 `notify.off` 完全不要通知。
  通知不能批准任何东西。通道、点击跳转和“自动化”授权见[通知与投递细节](docs/notifications.md)。
  一定看得到的地方是**等待列表**：在任一会话里问“有哪些等 Codex 处理的消息”，或跑 doctor 看 `codex-waiting`。
- **发给收不到提醒的身份时会提示发件方**：收件方既没绑定唤醒、bridge 也不知道它在哪个宿主（例如 Codex 以 `wake: null`
  注册）时，发件结果带一条警告：对方要自己查收件箱才会看到。这种情况不弹通知，因为不知道该提醒谁。
- **不保证“恰好送达一次”**：每条单发消息都有投递状态（`queued`、`sending`、`accepted`、`failed`、`unknown`、
  `expired`），说不清时标为 `unknown`，绝不自动重发；排队超过时限（默认 24 小时）还没被取走就标为 `expired`，
  发件人会收到通知。排队上限、`idempotencyKey` 和回复的规则见[通知与投递细节](docs/notifications.md#投递)和接口文档 §6。

## 已知问题

只列现在仍有效的；各版本当时的说明见 [CHANGELOG.md](CHANGELOG.md)。

- **脚本身份没法确认（ack）收到的消息**（0.9.3 发现）：CLI 没有 `inbox`／`ack` 命令，会话用 `bridge_ack` 代它确认也会被
  拒绝。发给脚本身份的消息只能等过期（默认 24 小时），在那之前这个身份也退役不了。脚本也读不到回复的正文，所以脚本发的
  应是通知，不要带 `--expects-reply`。
- **发给 Claude 会话的消息常停在 `unknown`**（0.9.4 验收）：对方没被扣住时 Claude Code 通常不给回执，直到对方读到才变成
  `accepted`。不要因此重发。
- **停掉的 Claude 会话叫不醒**（0.9.0）：Claude 桌面应用停掉的会话，谁发信都叫不醒，消息排队并在 5 分钟后通知你。
- **Codex 任务在 ChatGPT 重启后第一次信箱调用会被拒一次**（0.7.1）：bridge 认不出调用它的 Codex 任务，会话按报错用原名
  重新登记后重做即可。
- **ChatGPT 刚重启、还没打开的任务报 `not-loaded`**（0.8.3），不会报等待状态。
- **Codex 的等待状态只在真实宿主上核对过运行命令批准和提问**（0.8.4）：改文件、权限申请、MCP 工具提问只有单元测试。
- **已经开着的请求不会自动关闭**（0.8.0）：要由收件方用 `alsoAnswers` 或发件方用 `withdraws` 清理；以结果里的 `closed` 为准。
- **还没在真实宿主上用 launchd 实测**（0.9.0）。

## 不做什么

- 不跨机器，只在同一台 Mac 上工作；不提供网络服务，不把信箱暴露给别的机器。
- 不是事项系统或任务派发器，没有项目组、领取或排期。
- 不带任何开发工作流（Spec、计划、阶段提示等属于 Spec Guard）。
- 不承诺“恰好送达一次”；“宿主已接收”不等于“对方已处理”（见接口文档 §6）。

## 脚本与 launchd

脚本和 launchd 任务（PATH 只有 `/usr/bin:/bin`、读不了 `~/Documents`）用 `~/.agent-relay/bin/agent-relay` 读信箱和发信，
它由 `install`、`upgrade` 写好，写死了 node 和运行时的绝对路径。`agents`、`outbox <名字>`、`sessions` 只读，输出与
对应 MCP 工具逐字段相同；`send` 只能以用户确认登记的脚本身份发信，正文从 `--body-file` 或标准输入读：

```bash
~/.agent-relay/bin/agent-relay register-script-identity my-patrol --confirm
printf '巡检发现 #12 未处理' | ~/.agent-relay/bin/agent-relay send --from my-patrol --to some-agent
```

命令清单、退出码和唤醒的限制见接口文档 §2.4。脚本身份不能确认收到的消息、读不到回复正文，见“[已知问题](#已知问题)”。

## 更新与升级

### 更新插件

Claude Code 会话在**启动时**定下用哪一份插件，之后一直用这一份：已经开着的会话、关掉应用后重新打开、恢复
（resume）原来的会话，都还是旧的那份。更新插件后要**新开一个会话**（包括桌面应用的 Code 标签页）才会用上新版。
信箱工具的参数定义也一样：已开着的 Claude Code 会话重连 MCP 也拿不到新参数，传新参数会被拒绝（`expected boolean`）；
要用新参数，Claude Code 新开会话，Codex 新开任务。

- **从本地克隆装的**：Claude 新会话直接读克隆目录，`git -C <克隆> pull --ff-only` 之后新开会话即可。用户级记录在
  `claude plugin list` 里的版本标签不会跟着变，doctor 会因此报 warn；再跑
  `claude plugin marketplace update agent-relay-marketplace` 和
  `claude plugin update --scope user agent-relay@agent-relay-marketplace` 刷新它，这两步只改标签。Codex 再执行一次 `codex plugin add agent-relay@agent-relay-marketplace`。
- **从 GitHub 装的**：先 `claude plugin marketplace update agent-relay-marketplace`，再
  `claude plugin update --scope user agent-relay@agent-relay-marketplace`。不带 `--scope` 时这条命令只更新“当前目录”
  那条项目级记录，不更新用户级安装。之后新开会话。
- **Codex**：更新插件后用 ⌘Q 完全退出 ChatGPT 应用再打开，已经打开的线程才会连上新版。

`python3 -B <插件目录>/hooks/native_collaboration_runtime.py doctor` 的 `claude-plugin` 一项会核对新会话会加载的那份
副本的版本（读副本里的 `plugin.json`，不看 `claude plugin list` 显示的版本），不一致时给出要执行的命令。
`claude plugin list` 显示的版本与 doctor 报的不一致时，那是那条记录上的旧标签，不代表加载了旧版；doctor 会给出 warn，
列出这些记录和清理命令（逐个目录 `claude plugin uninstall --scope local` 或更新记录），由你逐条执行，doctor 自己不动手。
目录已删的记录不告警，也不列出，只计数并说明可以留着、或照它给的办法删掉；project scope 的记录只给说明、不给命令，因为改它会改
那个仓库里提交的 `.claude/settings.json`。
插件里带了新版 bridge 运行代码时（bridge 里只改了测试或文档不算），还要按下一节升级运行时；CHANGELOG 每一版的开头会写明要不要。

### 升级运行时

**先更新插件，再升级运行时**：新版 bridge 可能把信箱升到新的 schema（0.7.0 升到 6），旧版插件的钩子读不了新 schema，
退役命令和委派会因此停下。所以先把两个宿主的插件都更新到新版（新开会话、⌘Q 重开 ChatGPT），再做下面的升级。

插件更新带来新版 bridge 运行代码时，`status` 会报告 `bridge.current: false`（bridge 里只改了测试或文档不算）。
agent 会先问你，在你关掉所有正在用信箱的会话后再执行 `python3 -B <插件目录>/hooks/native_collaboration_runtime.py upgrade --confirm`：先把邮箱备份到 `~/.agent-relay/backups/<时间>/`，
在旁边装好新版，把 `mailbox/` 和 `data/` 挪过去再整体替换，核对通过才算完成，失败会自动换回。旧目录
`runtime.previous-<时间>` 保留，确认无误后由你删除；宿主接入不用动。新版 bridge 会把邮箱升级到 schema 7（从更早的 schema 一次升到位，升级前自动备份）：
回到旧运行时还能打开它，但旧版 agent-relay 插件读不了新 schema（0.7.x 最多认到 6），所以回滚时要连插件一起回滚，或者用备份恢复邮箱
（之后收到的消息会丢失）。

停 bridge 有两种方式，升级前任选其一，然后在“终端”里用 `pgrep -fl "agent-relay/runtime/dist/server.js"` 确认没有输出：

- **退出应用**：关掉所有 Claude Code 会话，⌘Q 退出 ChatGPT 应用（Codex 的 bridge 由它启动）。升级完成后重新打开即可。
- **只结束 bridge 进程**：`pkill -TERM -f "[a]gent-relay/runtime/dist/server.js"`（方括号让它不会匹配到执行它的 shell
  自己）。升级完成后，Claude Code 会话重开即可；ChatGPT 应用要 ⌘Q 完全退出再打开，否则已经打开的 Codex 线程会一直报
  “Transport closed”。

升级成功时，输出的 `next` 会提醒你重开 ChatGPT 应用。之后 doctor 的 `codex-restart` 一项会比较 ChatGPT 应用的启动时间
和最近一次升级（最新的 `runtime.previous-<时间>`）：应用还是升级前打开的就报 warn，重开后变成 ok。终端里运行的
`codex` 会话升级后同样要重开，doctor 看不出来。

- **回滚**：同样关掉所有会话后执行 `python3 -B <插件目录>/hooks/native_collaboration_runtime.py rollback --confirm`，回到最新的
  `runtime.previous-<时间>`，信箱和数据一起带过去；先备份信箱，当前版本保留为 `runtime.rolled-back-<时间>`。
- **中途被打断**：升级、重装或回滚半路停下（进程被杀、断电），`~/.agent-relay/runtime-swap.json` 会留下记录，`status` 报
  `interrupted`，doctor 判为 fail，其他命令拒绝执行。关掉所有会话后执行 `python3 -B <插件目录>/hooks/native_collaboration_runtime.py recover --confirm`：
  一律回到切换前的运行时（不往前补完），没换成的那份保留为 `.runtime-<类型>-failed-<时间>`。之后可以再升级一次。
- `runtime.previous-*`、`runtime.rolled-back-*`、`.runtime-*-failed-*` 都不会自动删除，确认无误后由你删。

升级后每个会话先用原名重新注册一次（记下所属会话）。

## 卸载

完整卸载按下面的顺序做（`collaboration-ops` skill 会逐步先问你），消息历史默认保留：

1. 关掉所有正在用信箱的会话（Claude 这一步要关掉**所有** Claude Code 会话，见第 3 步）。
2. `python3 -B <插件目录>/hooks/native_collaboration_runtime.py doctor`：看清当前接入了哪些宿主。
3. 移除宿主配置：`python3 -B <插件目录>/hooks/native_collaboration_adapters.py uninstall-codex --confirm-uninstall` 和
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
4. 移除运行时：`python3 -B <插件目录>/hooks/native_collaboration_runtime.py uninstall --confirm`。只删构建产物，`mailbox/`（消息历史和备份）
   和 `data/` 保留；以后再 `install` 会围绕它们重建。
5. 卸载插件：`claude plugin uninstall agent-relay@agent-relay-marketplace`；
   `codex plugin remove agent-relay@agent-relay-marketplace`。
6. 再跑一次 `doctor`（卸载插件前跑也可以）：宿主未接入、运行时已卸载并给出历史所在路径。

不再需要消息历史时，删除 `~/.agent-relay/` 由你自己来做。旧版本在信箱目录留下的 `codex-gate.off` 已不再使用，
可以删掉（agent-relay 不会替你删）。

## 进阶设置

### 找到插件目录

上文的命令都写成 `<插件目录>/hooks/…`。插件目录是宿主实际加载的那份插件（从 GitHub 装的在宿主的插件缓存里，从本地克隆
装的就是克隆里的 `plugins/agent-relay`），可以这样查：

```bash
claude plugin list --json | python3 -c 'import json,sys; ps=[p for p in json.load(sys.stdin) if p.get("id","").startswith("agent-relay@") and p.get("enabled")]; p=next((p for p in ps if p.get("scope")=="user"), ps[0] if ps else {}); print(p.get("readFromFolder") or p.get("installPath") or "")'
codex plugin list --json | python3 -c 'import json,sys; print(next((p["source"]["path"] for p in json.load(sys.stdin).get("installed",[]) if p.get("name")=="agent-relay" and p.get("enabled") and (p.get("source") or {}).get("path")), ""))'
```

第一条用于 Claude Code，第二条用于 Codex；两个都装了时，任选一个打印出来的目录即可。让 agent 去做时不用管这一步，
技能会自己找到插件目录。

### 换一个状态目录

运行时、邮箱、委派记录和迁移备份默认都在 `~/.agent-relay/`。设置环境变量 `AGENT_RELAY_HOME`（必须是绝对路径，
相对路径会直接报错）可以把它们整体换到别处，所有 agent-relay 命令都会改用这个目录；命令行里显式给出的 `--root`、
`--state-root` 仍然优先。注意：接入宿主时写进宿主配置的是当时解析出的绝对路径，之后再改这个变量**不会**挪动
已经接入的宿主，要在新目录下重新安装运行时并重新接入宿主才会生效。

## 与 Spec Guard 的关系

两个插件互相独立，可以只装其中一个。同时安装时，Spec Guard 读取本插件根目录的
[`interface.json`](plugins/agent-relay/interface.json)（接口 2.10；Spec Guard 0.56.0 起接受 `>=1.0,<3.0`）判断 agent-relay 是否可用，只通过 agent-relay 的
skill 名使用协作；未安装时 Spec Guard 的工作流照常运行，只在需要协作的步骤提示安装。

### 从 Spec Guard 的协作能力迁移

用过 Spec Guard 内置协作的话，旧数据在 `~/.spec-guard/native-collaboration/` 和 `~/.spec-guard/session-delegation/`。
让 agent 走 `collaboration-ops` 的迁移步骤，或自己运行：

```bash
python3 -B <插件目录>/hooks/state_migration.py detect
python3 -B <插件目录>/hooks/state_migration.py migrate --confirm
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

## 术语表

| 术语 | 意思 |
|---|---|
| 宿主 | 会话跑在哪个应用里：Claude Code（CLI 或桌面应用）或 Codex（ChatGPT 应用或 CLI） |
| 信箱 | 本机的一个私有 SQLite 邮箱，所有经 agent-relay 的消息都存在这里，在 `~/.agent-relay/runtime/mailbox/` |
| bridge | 每个会话里连着信箱的那个 MCP 服务（`agent-relay`），提供 10 个 `bridge_*` 工具，负责投递和唤醒 |
| 运行时 | `~/.agent-relay/runtime/` 下构建好的 bridge 程序和信箱；`install`／`upgrade` 管它 |
| 身份 | 会话在信箱里注册的名字；归注册它的会话所有，用完可以退役 |
| 唤醒绑定 | 把身份绑到当前会话（`wake`），有信来时 bridge 叫醒这个会话；默认不绑 |
| 脚本身份 | 用户在终端登记、给脚本和 launchd 发信用的身份，只能发不能确认 |
| 投递状态 | 一条单发消息走到哪一步：`queued`、`sending`、`accepted`、`failed`、`unknown`、`expired` |
| `held` | 两种意思：委派缺前置条件、没有启动（`held/<原因>`）；或者 Claude Code 把发给某个会话的提醒扣住了 |
| `expectsReply` | 发件方把消息标成“要回复的请求”；收件方处理完要用 `replyTo` 回复，只 ack 不算 |
| `not-loaded` | Codex 任务所在的 ChatGPT 应用这次启动后还没打开过它 |
| 委派 | 一边新开一个受限的会话去另一个宿主干活，结果经信箱回来 |

## 文档

- [接口文档](docs/collaboration-interface.md)：工具、消息、状态、投递语义、身份、授权、委派与加固目标。
- [通知与投递细节](docs/notifications.md)：通知通道、点击跳转、预览开关，以及排队上限、重试 key 和回复规则。
- [变更记录](CHANGELOG.md)：版本变化与升级步骤。
- [安全说明](SECURITY.md)：防护范围、信任边界与如何报告安全问题。
- [后台唤醒](plugins/agent-relay/bridge/docs/BACKGROUND-WAKE.md)：唤醒的实现方式与 Claude 提醒过期的原因。
- [运行时说明](plugins/agent-relay/references/collaboration-runtime.md)、
  [协作协议](plugins/agent-relay/references/collaboration-protocol.md)。
- 参与开发、跑测试、发版：见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可与致谢

agent-relay 以 [MIT 许可](LICENSE) 发布。
信箱运行时基于 Tesla Major 的 [claude-codex-mcp-bridge](https://github.com/WebisityStudio/claude-codex-mcp-bridge)（MIT），
固定提交 `8f12c88` 的副本收在 [`plugins/agent-relay/bridge/`](plugins/agent-relay/bridge/) 由 agent-relay 维护；
来源、许可原文和改动记录见 [`UPSTREAM.md`](plugins/agent-relay/bridge/UPSTREAM.md)。

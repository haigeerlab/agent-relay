# Claude 桌面版与 Codex 桌面版的宿主差异（多会话协作视角）

| 项 | 内容 |
|---|---|
| 文档日期 | 2026-10-17（原文初版）；2026-11-22 迁入本仓库 |
| 来源与维护 | 原文在 decision-inbox 仓库的 `docs/host-differences.md`，最后更新 2026-10-19，编到 H26。decision-inbox 已于 2026-11-19 停止维护，原文保留不动。2026-11-22 迁入 agent-relay，此后由 agent-relay 维护，新条目和更正都改这一份 |
| 适用范围 | 同一台 Mac 上，用 Claude 桌面版（Claude Code）与 Codex 桌面版（ChatGPT 应用内的 Codex）同时跑多个 AI 编码会话、并通过 agent-relay 互相协作 |
| 用途 | 开发 agent-relay 以及 spec-guard、module-crew 这类跨宿主插件时，作为两个宿主行为差异的依据 |
| 证据来源 | 2026-10-13 至 2026-10-16 在一个真实多会话协作组（5 条开发线 + 总协调 + 负责人 + 收件枢纽）上的观测；之后各条目注明的真实宿主验收；spec-guard、agent-relay 的设计文档 |

迁入时做了去敏：协作组、测试组和需求模块的代号、邮箱消息编号、决定编号改成了泛称，事实本身不变。文中「收件枢纽」「巡视」「onboard」「doctor」等说的是 decision-inbox 当时的角色和命令。

## 证据等级

| 标记 | 含义 |
|---|---|
| **实测** | 在下文列出的版本上亲自观测或复现过，附时间和现象 |
| **文档** | 来自 spec-guard / agent-relay 仓库已发布的设计文档或升级说明，未在本次逐项复现 |
| **未验证** | 合理推断或尚未测试，不能作为设计依据 |

宿主行为会随版本变化。引用本文结论前，先用第 6 节的命令核对版本；版本不同的，按「未验证」对待。

---

## 1. 结论摘要

1. **会话生命周期相反**：Claude 桌面版会**挂起空闲会话**，agent-relay 叫不醒，只能由另一个 Claude 会话用桌面版自带的会话消息工具叫醒；Codex 桌面版的空闲会话能被 agent-relay 直接叫醒，但**应用一重启，所有会话都不会自动加载**，必须用户逐个点开。（H1、H2、H4）
2. **Codex 会话会丢联调身份**：长时间空闲或应用重启后，会话常以「不是本会话的身份」读不到自己的消息，需用原名重新登记；期间即使会话在运行，agent-relay 仍判它离线。（H3）
3. **Codex 原生跨会话消息不推回结果**，跨会话的请求与回复必须走 agent-relay 邮箱。（H5）
4. **审批模型不同**：Codex 的自动审批不认其他会话转来的批准，必须用户在原会话亲口确认；任何会话都看不到别的会话里弹出的宿主确认。（H10、H12）
5. **插件机制不同**：Claude 插件提供斜杠命令、更新后新开会话即可；Codex 插件只能提供技能、更新后要完全退出 ChatGPT 应用；Codex 钩子必须在命令行版里信任，桌面版不会提示。（H6、H7、H8）

---

## 2. 测试环境与版本

| 组件 | 版本 | 取得方式 |
|---|---|---|
| macOS | 15.7.3（24G419） | `sw_vers` |
| Claude 桌面应用 | 2.42304.0 | `defaults read /Applications/Claude.app/Contents/Info.plist CFBundleShortVersionString` |
| Claude Code | 2.1.299 | `claude --version` |
| ChatGPT 应用（含 Codex 桌面版） | 26.1007.71326（build 20398） | `defaults read /Applications/ChatGPT.app/Contents/Info.plist CFBundleShortVersionString` / `CFBundleVersion` |
| ChatGPT 应用内置 codex | codex-cli 0.162.0-alpha.17.2 | `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex --version` |
| 命令行版 codex | codex-cli 0.162.1（nvm 安装） | `codex --version` |
| agent-relay | 运行时 0.6.10 起（2026-10-16 当天升级）；Codex 侧插件缓存 0.6.11；运行时提交 `8f12c880` | `~/.codex/plugins/cache/agent-relay-marketplace/agent-relay/`、`~/.agent-relay/runtime/manifest.json` |
| spec-guard | 0.63.0（两个宿主） | `~/.claude/plugins/installed_plugins.json`、`~/.codex/plugins/cache/spec-guard-marketplace/spec-guard/` |

注：观测期间 agent-relay 从 0.6.9 升到 0.6.11；与版本相关的现象在条目里注明。Claude 侧插件安装记录里的 agent-relay 版本号停留在 0.6.1（2026-10-09 写入），但两边共用同一个运行时（`~/.agent-relay/runtime`），实际行为以运行时为准。

---

## 3. 差异明细

### 3.1 会话生命周期与唤醒

#### H1 空闲会话：Claude 会被挂起，Codex 不会

| | Claude 桌面版 | Codex 桌面版 |
|---|---|---|
| 行为 | 应用会在内存压力下暂停空闲会话；应用自己的日志称 governor eviction，远多于空闲超时，最多保留 6 个 live sessions（ecosystem-lead 调查，2026-11-25） | 空闲会话保留，agent-relay 可直接让它开始新一轮 |
| 证据 | **实测**：agent-relay 唤醒记录为 `Claude session is not running (the Claude app may have stopped it while idle); the message waits and is delivered once that session is opened` | **实测**：唤醒记录为 `Codex confirmed a new turn` |
| 影响 | 收件枢纽、负责人这类 Claude 会话会周期性「消失」，期间待答表看起来是空的 | 只要应用没重启，叫醒可靠 |

#### H2 应用重启后：Codex 会话不自动加载

- **现象**：ChatGPT 应用重启后，之前的 Codex 会话在用户点开前都不会加载；发给它们的消息投递状态停在排队，唤醒按「离线」重试，直到用户点开。
- **证据（实测）**：2026-10-16 两次重启（14:14:54、15:56:42）。第一次：发给两个会话的唤醒分别重试 29 次和 23 次以上，记录为 `Codex local connection unavailable`；第二次：三个会话各重试 7 次，agent-relay 0.6.11 的记录为 `The ChatGPT app did not answer for this Codex task, usually because it was not opened since …`。用户点开后，三个会话在 1 分钟内全部开始处理，消息无丢失。同期两个测试用 Codex 会话收发正常，排除 agent-relay 整体故障。
- **Claude 对照**：Codex 重启不影响 Claude 会话。
- **对策**：重启 ChatGPT 应用后，逐个点开参与协作的 Codex 会话；唤醒只重试约 1 小时，超时后点开还需让会话主动读一次收件箱。

#### H3 联调身份丢失：只在 Codex 侧观察到

- **现象**：会话被点开后读收件箱，返回 `readRecorded: false`，`readNote` 为 `"<名字>" is not an identity of this session`；会话自己用原名重新登记后恢复。期间 agent-relay 仍把这个**正在运行**的会话判为离线、继续重试唤醒。
- **证据（实测）**：2026-10-16 共 4 次：长时间空闲的两个会话被点开时各 1 次（13:06）；应用重启后两个会话各 1 次（14:51），其中一个会话已正常回答用户，但发给它的消息仍是排队、未读。
- **Claude 对照**：观测期内未见 Claude 会话出现此提示（**未验证**是否不会发生）。
- **状态**：agent-relay 0.7.1 起有引导式恢复：读收件箱时提示会话用原名重新登记，登记后可再读一次；完全自动恢复不可行（会话得自己重新登记，旁人替它登记会被身份校验拒绝）。

#### H25 Codex 每一轮按需重启 MCP 服务器：两轮之间结束 bridge 会自动重连

- **现象**：Codex 每一轮开始时按需启动 MCP 服务器。在两轮之间结束 agent-relay 的 bridge 进程，下一轮会起新的 bridge，不留断掉的连接。
- **证据（实测）**：2026-10-18 agent-relay 0.8.2 真实宿主验收（结果经 agent-relay 邮箱报给负责人）：测试任务被点开后 3 秒内，codex app-server 下起了两个 bridge 进程；用 SIGTERM 结束它们后再发一条带唤醒的消息，ChatGPT 回 `Codex confirmed a new turn`，又起了两个新的 bridge 进程，任务 16 秒后读到并确认了这条消息。
- **对照**：agent-relay 0.8.0 升级时用 pkill 结束所有 bridge，正开着的 Codex 任务一直报 `Transport closed`，直到 ⌘Q 重启 ChatGPT 才恢复。两者不矛盾。
- **推测（未验证，待复核）**：只有 bridge 在某一轮进行中断掉，或 Codex 启动 bridge 时运行时目录正被替换，那一轮才会留下坏连接。
- **影响**：agent-relay 0.8.2 的「送达存疑」提醒针对「已送达、但这一轮读不到信箱」，两轮之间结束 bridge 不会触发它。H2 的对策（重启后逐个点开 Codex 会话）不变；升级 agent-relay 后，只有正在运行的那一轮报 `Transport closed` 才需要重启 ChatGPT（待复核）。

#### H4 谁能叫醒已停止的 Claude 会话

- **结论**：agent-relay 叫不醒已停止的 Claude 会话；Claude 桌面版自带的会话消息工具可以叫醒，但它只能在 Claude 会话内部调用，外部进程（包括 agent-relay）调不到。
- **证据（实测）**：2026-10-16 13:36，由 Claude 桌面版定时任务启动的一次性会话调用该工具，向一个空闲的 Claude 会话发消息，状态 `delivered`，目标会话随即开始处理。
- **影响**：decision-inbox 的巡视必须运行在 Claude 侧（定时任务或收件枢纽），由它负责叫醒 Claude 会话；这是「唤醒归 agent-relay」原则下唯一的例外。
- **补充实测（2026-11-25/26）**：带 `-open claude://claude.ai/epitaxy/local_<uuid>` 的 terminal-notifier 通知被点击后打开对应会话，原本停止的会话进程在点击时启动；该 link 来自桌面应用的 `get_session("self")`。

### 3.2 会话之间的消息

#### H5 原生跨会话消息

| | Claude 桌面版 | Codex 桌面版 |
|---|---|---|
| 原生工具 | 桌面版会话消息工具：消息以一轮用户输入送达目标会话，能叫醒已停止的会话 | `send_message_to_thread`：能把请求送到对方，但**对方的结果不会推回请求方** |
| 证据 | **实测**（见 H4） | **实测**：2026-10-16 统计，总协调与 4 条开发线之间约 193 次原生请求，邮箱里对应回复为 0；请求方要靠外部提醒才去对方会话取结果 |
| 结论 | 可用于兜底叫醒 | 跨会话请求与回复一律走 agent-relay 邮箱（agent-relay 0.6.9 起，Codex 之间派活默认走邮箱并按 `replyTo` 推回） |

#### H27 Claude 只对扣留过的 peer 消息发投递回执；回执每条新开连接（实测）

- **现象**：bridge 经 Claude Code 跨会话消息（`peer_message_status`）投递提醒时，被 permission-mode parity 扣留的消息会先回 `held`，放行（交给模型）时再回 `delivered`，两者相隔约 0.8～0.9 秒（会话刚启动时）。没被扣留、直接进队列的消息，Claude 不发任何回执，交给模型之后也不发。每条回执都新开一个到 `from` 地址的 unix socket 连接，写一行后关闭（macOS 上 150ms），`held` 和 `delivered` 不共用连接。
- **证据（实测）**：agent-relay 0.9.4 真实宿主验收（2026-10-27）共 6 轮。直接进队列的 3 轮（会话刚被拉起、正在跑上一轮、忙时并入当前轮）都没有回执，忙时那轮 60 秒里一次连接都没有。被扣留的 3 轮在 0.80／0.86／0.91 秒后收到 `delivered`。回执的连接方式读自 Claude Code 2.1.328 的二进制：回执发送函数每次 `connect` → `write` → 150ms 后 `end`。
- **对 agent-relay 的影响**：没被扣留的消息，bridge 等 1.8 秒没收到回执就记为 `unknown`，一直停在 `unknown`，直到对方读件才变成 `read`／`accepted`。`unknown` 不算失败，不告警、不重发。迟到的 `delivered` 走新连接，所以 bridge 回调服务端每个连接 2 秒的空闲超时不会丢掉它（D270，有回归测试）。Claude 以后要是改成复用连接，就有丢回执的风险，由 D268（已读或已确认的 `held` 不告警）兜住告警。来源 PR #177。

### 3.3 插件机制

#### H6 安装与更新后的生效方式（文档）

| | Claude Code | Codex |
|---|---|---|
| 更新 | `claude plugin marketplace update <市场>`，`claude plugin update --scope user <插件>@<市场>` | 改 `~/.codex/config.toml` 里该市场的 `ref`，`codex plugin marketplace upgrade`，`codex plugin add <插件>@<市场>` |
| 生效 | **新开会话**即用新版本；已开着的会话仍是旧版本 | **⌘Q 完全退出 ChatGPT 应用再打开**（随之触发 H2） |

来源：agent-relay 0.6.10 升级说明。

#### H7 插件能提供的入口（文档）

| | Claude Code | Codex |
|---|---|---|
| 命令 | 插件可注册**斜杠命令**（如 `/spec-guard:map`） | 插件**不能注册斜杠命令**，只能提供技能，用自然语言或 `$技能名` 触发 |
| 插件根目录变量 | `CLAUDE_PLUGIN_ROOT`（命令里由宿主代入） | `PLUGIN_ROOT`；找不到时需查询 `codex plugin list` |
| 项目规则文件 | `CLAUDE.md` | `AGENTS.md` |
| 外部定位已安装插件 | `~/.claude/plugins/installed_plugins.json` 的 `installPath` | `~/.codex/plugins/cache/<市场>/<插件>/<版本>/` |

来源：spec-guard `docs/design.md`「两个宿主的差异」。

#### H18 Codex 会话目录决定加载哪份 AGENTS.md（文档 + 实测）

- **规则**：从会话工作目录往上找到最近的含 `.git` 的目录作为项目根，加载根到工作目录这一段上每一层的 AGENTS.md；同一层有 AGENTS.override.md 时用它取代 AGENTS.md；总量上限 32KiB；不受信任的项目不加载（openai/codex `codex-rs/core/src/agents_md.rs`）。
- **证据（实测）**：2026-10-17 开发线会话开在项目目录之外时，约定块没被加载，表现为不认邮箱派来的活；在项目目录里新开任务后正常。
- **对策**：接入时 `onboard join` 用 `--session-cwd` 核对；`decision-inbox doctor` 逐个报「Codex 加载约定块」。

### 3.4 钩子

#### H8 钩子信任

| | Claude Code | Codex |
|---|---|---|
| 信任方式 | 首次使用时在 `/hooks` 中信任（**文档**） | **桌面版从不弹出信任提示**；必须在项目目录运行命令行版 `codex`，在「Hooks need review」中信任，写入 `~/.codex/config.toml` 的 `[hooks.state."<路径>/.codex/hooks.json:stop:0:0"] trusted_hash`（**实测**） |
| 修改钩子后 | — | 命令一变 `trusted_hash` 就失效，**必须重新信任**（**实测**） |
| 设计约束 | — | 钩子命令要尽量稳定；信任只能由用户亲自在终端操作 |

#### H9 停止钩子（Stop hook）

- **Codex（实测）**：命令行版 0.162.1 与桌面版内置 0.162.0-alpha.17.2 都会触发 `Stop`。返回 `{"decision":"block","reason":"…"}` 时，`reason` 喂回模型并**在同一轮继续**；再次触发时输入带 `stop_hook_active: true`，此时应放行以免死循环。输入还包含 `last_assistant_message`、`cwd`、`turn_id`。
- **Claude 桌面版**：**未验证**（本次未在 Claude 桌面版工作会话上测试停止钩子的拦截效果）。

### 3.5 权限与审批

#### H10 审批模型

| | Claude 桌面版 | Codex 桌面版 |
|---|---|---|
| 机制 | 按会话的权限模式（默认 / 自动 / 跳过）弹出确认 | 带自动审批；对写规则文件、改审计策略等动作做判断 |
| 转交的批准 | 不适用 | **不认**：用户在收件枢纽批过、由其他会话转来的批准，自动审批仍拒绝，要求用户在**该会话里直接**写出批准原话（**实测**，2026-10-16 两次：写长期规则文件、更新审计指纹） |
| 定时任务 | 创建时若没保存权限模式，运行用默认模式，会停在确认上；运行中批准的工具会记到任务上（**实测**）；见 H20 | 未验证 |
| 邮箱转来的任务 | 不适用 | 自动审批（守卫）把会话加载的 AGENTS.md 和用户在该会话里说过的「按收到的任务做」当作可信授权：两者都在时，中、低风险操作放行（**实测**，2026-10-17 一个检查点授权需求的开发中）；新开任务里用户只让它登记身份、没说那句话时，开发线也按约定块执行负责人经邮箱派来的活，只发邮箱消息、没有触发守卫（**实测**，2026-10-17 另一个需求的开发中） |

#### H11 沙箱（文档）

Codex 默认的 workspace-write 沙箱不允许写 `.git`，会话每次提交都要申请提权、由用户审批。Claude Code 无此限制。

#### H12 别的会话看不到宿主弹窗（两边相同）

- 任何会话都看不到别的会话里弹出的宿主确认。
- **证据（实测）**：2026-10-16 定时任务运行会话自述「全程没有弹出要人确认的提示」，实际调用 agent-relay 工具时弹了确认、由用户手动点了允许，停顿约 3 分钟。
- **证据（会话记录）**：2026-10-18 一次停摆排查中，别的会话代开的 Claude 会话里两次 `git push` 都弹了确认、被点了允许（`permissionDecision.source` 为 `user_temporary`，权限模式 `default`），事后被记成「没弹」。判断某个会话弹没弹确认，看 `~/.claude/projects/<目录>/<会话>.jsonl` 里那次工具结果的 `permissionDecision.source`：`config` 是规则放行或拒绝，`user_temporary`／`user_permanent` 是有人点了。（2026-10-19 查证，经用户决定写入）
- **设计约束**：巡视与收件枢纽不能依赖会话对权限情况的自述；「要用户去原会话确认」必须作为显式事项上报。

### 3.6 可观测性与运行环境

#### H13 会话记录

| | Claude 桌面版 | Codex 桌面版 |
|---|---|---|
| 位置 | `~/.claude/projects/<项目>/` 下的 JSONL | `~/.codex/sessions/<年>/<月>/<日>/rollout-*.jsonl` |
| 读取 | 跨会话读取要通过桌面版会话工具 | 文件里有 `task_started`、`task_complete` 等事件，**直接读文件即可判断哪个会话停在哪一轮**（**实测**） |
| 上下文窗口 | 记录里不写窗口大小（**文档**） | 记录里有窗口大小（**文档**） |

#### H14 Codex 有两份可执行文件，版本不同（实测）

ChatGPT 应用内置一份 codex（0.162.0-alpha.17.2），命令行另装一份（0.162.1）。桌面版行为以内置那份为准；钩子信任却要用命令行版完成（H8）。两份版本可能不同步，排查问题时要分别核对。

#### H19 Claude 自动模式会拦部分命令（实测）

- **现象**：权限模式为自动时，带 `--relayed-from` 的 `decision-inbox inbox reply` 被拦了两次（2026-10-17），收件枢纽只能改为请用户亲手回一遍；会话停止类工具（`stop_session`）也被拦。
- **影响**：收件枢纽遇到被拦的命令，要先讲清是宿主拦的、为什么，再给选项；不要换个写法绕过。

#### H20 Claude 定时任务不继承创建者会话的权限（实测）

- **现象**：巡视定时任务每遇到一个没批过的工具就停在权限确认上，停住期间后面每一轮都不跑；2026-10-17 一天 3 次，最长 300 多分钟没跑。创建它的收件枢纽会话批过的工具，任务里照样要再批。
- **对策**：`decision-inbox onboard allow <协作组> --project <收件枢纽目录>` 预览要放行的命令和工具，用户确认后加 `--confirm` 写进收件枢纽目录的 `.claude/settings.local.json`；`decision-inbox doctor` 报「巡视 N 分钟没跑」。

#### H21 目录型插件市场：Claude 直接读源目录（实测）

- **现象**：用 `claude plugin marketplace add <本地目录>` 加的市场，Claude 按源目录加载插件（`claude plugin list` 显示 Read from 源目录、源目录里的版本），`~/.claude/plugins/installed_plugins.json` 里的版本和安装路径却停在当初的缓存（2026-10-17：agent-relay 记录为 0.6.1，实际加载 0.8.2）。
- **影响**：按安装记录找依赖插件会拿到旧版本；decision-inbox 先看 `known_marketplaces.json`，目录型市场取源目录里的插件。

#### H22 Claude 定时任务：第一次手动运行前不按时触发（实测）

- **现象**：2026-10-18 一个测试协作组的巡视任务 02:02 建好（每 5 分钟），02:07、02:12、02:17 都没运行，运行记录为 0；02:20 手动「立即运行」一次后，02:22 起才按时触发。
- **另见**：一轮巡视要 2～3 分钟，上一轮没结束时下一轮会被跳过；上一轮留下的输入文件已存在时，宿主的写文件工具不让覆盖没读过的文件，巡视会话要先读再写，一轮拖到 3 分钟以上。
- **影响**：接入步骤必须写明「建好后手动立即运行一次」；0.0.12 起巡视与收件枢纽的命令读完输入文件即删除。

#### H24 Claude 定时任务周期触发不规律（实测）

- **现象**：2026-10-18 同一测试协作组的巡视任务（`*/5 * * * *`）手动运行过一次后，只在 02:21、02:34 自己触发；02:37～03:05 一次也没触发，列表里的 `nextRunAt` 不断后推、运行记录不增加。手动「立即运行」随时有效。
- **影响**：巡视间隔不能按 5 分钟估算；「巡视 N 分钟没跑」会在没有任何故障时出现。实地验收 P3 的「巡视停摆」指标要把这种情况单独计数（patrol-cadence 起 `query stats` 统计轮数与最长间隔）。
- **观察 1 小时（2026-10-18 03:13～04:12，每分钟记录前台应用与锁屏）**：这一小时里巡视**一次也没有自动触发**；其中 34 分钟 Claude 桌面版在前台且未锁屏，25 分钟锁屏。到观察结束，任务自建好以来只自动跑过 2 次（02:21、02:34，都在一次手动运行后的 15 分钟内），手动运行 2 次。
- **结论**：不是锁屏或窗口被遮挡造成的；在这台机器上，这个周期任务的自动触发基本不起作用，原因**未查明**（宿主内部机制，本插件看不到）。应向宿主反馈；巡视不能只靠定时任务，需要后备触发。0.0.14 起采用对策 B（hub-patrol）：收件枢纽被叫醒或用户说话时，巡视超过 10 分钟没跑就顺带跑一轮；`query stats` 分别统计定时任务与收件枢纽各跑了几轮。

#### H23 agent-relay 身份名绑在旧会话上（实测）

- **现象**：2026-10-18 收件枢纽换会话后用原身份名 `bridge_register`，因名字还绑在已归档的旧会话上被拒；用户同意后带 `takeover` 才登记成功。
- **影响**：实地验收 P2 沿用原收件枢纽身份名时一定会遇到，要先征得用户同意接管。

#### H26 Claude 的 CLAUDE.local.md：和 CLAUDE.md 一起加载，有它时不再读 AGENTS.md（文档）

- **规则**：Claude Code 加载工作目录及上层每一层的 `CLAUDE.md` 和 `CLAUDE.local.md`；同一层里 `CLAUDE.local.md` 排在 `CLAUDE.md` 后面。`CLAUDE.local.md` 要自己加进 git 的忽略规则。被忽略的 `CLAUDE.local.md` 只存在于创建它的那个 worktree，别的 worktree 拿不到。工作目录或上层只要有 `CLAUDE.md` 或 `CLAUDE.local.md`，默认就不再读 `AGENTS.md`；要两种都读，得在设置里改「Project instructions」（code.claude.com/docs/en/memory，2026-10-18 查阅）。
- **Codex 对照**：Codex 只读 `AGENTS.md`（H18），不读 `CLAUDE.local.md`。
- **影响**：module-crew 的协调会话开在集成 checkout 里，约定块写进 `CLAUDE.local.md`（`onboard join --local-rules`），就不会被提交，也不会被模块 worktree 继承。桌面版 Code 标签页是否同样加载这个文件，**待复核**（联合演练 P2）。

#### H15 定时任务

- **Claude 桌面版（实测）**：一次性定时任务按时启动（无延迟），能运行 Bash、只读查询 SQLite、调用 agent-relay MCP 工具、调用会话消息工具。周期任务每次触发有几分钟的负载均衡延迟（**文档**：工具说明）。周期间隔的实际值、应用关闭时的补跑行为**未验证**。
- **Codex 桌面版**：**未验证**。

### 3.7 使用习惯

#### H16 收件枢纽放在哪个宿主

- **实测**：收件枢纽放在 Codex 侧边栏时，它只是众多会话之一，13 项待决定事项里只有 5 项经它答复；移到用户平时审查所在的 Claude 桌面版后，绝大多数事项都经它答复。
- **结论**：收件枢纽固定放在 Claude 桌面版。

---

#### H17 自动压缩后容易抓「最近一条人工输入」当任务（Codex，待复核）

- **现象**：长会话在一轮中途自动压缩后，模型倾向于把**压缩前最近一条用户亲手输入**当成当前任务，而不是压缩前正在做的、由邮箱转来的新任务；核对发现旧任务已完成后直接结束这一轮。
- **证据（实测，3 次）**：2026-10-15 两次；2026-10-16 18:11:19 一次——会话正按邮箱转来的用户答复为新模块写 Spec，压缩后转去复核 8 小时前用户亲手发的一条旧批准，报告「已执行，不重复覆盖」后结束，新模块 Spec 一字未写。压缩时 spec-guard 注入了正确的当前模块与下一步，仍未接上。
- **推测机制（未验证）**：经 agent-relay 邮箱送达的任务不以「用户消息」形式进入会话记录，压缩摘要里保留的最近人工输入因此权重更高。
- **Claude 对照**：未观察到（**未验证**）。
- **设计约束**：停止钩子要能拦下「有人在等本会话交付却收工」；压缩后提示应明确「核对后接着做建议的下一步」——spec-guard 0.64.2 已落地：压缩后注入末尾加了「once checked, carry on with the suggested next step above, if there is one, instead of ending the turn」，两宿主共用；真实中途压缩后的效果待在观测样本中复核。

---

## 4. 历史：decision-inbox 当时的设计约束（仅存档）

> 本节是原文 §4，记录 decision-inbox 在 2026-10 依据上面各条目定下的设计约束，迁入时原样保留作历史，不是 agent-relay 的约束，也不再更新。agent-relay 自己的设计约束写在 `spec/` 下各模块 Spec 里，引用本文条目时写 `docs/host-differences.md` 加条目号。

| 约束 | 来源条目 |
|---|---|
| 收件枢纽与巡视运行在 Claude 桌面版 | H4、H15、H16 |
| 叫醒 Claude 会话由本插件做（会话消息工具），叫醒 Codex 会话交给 agent-relay | H1、H4 |
| 巡视要把「Codex 会话未加载」「身份未对上」识别为独立原因，提示用户点开或让会话重读收件箱 | H2、H3 |
| 接入说明写明：重启 ChatGPT 应用后逐个点开协作中的 Codex 会话 | H2 |
| 跨会话请求与回复一律走 agent-relay 邮箱 | H5 |
| Codex 侧查询做成技能，Claude 侧做斜杠命令 | H7 |
| 停止钩子命令保持稳定；Codex 侧接入后提示用户在命令行版信任 | H8 |
| 「要用户去原会话亲自确认」作为显式事项上报，算进「等你决定」 | H10、H12 |
| 不依赖会话对权限情况的自述 | H12 |
| 停止钩子拦下「有人在等本会话交付却收工」，覆盖压缩后跑偏 | H17 |
| 开发线的 Codex 会话开在接入时的项目目录里；doctor 核对能否加载约定块 | H18 |
| 宿主拦下的命令不绕过，收件枢纽先讲清原因再给选项 | H19 |
| 收件枢纽目录一次性放行巡视与收件枢纽要用的命令和工具；doctor 报巡视停摆 | H20 |
| 找依赖插件时识别目录型插件市场 | H21 |
| 巡视任务建好后先手动运行一次；命令读完输入文件即删除，免得下一轮被旧文件卡住 | H22 |
| 收件枢纽换会话沿用原身份名，接管前先问用户 | H23 |
| 协调会话的约定块可以写进 `CLAUDE.local.md` 并排除出 git；只有 AGENTS.md 的项目接入时要提示 | H26 |

## 5. 未验证 / 待复核

1. Claude 桌面版工作会话上的停止钩子拦截效果（H9）。
2. Claude 会话是否也会出现联调身份丢失（H3）。
3. Claude 桌面版周期定时任务的实际间隔、应用关闭时的补跑（H15）。
4. Codex 桌面版是否有可用于巡视的定时任务（H15）。
5. Codex 压缩后抓最近人工输入的机制（H17），以及 Claude 侧是否同样发生
6. agent-relay 0.7.1 起的引导式恢复在 H2、H3 场景下的实际效果。
7. bridge 在一轮进行中断掉、或启动时运行时目录正被替换，是否就是留下 `Transport closed` 坏连接的条件（H25）。
8. Claude 桌面版 Code 标签页是否像 Claude Code 一样加载 `CLAUDE.local.md`（H26）。

## 6. 复核方法

```bash
sw_vers
claude --version
codex --version
/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex --version
defaults read /Applications/Claude.app/Contents/Info.plist CFBundleShortVersionString
defaults read /Applications/ChatGPT.app/Contents/Info.plist CFBundleShortVersionString
```

- H2：重启 ChatGPT 应用后，给一个未点开的 Codex 会话发 agent-relay 消息，查 `~/.agent-relay/runtime/mailbox/bridge.sqlite` 的 `wake_jobs`（`state`、`attempts`、`pending_reason`、`detail`）；点开会话后再查一次。
- H3：在长时间空闲或重启后点开的 Codex 会话里读收件箱，看返回的 `readRecorded` 与 `readNote`。
- H5：用 `send_message_to_thread` 派一个任务，对方完成后检查请求方是否收到结果。
- H9：在 `.codex/hooks.json` 配一个返回 `decision:block` 的 Stop 钩子，经命令行版信任后在桌面版触发。

## 修订记录

| 日期 | 变更 |
|---|---|
| 2026-11-26 | H1 记录 Claude 桌面应用在内存压力下的 governor eviction；H4 补 2026-11-25/26 实测：terminal-notifier 带会话 link 的通知点击后打开该会话并启动停止的进程，link 来自 `get_session("self")` |
| 2026-10-16 | 初版：16 条差异，基于 2026-10-13 至 10-16 的实测与两个插件仓库的文档 |
| 2026-10-17 | 新增 H17（Codex 自动压缩后抓最近人工输入当任务，待复核） |
| 2026-10-17 | H3 改为 agent-relay 0.7.1 起有引导式恢复；H10 补守卫对邮箱转来任务的判断；新增 H18（Codex 会话目录决定加载哪份 AGENTS.md）、H19（Claude 自动模式拦命令）、H20（定时任务不继承权限）、H21（目录型插件市场读源目录） |
| 2026-10-18 | 新增 H25（Codex 每一轮按需重启 MCP 服务器，两轮之间结束 bridge 会自动重连；一轮中途断掉才需重启 ChatGPT，待复核），来源 agent-relay 负责人 |
| 2026-10-18 | 新增 H26（CLAUDE.local.md 的加载规则，以及有它时不再读 AGENTS.md），来源 Claude Code 官方文档 |
| 2026-11-22 | 从 decision-inbox 迁入 agent-relay（`docs/host-differences.md`），此后由 agent-relay 维护；去掉协作组、测试组、需求模块代号和邮箱消息、决定编号；§4 标为历史存档；新增 H27（Claude 只对扣留过的 peer 消息发投递回执，回执每条新开连接），来源 agent-relay 0.9.4 验收、PR #177 |

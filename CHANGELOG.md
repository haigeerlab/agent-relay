# Changelog

## [Unreleased]

- **任何权限模式都能绑定唤醒，被唤醒的回合按会话自己的设置运行**（模块 `wake-any-mode`，D140–D145，第二轮联调 A1）：
  Claude 的 auto 模式、Codex 的“帮我批准”下都可以加入并绑定唤醒。bridge 不再把被唤醒的 Codex 回合改成“用户审批 +
  只读沙箱”（撤销 codex-gated-wake D65，用户 2026-10-09 确认），连带删除 ChatGPT 26.930 版本门槛、唤醒后读记录核对和
  `codex-gate.off`；旧版本留下的 `codex-gate.off` 不再使用，可以自己删掉。来信仍是不可信内容、不构成授权，会话需要更高
  权限时照常自己向你申请。**风险**：自动审查模式下，被唤醒那一轮的操作不一定经过你本人。bridge 改动，升级运行时后生效。
- **CI 按改动决定跑不跑**（模块 `ci-on-demand`，D135–D139）：只改 `CLAUDE.md`、`AGENTS.md`、`spec/`、`tasks/`、`.agent/` 的 PR
  和推送，四个必需检查直接通过、不跑测试；其余改动照常跑 Python 3.9/3.14 × Node 22/24 全矩阵。判断在每个任务内部做
  （`scripts/ci_scope.py`），不用路径过滤，所以必需检查不会卡在“等待中”；拿不准时一律全量。新增守护测试，测试跑到的代码
  一旦引用这些路径就变红。每周一 03:00 UTC 定时全量跑一次。只改 CI，不影响插件与运行时。
- **升级说明写清楚怎么停 bridge**（模块 `upgrade-restart-note`，D132–D134，0.5.2 E1 验收发现 F2）：README“升级运行时”与
  collaboration-ops 技能写明两种方式——退出应用后重开；或用 `pkill -TERM -f "[a]gent-relay/runtime/dist/server.js"` 只结束
  bridge（方括号让它不会结束执行它的 shell），这时 ChatGPT 应用要 ⌘Q 完全退出再打开，否则已打开的 Codex 线程会一直报
  “Transport closed”。技能要求 agent 只有在用户明确同意这一步后才执行 `pkill`。只改文档。
## [0.5.2] - 2026-10-09

接口仍为 **1.4**，信箱 schema 仍为 5，委派库结构仍为 2。这一版收尾 0.4.0 架构审核剩下的发现：状态迁移、委派的并发与
首次建库、确认与唤醒任务的事务。只有 `ack-wake-atomic` 改了 bridge，要升级运行时才生效；其余都在插件的 hooks 里，
更新插件即生效。

- **确认与关闭唤醒任务一起完成**（模块 `ack-wake-atomic`，D130，0.4.0 架构审核）：`bridge_ack`（以及带确认的
  `bridge_wait`）以前先在自动提交里记下确认，再另开事务关闭对应的唤醒任务，多条消息也是逐条提交；中途出错或被杀会留下
  “消息已确认、唤醒任务还待发”，之后可能再提醒一次收件人。现在一次确认的全部消息与它们的唤醒任务在同一个事务里完成，
  要么都成功，要么都不变；返回值、重复确认与只能确认发给自己的消息不变。bridge 改动，升级运行时后生效。
- **多个进程同时首次打开委派库不再报错**（模块 `delegation-store-init`，D127、D128，`delegation-claim` 实测时发现）：以前几个
  进程同时第一次创建 `~/.agent-relay/delegation/` 时，可能报 “state directory could not be created” 或 “delegation database
  schema is incomplete”（主分支代码复现 30 次失败 3 次）；建库进程若在建表前死掉，留下的空库文件以后每次都被拒绝。现在目录被
  别的进程抢先建好时照常检查后使用，每个打开的进程都在写事务里给空库（版本 0 且没有任何表）建表，其他进程等它完成；已有
  内容但结构不对的库照旧拒绝，目录、文件与附属文件的检查不变。委派库结构仍为 2。合并后的审查修正：版本 0 但含有视图、索引或
  触发器的外来库也不算空库、不会被补表；已建好的库打开时不再拿写锁（以前别的进程持有写锁时，打开会等 5 秒后报
  “delegation database is corrupt”）。
- **委派一次只有一个调用能碰到宿主**（模块 `delegation-claim`，D122–D125，0.4.0 架构审核）：以前用同一个启动键并发创建时，
  两个调用都会启动宿主会话（Codex 发两次 `thread/start`），并发追问会发出两轮，后到的那个在宿主已经动了之后才失败。现在
  控制器在调用 Claude/Codex 适配器之前先认领这个委派（`~/.agent-relay/delegation/claims/<id>.lock` 上的 flock，进程死掉
  自动释放）：另一个调用正在处理时返回 `prerequisite: operation-in-progress`，什么都不启动；上一次在半路被杀时，下一次调用
  把记录记为 `unknown` 并返回 `previous-operation-interrupted`，绝不再启动一次。委派库结构不变（仍是 2），插件更新即生效，
  不用升级运行时。session-delegation 技能与接口文档写明这两个结果（D126）。
- **状态迁移一次只跑一个，失败了就换回去**（模块 `state-migration-safety`，D116–D119，0.4.0 架构审核 B6、C11）：
  `state_migration.py migrate --confirm` 以前没有互斥，也不检查 agent-relay 自己的信箱服务，却会删掉目标信箱文件再复制进去；
  中途出错或被杀会留下“目标信箱已有数据、永远不能重试”的半截状态。现在同一时间只允许一次迁移（对 `~/.agent-relay` 目录加
  锁，不留锁文件），agent-relay 的信箱服务在运行时也拒绝；信箱、data 和委派目录先在旁边准备好、核对行数，再整体换上，每一步
  前写 `state-migration.json`；任何一步出错或行数不符都换回原样（以前行数不符时会把复制的数据留在原处），没换成的那份保留为
  `.state-migration-failed-<时间>`，被换下的目录在成功后也保留。同一秒内已有备份时改用 `-1` 后缀。
- **`state_migration.py recover --confirm`**（模块 `state-migration-safety`，D120）：迁移半路被杀时，`detect` 报 `interrupted`、
  `migrate` 拒绝执行，这条命令按记录回到迁移前的样子（只回退、不补完），之后可以再迁移。接口文档 §13、README 与
  collaboration-ops 技能写明这些；`interface.json` 仍为 1.4（D121）。
以上来自五个 PR：`state-migration-safety`（#41）、`delegation-claim`（#42）、`delegation-store-init`（#43、#44）、
`ack-wake-atomic`（#45）。

### 从 0.5.1 升级

1. 两个宿主都更新插件：
   - Claude Code（从 GitHub 装的）：先 `claude plugin marketplace update agent-relay-marketplace`，再
     `claude plugin update agent-relay@agent-relay-marketplace`。
   - Codex：把 `~/.codex/config.toml` 里 `[marketplaces.agent-relay-marketplace]` 的 `ref` 改成 `"v0.5.2"`（自己改，改前留一份
     副本），再 `codex plugin marketplace upgrade`，最后 `codex plugin add agent-relay@agent-relay-marketplace`。
   - 从本地克隆装的：把克隆更新到 v0.5.2 后，Claude 无需其他操作，Codex 再执行一次 `codex plugin add`。
2. **关闭所有使用信箱的会话**（所有 Claude Code 会话和 ChatGPT 应用），在 macOS 自带的“终端”里确认
   `pgrep -fl "agent-relay/runtime/dist/server.js"` 没有输出，再执行
   `python3 -B <插件目录>/hooks/native_collaboration_runtime.py upgrade --confirm`。半路被打断时按 `status` 的提示执行
   `recover --confirm`。宿主接入不用重做。
3. `doctor`：`runtime`、`probe`（10 个工具）、`host-entries` 为 ok。
4. 想退回 0.5.1：关掉所有会话后 `rollback --confirm`，并把两个宿主的插件也退回 v0.5.1（只回滚运行时也能用，但 doctor 的
   `runtime` 会一直 warn “bridge is older than this plugin's” 并提示再升级）。

从更早的版本升级：按对应版本的说明做完宿主那边的步骤，把 `ref` 换成 `"v0.5.2"` 更新插件，再做上面第 2–3 步。

### 已知问题

- 查看委派状态（`status`）不拿认领：它与一个正在进行的 `continue` 同时推进同一条记录时，其中一方可能得到
  “invalid-state-transition” 错误；状态转换都在事务里并检查合法性，不会因此重复碰到宿主，再查一次 `status` 即可。
- 0.5.1、0.5.0 列出的已知问题仍然存在，见下方各版本的“已知问题”。

## [0.5.1] - 2026-10-08

接口仍为 **1.4**，信箱 schema 仍为 5。两处修正都来自 0.5.0 的真机复验：bridge 的 CLI 和 MCP 服务在没有指定信箱时，不再退回
上游的默认库 `~/.local/share/claude-codex-bridge/bridge.sqlite`。agent-relay 自己的启动方式（宿主接入、`probe`、Codex 委派、
退役脚本）本来就指定信箱，行为不变。

- **MCP 服务也不再碰上游默认库**（模块 `server-db-guard`，D114）：没有设 `BRIDGE_DB_PATH` 就启动 `dist/server.js` 时，以前会
  打开（不存在就新建）`~/.local/share/claude-codex-bridge/bridge.sqlite`，变成一个只有它自己看得到的信箱，注册和发出的消息
  无人收到；现在在打开任何数据库之前就拒绝启动，以 2 退出，并在日志里说明服务由 `native_collaboration_adapters.py
  install-claude / install-codex` 接入的宿主启动。宿主接入、`probe` 和 Codex 委派本来就传这个变量，不受影响。万一宿主里
  agent-relay 显示连接失败（例如手改过的条目没带这个变量），运行 `doctor`：`host-entries` 会判为 fail（“entry points at another
  runtime”），按提示重新执行 `install-claude` / `install-codex` 即可。
- **CLI 的 `retire` 不再碰上游默认库**（模块 `retire-cli-guard`，D111、D112，0.5.0 真机复验发现 F1）：直接运行
  `node ~/.agent-relay/runtime/dist/cli.js retire <名字>` 而没有设 `BRIDGE_DB_PATH` 时，以前会打开（不存在就新建）
  `~/.local/share/claude-codex-bridge/bridge.sqlite` 并在那里退役，现在在打开任何数据库之前就拒绝，以 2 退出，并提示改用
  `native_collaboration_retire.py --name <名字> --confirm-retire`。`BRIDGE_DB_PATH` 为空白也算没设；经 Python 脚本退役不变，
  帮助里写明这一点。

以上改动都在 bridge 里，要升级运行时才生效（见下）。两个模块：`retire-cli-guard`（#37）、`server-db-guard`（#38）。

### 从 0.5.0 升级

1. 两个宿主都更新插件：
   - Claude Code（从 GitHub 装的）：先 `claude plugin marketplace update agent-relay-marketplace`，再
     `claude plugin update agent-relay@agent-relay-marketplace`。
   - Codex：把 `~/.codex/config.toml` 里 `[marketplaces.agent-relay-marketplace]` 的 `ref` 改成 `"v0.5.1"`（自己改，改前留一份
     副本），再 `codex plugin marketplace upgrade`，最后 `codex plugin add agent-relay@agent-relay-marketplace`。
   - 从本地克隆装的：把克隆更新到 v0.5.1 后，Claude 无需其他操作，Codex 再执行一次 `codex plugin add`。
2. **关闭所有使用信箱的会话**（所有 Claude Code 会话和 ChatGPT 应用），在 macOS 自带的“终端”里确认
   `pgrep -fl "agent-relay/runtime/dist/server.js"` 没有输出，再执行
   `python3 -B <插件目录>/hooks/native_collaboration_runtime.py upgrade --confirm`。半路被打断时按 `status` 的提示执行
   `recover --confirm`。宿主接入不用重做。
3. `doctor`：`runtime`、`probe`（10 个工具）、`host-entries` 为 ok。宿主里 agent-relay 若显示连接失败，见上面 `server-db-guard`
   一条。
4. 想退回 0.5.0：关掉所有会话后 `rollback --confirm`，并把两个宿主的插件也退回 v0.5.0。只回滚运行时也能用（两版工具集合
   相同，探针照常列出 10 个工具），但 doctor 的 `runtime` 会一直 warn “bridge is older than this plugin's” 并提示再
   `upgrade --confirm`，`status` 的 `bridge.current` 为 false。

从更早的版本升级：按 0.5.0 的说明做完宿主那边的步骤，把 `ref` 换成 `"v0.5.1"` 更新插件，再做上面第 2–3 步。

### 已知问题

- 0.5.0 列出的已知问题仍然存在（状态迁移工具不在恢复范围内、编排表保留、读取不鉴权等），见下方 0.5.0 的“已知问题”；其中
  退回 0.4.0 时不连插件一起退回，探针会判 fail；退回 0.5.0 时探针能过，但 doctor 的 `runtime` 会 warn（见上面第 4 步）。
- doctor 的 `host-entries` 对缺少 `BRIDGE_DB_PATH` 的条目报的是 “entry points at another runtime”，不会单独点明缺这个变量。

## [0.5.0] - 2026-10-08

接口升到 **1.4**（`interface.json`）：`readRecorded` / `readNote` 以及运行时的 `rollback`、`recover` 命令和 `interrupted` 状态
都是 1.x 内的兼容新增；Spec Guard 的探测范围 `>=1.0,<2.0` 不用改。这一版来自 0.4.0 的架构审核：删掉一直禁用的 Codex
编排器和上游 TS CLI 的控制面，修正“别人读一眼就算已读”，让运行时的升级、重装可以恢复，并新增回滚命令。信箱 schema 仍为 5。

- **升级中断后能恢复**（模块 `upgrade-recovery`，D104、D105、D109）：运行时的切换（升级、重装、回滚）在旁边写一份
  `runtime-swap.json` 记录进行到哪一步。半路停下时 `status` 报 `interrupted`，`install`、`upgrade`、`uninstall` 拒绝执行；新命令
  `recover --confirm` 一律回到切换前的运行时（不往前补完），信箱和数据搬回原处、核对行数，没换成的那份保留为
  `.runtime-<类型>-failed-<时间>` 供查看。
- **升级与重装当场回退**（模块 `upgrade-recovery`，D106、D107）：搬信箱、撤下旧运行时、换上新的、验证，任何一步出错（包括最后一次
  改名）都立刻回到原来的运行时，不再留下没有 `runtime/` 的状态；临时目录名带随机后缀，失败时只删本次自己建的（以前重装失败会按
  “同一秒”的名字删掉别人的目录）。
- **`rollback --confirm`**（模块 `upgrade-recovery`，D108）：一条命令回到最新的 `runtime.previous-*`，信箱和数据一起带过去；先备份信箱、
  记录切换日志、核对行数；当前版本保留为 `runtime.rolled-back-<时间>`，什么都不删。要求运行时就绪、没有 bridge 在跑。升级结果里的
  手工回滚步骤改为指向这条命令；旧版插件只认 schema ≤ 4 的提醒照旧附在结果里。
- **doctor 与文档**（模块 `upgrade-recovery`，D109、D110）：有切换日志时 doctor 的 runtime 检查判为 fail，下一步指向
  `recover --confirm`（以前会叫你重新 install）；日志读不了时也判 fail、不崩溃。README 升级段落、collaboration-ops 技能和接口文档
  §2.3 写明 `rollback`、`recover` 与 `interrupted`，作为 1.4 内的新增。
- **Spec Guard 看到的提示也指向 recover**（模块 `upgrade-recovery`，第二轮联调审查 #34 发现）：`relay_status.py`（`interface.json` 的
  `status` 命令）在切换中断时给出 recover 的指引，不再叫你去安装（安装会被拒绝）；切换记录读不了时也照常回答，提示交给人检查，
  不再报错退出。
- **只有本人读取才算已读**（模块 `inbox-read-receipt`，D99、D100）：`bridge_inbox` 和不确认的 `bridge_wait` 只有在调用方就是该
  身份时才记已读、刷新活跃时间，`bridge_outbox` 同理只在本人查看时刷新活跃时间。以前任何会话读一眼别人的收件箱，消息就变成
  `accepted`，还在等待的唤醒任务也被关掉，真正的收件人从此不会被提醒。读取仍不鉴权；结果新增 `readRecorded`（总是有）和
  `readNote`（为 false 时说明原因；bridge 重启后的 Codex 会话读自己的身份时会看到它，按提示重新注册即可）。
- **接口 1.4**（模块 `inbox-read-receipt`，D101）：`interface.json` 升到 1.4，`readRecorded` / `readNote` 是 1.x 内的兼容新增，接口文档
  §2.1 与“Message read”一行写明只有本人读取才算；Spec Guard 的探测范围 `>=1.0,<2.0` 不用改。
- **bridge 的 TS CLI 只留 `retire` 和 `help`**（模块 `legacy-cli-cleanup`，D95）：上游的 setup、doctor、status、demo、prune、backup、
  rollback、uninstall 都删了——安装、升级、体检和卸载只认 agent-relay 的 Python 运行时（这个 CLI 本来就不在 PATH 上，唯一的
  调用方是身份退役脚本）。命令写错时打印用法并以 2 退出；`retire` 的输出和退出码不变。
- **名字统一为 agent-relay**（模块 `legacy-cli-cleanup`，D96）：信箱服务在 MCP 握手里自报 `agent-relay`，日志前缀 `[agent-relay]`；
  bridge 的 npm 包改名 `agent-relay-bridge`，只留一个 bin。发给 Claude/Codex 应用接口的 `clientType` 和默认数据目录名
  （agent-relay 总是指定信箱路径，用不到它）保持原样。
- **doctor 去掉 `--claude-settings`**（模块 `legacy-cli-cleanup`，D97）：上个模块起 doctor 已不读 Claude 设置文件；卸载用的同名
  选项在 adapters 里，照旧保留。
- **bridge 文档跟上**（模块 `legacy-cli-cleanup`，D98）：bridge 的 README、INSTRUCTIONS、BACKGROUND-WAKE 的安装、维护、存储与日常
  维护改为 agent-relay 的 Python 命令和 `~/.agent-relay/runtime`；README 里残留的 Codex worker 斜杠命令一节（上个模块漏删）一并
  去掉；channel 启动参数改为 `server:agent-relay`。
- **删除 Codex 编排器**（模块 `orchestrator-removal`，D90、D91、D93）：bridge 不再注册 `ask_codex`、`review_with_codex`、
  `bridge_orchestrate_codex`、`bridge_continue_codex`、`bridge_orchestration_wait`、`bridge_orchestration_status` 和
  `bridge_retire`，MCP 服务只提供十个信箱工具。这七个工具在所有宿主上本来就是禁用的；委托 Codex 改由 delegate 插件负责。
  身份退役仍用 CLI 的 `retire`。`orchestrator.ts`、`simple-tools.ts`、`process-info.ts` 及其测试一并删除，tag `v0.4.0`
  保留最后一份。信箱里的编排表原样保留、不再读写；doctor 不再检查 Codex CLI，`status` 和 doctor 不再统计 Codex runs，
  `BRIDGE_WORKTREE_ROOT` 与 `smoke:orchestrator` 脚本一并去掉。
- **工具集合由运行时探针强制**（模块 `orchestrator-removal`，D91、D92）：`probe` 要求 MCP 服务提供的工具与十个信箱工具
  完全一致，多一个或少一个都判为 invalid 并写明是哪个。`install-claude` 不再往 Claude 设置里写拒绝规则（已没有可拒绝的
  工具），也不再改动设置文件；0.4.0 写下的七条规则升级后留着无害，`uninstall-claude` 照旧识别并移除，doctor 不再要求它们。
  Codex 那边“始终允许”留下的任何审批子表，卸载时照旧一并清掉。
- **文档**（模块 `orchestrator-removal`，D94）：bridge 的 README、INSTRUCTIONS、CHANGELOG，接口文档 §2.2，collaboration-ops 与
  session-delegation 技能，以及本 README 的卸载说明，都改为“编排工具已删除”；旧名字只留在删除说明和历史里。

以上 bridge 改动都要升级运行时才生效（见下）。四个模块：`orchestrator-removal`（#31）、`legacy-cli-cleanup`（#32）、
`inbox-read-receipt`（#33）、`upgrade-recovery`（#34）。

### 从 0.4.0 升级

1. 两个宿主都更新插件：
   - Claude Code（从 GitHub 装的）：先 `claude plugin marketplace update agent-relay-marketplace`，再
     `claude plugin update agent-relay@agent-relay-marketplace`。
   - Codex：把 `~/.codex/config.toml` 里 `[marketplaces.agent-relay-marketplace]` 的 `ref` 改成 `"v0.5.0"`（自己改，改前留一份
     副本），再 `codex plugin marketplace upgrade`，最后 `codex plugin add agent-relay@agent-relay-marketplace`。
   - 从本地克隆装的：把克隆更新到 v0.5.0 后，Claude 无需其他操作，Codex 再执行一次 `codex plugin add`。
2. **关闭所有使用信箱的会话**：所有 Claude Code 会话，以及 ChatGPT 应用（Codex 的 bridge 由它启动）。在 macOS 自带的
   “终端”里（不要在会话里）确认 `pgrep -fl "agent-relay/runtime/dist/server.js"` 没有输出，再执行
   `python3 -B <插件目录>/hooks/native_collaboration_runtime.py upgrade --confirm`。这次升级已经由 0.5.0 的代码执行：写切换记录、
   出错当场回退；万一半路被打断，`status` 会报 `interrupted`，按提示执行 `recover --confirm`。信箱先备份，schema 不变。
3. 宿主接入不用重做：信箱工具的预先批准不变；0.4.0 写进 Claude 设置的 7 条禁用规则留着无害（它们禁用的工具已经不存在），
   卸载时照旧移除。
4. `doctor`：`runtime` 和 `probe` 为 ok，`probe` 列出 10 个工具；不再有 Codex CLI 一项。preflight 显示
   `runtime bridge current`、各插件副本 `current`。
5. 升级后的行为：
   - 重开会话后各自重新注册一次名字。Codex 会话在 bridge 重启后读自己的收件箱，若结果里 `readRecorded` 为 false，按
     `readNote` 的提示用同一个名字再注册一次。
   - 读别人的收件箱不再把消息记为已读，收件人仍会被提醒。
   - 想退回 0.4.0：关掉所有会话后 `rollback --confirm`，并把两个宿主的插件也退回 v0.4.0（见“已知问题”）。

从更早的版本升级：先按各版本的说明做完宿主那边的步骤（从 0.2.x 来的要做 0.3.0 说明里的第 2 步），把 `ref` 换成
`"v0.5.0"` 更新插件，再做上面第 2–5 步（一次 `upgrade --confirm` 即可）。

### 已知问题

- `rollback --confirm` 只换运行时，不换插件：0.5.0 插件的探针要求恰好 10 个工具，回到 0.4.0 的运行时后 doctor 的 `probe`
  会判 fail，要把插件一起退回 v0.4.0。
- 一次性的状态迁移工具（`state_migration.py`）不在这次的恢复范围里：它仍然不是独占执行，中途失败也不会自动回退。
- 信箱里的编排表原样保留、不再读写；以后是否清理另行决定。
- 读取收件箱仍不鉴权：身份按“同一用户、同一台 Mac”的威胁模型处理，Codex 自报的线程编号不作为凭证。
- 0.4.0 列出的已知问题仍然存在（通知横幅、专注模式等），见下方 0.4.0 的“已知问题”。

## [0.4.0] - 2026-10-08

接口升到 **1.3**（`interface.json`）：`bridge_register` 的 `host`、`bridge_agents` 的 `waiting` 与 `host.verified` 都是
1.x 内的兼容新增；Spec Guard 的探测范围 `>=1.0,<2.0` 不用改。其他通知渠道的评估（Codex App 自己的提示、弹窗、
terminal-notifier）见 `spec/acceptance-030-gaps.md` D79；其中“terminal-notifier 未安装”一条已由 `notify-channel` 修正：
装了就用它（见下）。等待列表仍是一定看得到的地方。

- **doctor 按实际通道判断通知**（模块 `notify-channel`，D87）：找到合格的 terminal-notifier 时看它在通知中心的授权，否则看
  脚本编辑器；脚本编辑器无法被允许（它从不申请），所以提示改为“装 terminal-notifier（你决定）或用等待列表”，不再让你去
  设置里找它。`--test-notification` 走同一通道并写明用的哪个。
- **通知改用 terminal-notifier（如果装了）**（模块 `notify-channel`，D83、D84、D86，E2 的根治）：脚本编辑器从未申请通知权限，
  连“系统设置 → 通知”的列表里都没有它，`osascript` 发出的通知全被丢掉。现在只在 Homebrew 的固定路径（`/opt/homebrew/bin`、
  `/usr/local/bin`，从不按 PATH 找）找到合格的 terminal-notifier 时用它：参数只有 `-title`、`-subtitle`、`-group`，正文走
  标准输入，对端写的名字和内容都不会成为选项；2.0.0 与 3.1.0 实测一致。找不到时照旧用 `osascript`，失败也不补发第二条。
- **通知说清是什么事**（模块 `notify-channel`，D89、D89a，用户确认推翻 D67 的“不含正文”）：标题 `agent-relay · <发件会话> →
  Codex`，副标题 `#<编号> · <收件身份> · <原因>`（原因保留“该做什么”，最长 80 字），正文是消息开头最多 60 字的单行预览
  （控制字符与换行变空格，超长加 `…`）。信箱目录放 `notify-preview.off` 恢复旧样式（不含正文）。预览会出现在锁屏和共享
  屏幕上。
- **CI**（模块 `ci-macos`，D80）：GitHub Actions 在 `macos-15` 上为每个 PR 和 `main` 跑 `scripts/validate.sh`（含 bridge 的
  `npm run check`，不允许跳过），Python 3.9（苹果命令行工具自带）/ 3.14 × Node 22 / 24 四个组合；actions 按 SHA 固定，令牌
  只读。是否设为必需检查由维护者决定（README“开发与 CI”）。
- **`validate.sh` 在 Node 22 上也数对 bridge 测试**（模块 `ci-macos`，CI 首跑发现）：Node 22 在非终端下把汇总打印成
  TAP（`# tests 154`），原来只认 Node 24 的 `ℹ tests 154`，于是显示 `?`、总数少 154；现在两种都认。CI 也要求 bridge
  检查后面有测试数，不再接受 `?`。
- **doctor 写明用的是哪个 Python 和 Node**（模块 `ci-macos`，D81）：新增 `toolchain` 检查，无论是否装了运行时都给出 Python
  路径与版本、Node 路径、版本与来源；找不到可用的 Node 时 warn。
- **发给收不到提醒的身份时，发件方会得到警告**（模块 `acceptance-030-gaps`，D72，0.3.0 验收发现 E1）：收件方既没绑定唤醒、
  bridge 也不知道它在哪个宿主（例如以 `wake: null` 注册的 Codex 任务）时，`bridge_send` 的结果加一条警告，说明对方要自己查
  收件箱才会看到。广播、重复发送和 `wake: false` 不提示；不弹桌面通知，投递不变。
- **Codex 不绑唤醒也能登记自己的宿主**（模块 `acceptance-030-gaps`，D75、D75a）：`bridge_register` 新增可选 `host:
  {app: "codex", sessionId: <CODEX_THREAD_ID>}`，只记录宿主、不绑定唤醒；发给它的消息会尝试通知用户，并进入等待列表。
  这只是任务自报，不授予任何权限：不建立绑定、不代替接管、不证明发件身份；从 Claude 会话、与 `wake` 不一致或别的 app 时拒绝。
  `bridge_agents` 的 `host` 与 whoami 的 `recordedHost` 新增 `verified`（只有 Claude 宿主为 true）。collab skill 让 Codex
  不绑唤醒时带上 `host`。
- **升级不再因同一秒的备份撞名而失败**（模块 `acceptance-030-gaps`，D74）：`install-codex --approve-mailbox-tools` 后一秒内
  执行 `upgrade --confirm`，原来会报 “an upgrade with this timestamp already exists; retry in a second”；现在和宿主配置备份一样
  依次改用 `<时间>-1`、`<时间>-2`……，备份、暂存和 `runtime.previous-` 目录共用同一个后缀。
- **doctor 检查通知权限**（模块 `acceptance-030-gaps`，D78）：新增 `notifications` 检查，读取通知中心设置（只读）里
  “脚本编辑器”那一项：从未登记、看起来没允许、读不到都 warn，并写明到“系统设置 → 通知 → 脚本编辑器”打开；看起来已允许
  则 ok（专注模式仍可能挡住，doctor 看不到）。`doctor --test-notification` 按 bridge 的方式弹一条固定内容的测试通知，只在
  带这个参数时弹。判断依据是本机实测的未公开格式，所以只说“看起来”。
- **等 Codex 处理的消息有了一定看得到的地方**（模块 `acceptance-030-gaps`，D77）：`bridge_agents` 给宿主为 Codex 的身份加
  `waiting: {count, from, ids}`（未确认、未失败或过期，最多 20 个编号，不含正文）；collab skill 在你问“有哪些等 Codex 处理的
  消息”时照此回答；doctor 新增 `codex-waiting` 检查，有消息等了超过 10 分钟就 warn，并提示打开那个 Codex 任务。
- **“已通知”改为“已尝试通知”**（模块 `acceptance-030-gaps`，D76，0.3.0 验收发现 E2）：真机上 `osascript` 返回成功但 macOS
  没显示横幅（脚本编辑器从未获准通知），bridge 却告诉发件方 “The user was notified”。现在 wake 详情与发件警告写 “A desktop
  notification was attempted on this Mac; macOS may not show it …”，并指向等待列表与 doctor。
- **README 写明通知权限**（模块 `acceptance-030-gaps`，D73）：bridge 的桌面通知由 `osascript` 发出，macOS 记在“脚本编辑器”
  名下（本机实测 `com.apple.ScriptEditor2`）；看不到横幅时到“系统设置 → 通知 → 脚本编辑器”打开。
- **委派库不再因并发提交偶发报错**（模块 `delegation-sidecar-race`，D71）：检查 SQLite 附属文件时，另一个连接 COMMIT
  删掉了 `-journal`，原来会抛出 `FileNotFoundError`；现在按不存在处理。不安全的附属文件（符号链接、非普通文件、属主或
  权限不对）照旧拒绝。

以上 bridge 改动都要升级运行时才生效（见下）。四个模块：`acceptance-030-gaps`（0.3.0 验收发现的 E1、E2 与升级撞名）、
`delegation-sidecar-race`、`ci-macos`、`notify-channel`。

### 从 0.3.0 升级

1. 两个宿主都更新插件：
   - Claude Code（从 GitHub 装的）：先 `claude plugin marketplace update agent-relay-marketplace`，再
     `claude plugin update agent-relay@agent-relay-marketplace`。
   - Codex：marketplace 钉在 `--ref v0.3.0`（或更早的 tag），直接 `codex plugin add` 拿到的仍是旧版。先把
     `~/.codex/config.toml` 里 `[marketplaces.agent-relay-marketplace]` 的 `ref` 改成 `"v0.4.0"`（自己改，改前留一份副本），
     再 `codex plugin marketplace upgrade`，最后 `codex plugin add agent-relay@agent-relay-marketplace`。
   - 从本地克隆装的：把克隆更新到 v0.4.0 后，Claude 无需其他操作，Codex 再执行一次 `codex plugin add`。
2. **关闭所有使用信箱的会话**：所有 Claude Code 会话，以及 ChatGPT 应用（Codex 的 bridge 由它启动）。在 macOS 自带的
   “终端”里（不要在会话里）确认 `pgrep -fl "agent-relay/runtime/dist/server.js"` 没有输出，再执行
   `python3 -B <插件目录>/hooks/native_collaboration_runtime.py upgrade --confirm`。信箱先备份，历史保留，schema 仍为 5；
   同一秒里已有别的备份时自动改用 `-1` 后缀，不再要求重试。信箱工具的预先批准没有变化，不用重做。
3. `doctor`：`runtime` 为 ok；新的 `toolchain` 写明用的 Python 与 Node；`codex-waiting` 列出等 Codex 处理的消息；
   `notifications` 看实际通道：装了 terminal-notifier 且已允许为 ok，否则 warn 并说明出路。preflight 显示
   `runtime bridge current`、各插件副本 `current`。
4. 想在 macOS 上看到通知横幅：`brew install terminal-notifier`（是否安装由你决定；脚本编辑器那条路在多数 Mac 上走不通），
   第一次弹出时允许它，再跑 `doctor --test-notification` 确认。不装也行：在任一会话里问“有哪些等 Codex 处理的消息”，
   或看 doctor 的 `codex-waiting`。
5. 升级后的行为：
   - 通知默认带消息开头 60 字的预览（锁屏、共享屏幕时也会显示）；不要预览就在 `~/.agent-relay/runtime/mailbox/` 放
     `notify-preview.off`，完全不要通知放 `notify.off`。
   - 重开会话后各自重新注册一次名字。Codex 不绑唤醒时 collab skill 会带上 `host`（本任务的 `CODEX_THREAD_ID`），之后发给
     它的消息会尝试通知并进入等待列表；没带的，发件方会收到“对方要自己查收件箱”的警告。

从更早的版本升级：先按各版本的说明把 `ref` 换成 `"v0.4.0"` 更新插件；从 0.2.x 来的还要先做 0.3.0 说明里的第 2 步
（信箱工具的预先批准），再做上面第 2–5 步（一次 `upgrade --confirm` 即可）。

### 已知问题

- 专注模式可能挡住通知横幅，doctor 看不到专注模式；`notifications` 读的是未公开的通知中心设置格式，只能说“看起来”。
- 不装 terminal-notifier 时，`osascript` 的通知在多数 Mac 上会被系统丢掉（脚本编辑器从不申请通知权限）；以等待列表为准。
- 没带 `host` 注册、也没绑定唤醒的 Codex 身份，bridge 不知道它属于 Codex：发件方只收到警告，不会通知，也不进等待列表。
- 0.2.0 列出的已知问题仍然存在，见下方 0.2.0 的“已知问题”。

## [0.3.0] - 2026-10-08

接口升到 **1.2**（`interface.json`）：自动审批（“帮我批准”）的 Codex 会话现在可以绑定唤醒，属于 1.x 内的兼容变化；
Spec Guard 的探测范围 `>=1.0,<2.0` 不用改。

- **被唤醒的 Codex 回合要用户批准才能动手**（模块 `codex-gated-wake`，D65）：不论审批模式，bridge 唤醒 Codex 的那一轮
  都单独设为用户审批、on-request、只读沙箱且不联网；写文件、执行会改东西的命令、联网都会弹审批卡。用户自己的下一轮
  恢复原设置，`config.toml` 不改。
- **自动审批不再让协作无声卡住**（D66）：取代原来的“拒绝绑定、挂起唤醒”。门控只在确认能生效时使用：**真正挡住老版本
  的是事前的版本门槛**（ChatGPT 应用 26.930 或更新，否则挂起并通知用户）；唤醒后读该线程这一轮的 `turn_context`
  核对只是兜底（每 0.5 秒读一次、最多 10 秒），不符就写 `mailbox/codex-gate.off`、停用门控唤醒并通知用户。
- **Codex 收不到时通知用户**（D67）：不在线、挂起、未绑定唤醒时立即，忙则 10 分钟后仍未送达才通知；macOS 通知，写明
  发件会话和消息编号、不含正文，每条消息最多一次，信箱目录放 `notify.off` 可关闭。
- **doctor 的 `codex-approval` 说法改准**（D68）：App 的审批选择器按轮生效、不写进 `config.toml`；只有 ChatGPT 应用过旧
  或门控被停用时才 warn。
- **信箱工具对 Codex 预先批准**（D70）：`install-codex` 给 10 个信箱工具写 `approval_mode = "approve"`，读信、回复、确认
  不弹卡；已安装的运行 `native_collaboration_adapters.py install-codex --approve-mailbox-tools`（先备份，只补缺的）。
  不写 `~/.codex/rules`。

- **注册被拒时说明名字已退役**（模块 `register-retired-hint`，0.2.1 验收观察 O1）：另一个会话带 `reactivate: true` 注册
  一个已退役的名字时，拒绝信息除了归属冲突，还写明退役时间和退役人，并说明恢复需要同时带 `reactivate: true` 和
  `takeover: true`。只改提示文字，行为不变。

以上 bridge 改动都要升级运行时才生效（见下）。真实 App 上的端到端验收（审批卡、拒绝 / 允许一次、用户下一轮恢复原设置）
在发版后进行。

### 从 0.2.1 升级

1. 两个宿主都更新插件：
   - Claude Code（从 GitHub 装的）：先 `claude plugin marketplace update agent-relay-marketplace`，再
     `claude plugin update agent-relay@agent-relay-marketplace`。
   - Codex：marketplace 钉在 `--ref v0.2.1`（或更早的 tag），直接 `codex plugin add` 拿到的仍是旧版。先把
     `~/.codex/config.toml` 里 `[marketplaces.agent-relay-marketplace]` 的 `ref` 改成 `"v0.3.0"`（自己改，改前留一份副本），
     再 `codex plugin marketplace upgrade`，最后 `codex plugin add agent-relay@agent-relay-marketplace`。
   - 从本地克隆装的：把克隆更新到 v0.3.0 后，Claude 无需其他操作，Codex 再执行一次 `codex plugin add`。
2. 已接入 Codex 的，补上信箱工具的预先批准（会写 `~/.codex/config.toml`，先自动备份，只补缺的子表）：
   `python3 -B <插件目录>/hooks/native_collaboration_adapters.py install-codex --approve-mailbox-tools`。不补也能用，只是
   被唤醒的那一轮每次读信、回复、确认都会弹卡。
3. **关闭所有使用信箱的会话**：所有 Claude Code 会话，以及 ChatGPT 应用（Codex 的 bridge 由它启动）。在 macOS 自带的
   “终端”里（不要在会话里）确认 `pgrep -fl "agent-relay/runtime/dist/server.js"` 没有输出，再执行
   `python3 -B <插件目录>/hooks/native_collaboration_runtime.py upgrade --confirm`。信箱先备份，历史保留，schema 仍为 5。
4. `doctor`：`runtime` 为 ok；`codex-approval` 在 ChatGPT 应用 26.930 或更新时为 ok。preflight 显示
   `runtime bridge current`、各插件副本 `current`。
5. 升级后的行为：“帮我批准”的 Codex 会话也可以绑定唤醒。被叫醒的那一轮是只读的，读信、回复不弹卡（做过第 2 步），
   写文件、执行会改东西的命令、联网都会弹审批卡等你点；你自己的下一轮恢复原设置。消息送不到时会弹 macOS 通知；
   不想要通知，就在 `~/.agent-relay/runtime/mailbox/` 放一个空的 `notify.off` 文件。
6. 如果 doctor 报 “gated Codex wake is off”（同目录出现 `codex-gate.off`）：说明有一轮唤醒没显示出门控。先在 Codex 里
   看那一轮（文件里写着线程和轮次），确认没问题后删掉 `codex-gate.off`，门控唤醒就恢复。

从 0.2.0 升级：先按 0.2.1 的说明把 `ref` 换成 `"v0.3.0"` 更新插件，再做上面第 2–6 步（一次 `upgrade --confirm` 即可）。

### 已知问题

- 门控唤醒需要 `/Applications/ChatGPT.app` 26.930 或更新；读不到版本时 Codex 唤醒一律挂起并通知用户。
- 以 `wake: null` 注册、从未绑定过唤醒的 Codex 身份，bridge 记录不到它属于 Codex，发给它的消息送不到时不会通知。
- 0.2.0 列出的已知问题仍然存在，见下方 0.2.0 的“已知问题”。

## [0.2.1] - 2026-10-08

修复版本：接口升到 **1.1**（`interface.json`）——`bridge_register` 对已退役的名字默认拒绝，需要显式 `reactivate: true`，
属于 1.x 内向后兼容的收紧；Spec Guard 的探测范围 `>=1.0,<2.0` 不用改。补上清理 0.2.0 测试遗留时发现的三个缺口
（模块 `cleanup-gaps`，规格 [spec/cleanup-gaps.md](spec/cleanup-gaps.md)）。真实宿主上已验证 D59、D60。

- **D59 退役不再被过期消息挡住**：`native_collaboration_retire.py` 按 bridge 的未读规则计数，已过期的消息不算；仍挡住
  退役的消息在拒绝信息里列出编号和投递状态（最多 10 个，不含正文）。
- **D60 宿主拒绝、从未发出过一轮的 Codex 委派可以取消**：线程拿到了 id、却在发出第一轮之前就启动失败，宿主又拒绝该线程时，
  `cancel` 直接收尾为 `cancelled`，附 `host-thread-absent`；其他 `unknown` 照旧不自动收尾。
- **D61 已退役的名字不会被悄悄恢复**：`bridge_register`（含 `takeover`）遇到已退役的名字时拒绝，只有带
  `reactivate: true`（需用户同意）才恢复，结果写明 `reactivated: true`。改动在随插件附带的 bridge 里（记录见
  `bridge/UPSTREAM.md`），**要升级运行时才生效**。
- **D62 接口 1.1**：`interface.json` 从 1.0 升到 1.1。
- **D63 Codex 委派的身份已被退役时，追问返回 `held/identity-retired`**，不再发出（否则重新注册会被拒、结果回不来）。
- **preflight** 多一行 `runtime bridge`：已装运行时的 bridge 是否与本检出一致；只更新了插件、没有升级运行时会显示
  `OLDER`。

### 从 0.2.0 升级

1. 两个宿主都更新插件：
   - Claude Code（从 GitHub 装的）：先 `claude plugin marketplace update agent-relay-marketplace`，再
     `claude plugin update agent-relay@agent-relay-marketplace`。
   - Codex：marketplace 钉在 `--ref v0.2.0`，直接 `codex plugin add` 拿到的仍是 0.2.0。先把 `~/.codex/config.toml` 里
     `[marketplaces.agent-relay-marketplace]` 的 `ref` 改成 `"v0.2.1"`（自己改，改前留一份副本），再
     `codex plugin marketplace upgrade`，最后 `codex plugin add agent-relay@agent-relay-marketplace`。
   - 从本地克隆装的：把克隆更新到 v0.2.1 后，Claude 无需其他操作，Codex 再执行一次 `codex plugin add`。
2. 到这一步插件已是 0.2.1，但运行时里的 bridge 还是旧的：`doctor` 的 `runtime` 为 warn（bridge is older），
   `scripts/acceptance/preflight.sh` 显示 `runtime bridge OLDER`，D61 尚未生效。
3. **关闭所有使用信箱的会话，退出 Codex**，再执行
   `python3 -B <插件目录>/hooks/native_collaboration_runtime.py upgrade --confirm`（有 bridge 在运行时它会拒绝）。它先把信箱
   备份到 `~/.agent-relay/backups/<时间>/`，再换上新 bridge；信箱历史保留，schema 不变（仍为 5）。
4. `doctor` 的 `runtime` 为 ok，preflight 显示 `runtime bridge current`、各插件副本 `current`。
5. 之后对已退役的名字 `bridge_register` 会被拒：换一个新名字，或经用户同意后带 `reactivate: true`。

### 已知问题

- 0.2.0 列出的已知问题仍然存在，见下方 0.2.0 的“已知问题”。

## [0.2.0] - 2026-10-08

加固版本：接口仍为 1.0（`interface.json`），Spec Guard 的探测范围 `>=1.0,<2.0` 不用改。经过两轮真实宿主联调与
定向复跑，记录见 [第二轮](docs/acceptance/2026-10-07-round2.md)、[第二轮定向复跑](docs/acceptance/2026-10-07-round2-rerun.md)、
[验收工具与适配器验收](docs/acceptance/2026-10-08-acceptance-kit-round2.md)。

### 加固模块

- **delegation-fixes**：等待前置条件的 create 不再让之后的同名会话产生歧义，从未启动的记录能干净取消；git worktree
  里的 Claude 目标创建后能找到，第二轮 `continue` 可用（基线发现 3、4，第一轮联调发现 7）。
- **test-isolation**：`AGENT_RELAY_HOME` 把整个状态根（运行时、委派库、迁移备份）整体迁到别处；所有测试在临时状态根里
  运行，不碰真实的 `~/.agent-relay`。
- **bridge-vendoring**：上游 bridge（固定提交 8f12c88，MIT）收进仓库并按 `UPSTREAM.sha256` 核对，运行时从仓内副本
  安装，不再 git clone。
- **delivery-state-machine**：投递状态机（queued → sending → accepted / failed / unknown；queued → expired），有歧义的
  提交标为 unknown 且绝不自动重放，超时过期。
- **durable-ordering**：先持久化再提交；按接收方保证顺序，一个接收方卡住不影响其他；每个接收方的待投递数量有上限。
- **idempotency**：同一重试 key 只对应一份内容；回复带上被回复消息的编号，同样的回复只存一次。
- **identity-check**：发件人必须是本会话证明过的身份；只有收件人能回复；名字不能被别的宿主会话改绑（需显式接管）；
  Codex 自动审批（`approvals_reviewer = "guardian_subagent"` 或 `approval_policy = "never"`）时拒绝唤醒绑定、ping 暂存。
- **ops-commands**：`doctor`（运行时、探测、信箱、宿主接入、Codex 审批、唤醒绑定、旧 bridge 全面只读体检）、whoami、
  按消息编号查状态与等待、正文从文件读入，`--expires-at` 接受 ISO 8601 或 epoch 秒。
- **safe-uninstall**：`uninstall-codex` 连同 Codex 的“始终允许”审批子表一并移除，其他差异逐行指出；每次写宿主配置
  前先备份（目录 0700、文件 0600）；`native_collaboration_runtime.py uninstall --confirm` 删除构建、保留消息历史；
  写明完整卸载流程。
- **round2-fixes**：被委派的 Claude 目标先注册、等信箱工具就绪再作答，结果必定回传；委派控制器和 doctor 用宿主条目
  固定的 node；迁移和卸载后重装在 macOS 自带 Python 3.9 下可用；有 Claude 会话开着时保留 7 条拒绝规则。
- **acceptance-kit-round2**：preflight 比对各宿主实际加载的副本（`current`／`STALE` 加刷新命令），打印 base／routing
  两套允许清单（`--design`）和提示词在前的启动命令；skill 用宿主代入的 `${CLAUDE_PLUGIN_ROOT}` 找自己的代码；
  install／upgrade／退役用固定的 node，npm 也跑在它上面；`cleanup.sh` 在 Python 3.9 下可读信箱。
- **adapter-node**：宿主适配器（`install-claude`／`install-codex` 及打印配置）写入宿主条目固定的 node，node 过旧时在
  写任何东西之前拒绝；`uninstall-codex` 始终可用。

### 已修复的 0.1.0 已知问题

- Codex → Claude Code 委派的第二轮可用（delegation-fixes、round2-fixes）。
- 授权检查进入 bridge：Codex `guardian_subagent` 识别为自动批准，回复校验发件人与收件人（identity-check）。
- 完整的投递状态机、幂等键与过期处理（delivery-state-machine、durable-ordering、idempotency）。
- 选过“始终允许”后 `uninstall-codex` 也能删除受管条目（safe-uninstall）。

### 第二轮联调发现

- R2-1 doctor 用 PATH 的 node 探测；R2-7 委派控制器用 PATH 的 node：改用宿主条目固定的 node（round2-fixes）。
- R2-6 被委派的 Claude 目标在信箱工具连上前作答、结果不回传：已修复（round2-fixes）。
- R2-9 迁移和卸载后重装在 macOS `/usr/bin/python3` 3.9 下失败：已修复，支持 Python 3.9 到 3.14（round2-fixes）。
- R2-10 卸载 Claude 时仍开着的会话看到上游 worker 工具：有会话开着时保留拒绝规则（round2-fixes）。
- R2-3 启动命令吞掉提示词；R2-5 Codex 跑旧副本；R2-8 测试会话允许清单不全；R2-11 skill 可能选中旧缓存；
  R2-12 重装、退役、清理脚本在旧 node 与 Python 3.9 下失败：已修复（acceptance-kit-round2）。
- R2-13 宿主适配器写入 PATH 的 node：已修复（adapter-node）。
- R2-2 Codex App 的审批选择器不写 `config.toml`；R2-4 验收中出现两个来历不明的“始终允许”子表：宿主行为，见已知问题。

### 从 0.1.0 升级

1. 关闭所有使用信箱的会话，退出 Codex。
2. `python3 -B <插件目录>/hooks/native_collaboration_runtime.py upgrade --confirm`：先把信箱备份到
   `~/.agent-relay/backups/<时间>/`，再换上新版运行时，信箱从 schema 2 升到 5。0.1.0 插件不认 schema 5：要回滚就连插件一起回滚，或用备份恢复信箱（之后的消息会丢失）。
3. 两个宿主都更新插件：
   - Claude Code（从 GitHub 装的）：先 `claude plugin marketplace update agent-relay-marketplace` 拉到新目录，再
     `claude plugin update agent-relay@agent-relay-marketplace`。
   - Codex：0.1.0 的安装方式把 marketplace 钉在 `--ref v0.1.0`，直接 `codex plugin add` 拿到的仍是 0.1.0，而
     `codex plugin marketplace add --ref` 遇到同名 marketplace 会拒绝。所以先把 `~/.codex/config.toml` 里
     `[marketplaces.agent-relay-marketplace]` 的 `ref` 改成 `"v0.2.0"`（自己改，改前留一份副本），再
     `codex plugin marketplace upgrade`，最后 `codex plugin add agent-relay@agent-relay-marketplace`。
   - 从本地克隆装的：把克隆更新到 v0.2.0 后，Claude 无需其他操作（直接读源目录），Codex 再执行一次 `codex plugin add`。
   - 可用 `scripts/acceptance/preflight.sh` 确认各副本都是 `current`。
4. `python3 -B <插件目录>/hooks/native_collaboration_runtime.py doctor`，看到 `ok` 即可。
5. 之后每个会话重新注册一次身份（`bridge_register`），以记录它所在的宿主会话。
6. Codex 设为 AI 自动审批（`approvals_reviewer = "guardian_subagent"`）时，唤醒绑定会被拒、ping 会暂存；需要唤醒
   Codex 时请在 App 里把审批切到“请求批准”。

### 已知问题

- 在 PATH 首位是旧 node（例如 v12）的 shell 里，codex CLI 本身无法启动，preflight 的 Codex 一栏显示 `unknown`。
- 在保留历史上重装运行时、卸载运行时，都要求先关闭所有使用信箱的会话（有 bridge 在运行时会拒绝）。
- Codex App 的审批选择器不会写入 `config.toml`（R2-2）：doctor 按文件判断，以文件为准。
- schema 3 之前的旧消息状态显示为 `queued`；多个 Codex 线程共用同一个 bridge 进程时会共享已证明的身份名。

## [0.1.0] - 2026-10-07

首个版本：平移版本，行为与拆分前 Spec Guard 0.49.0 的协作能力一致（见
[docs/collaboration-interface.md](docs/collaboration-interface.md) 的“现状”栏）。代码连同逐文件历史从
Spec Guard 迁入，旧记录在 `docs/history/spec-guard/`。

### 新增

- **协作信箱**：同一台 Mac 上 Claude Code 与 Codex 会话互相发消息、回复、按需唤醒；`collab` skill 与
  `/agent-relay:collaboration` 命令。信箱运行时是固定提交的上游 bridge（MIT），装在 `~/.agent-relay/runtime/`。
- **会话路由**：按会话名字联系另一个会话；同宿主走宿主自带通信，跨宿主走信箱；同名时给出短编号让用户选
  （`session-routing` skill）。
- **跨宿主会话委派**：一句话创建 Codex 审查或 Claude Code 开发会话，有限授权、结果回传到发起会话
  （`session-delegation` skill）。
- **运行时管理**：只读检查，经用户同意后安装运行时、接入或移除宿主配置、退役身份（`collaboration-ops` skill）。
- **从 Spec Guard 迁移**：`state_migration.py detect / migrate --confirm` 先备份、只复制、逐表核对条数，不改
  `~/.spec-guard/`；有未结束的旧委派或仍在运行的旧 bridge 时拒绝迁移。
- **接口声明** `interface.json`（接口 1.0）与 `relay_status.py`，供 Spec Guard 0.50.0 检测本插件。
- 真实宿主验收清单 `docs/acceptance/checklist.md` 与第一轮接入联调记录 `docs/acceptance/2026-10-07-round1.md`。

### 已知问题

均记录在接口文档“现状”栏，计划在加固版本处理：

- Codex → Claude Code 委派的第二轮不可用：0.1.0 在 Claude Code 2.1.291 上创建后报 `state=unknown`，随后
  `continue` 被拒（第一轮联调发现 7；早先宿主上的表现是空闲时报 `target-busy`）。
- 授权检查只在 skill 规则里：Codex `approvals_reviewer = "guardian_subagent"` 不被识别为自动批准；回复不校验
  发件人身份。
- 投递状态只有入箱与唤醒结果，没有完整的送达状态机、幂等键与过期处理。
- 在 Codex 里对信箱工具选过“始终允许”后，`uninstall-codex` 会把受管条目视为已被用户修改而拒绝删除，需要手工删除
  （第一轮联调发现 6）。

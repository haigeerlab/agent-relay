# Changelog

## [Unreleased]

接口升到 **1.3**（`interface.json`）：`bridge_register` 的 `host`、`bridge_agents` 的 `waiting` 与 `host.verified` 都是
1.x 内的兼容新增；Spec Guard 的探测范围 `>=1.0,<2.0` 不用改。其他通知渠道的评估（Codex App 自己的提示、弹窗、
terminal-notifier）见 `spec/acceptance-030-gaps.md` D79，结论是不加，以等待列表为准。

- **CI**（模块 `ci-macos`，D80）：GitHub Actions 在 `macos-15` 上为每个 PR 和 `main` 跑 `scripts/validate.sh`（含 bridge 的
  `npm run check`，不允许跳过），Python 3.9（苹果命令行工具自带）/ 3.14 × Node 22 / 24 四个组合；actions 按 SHA 固定，令牌
  只读。是否设为必需检查由维护者决定（README“开发与 CI”）。
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

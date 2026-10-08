# Capability Map: agent-relay

> 由 `/spec` 的 Phase 0 产出。**必须经人工评审后才能往下走。**
> Addy 原文：把图搞错代价很大，评审十行不算什么。

## 目标

agent-relay 是从 Spec Guard 拆出的独立插件，让同一台 Mac 上的 Claude Code 与 Codex 会话互相发消息、按名字找到对方并在有限授权内委派会话，
不需要安装 Spec Guard 的工作流。先平移：每个模块的行为与拆分前基线（`docs/baselines/collaboration-pre-split.md`）一致，以
`docs/collaboration-interface.md` 的现状栏为准；平移版本通过第一轮接入联调后，再按加固目标栏逐项加固。

<!-- 这一段是 Proposal 评审的目标指纹底本（`spec-digest.py` 计算）。
     改写目标会让已发布的 Proposal 被判为过期，所以改了先人工评审；追加模块不需要改这里。
     标题必须是 `## 目标`（或 `## Goal`）—— 指纹脚本按标题定位这一节。 -->

## 模块

| Module id | Responsibility | Depends on |
|---|---|---|
| acceptance-kit | 建立本仓库的测试运行入口与可复用的真实宿主验收脚本和清单，供平移、加固与两轮联调共用；修正迁出时读 Spec Guard 文件的 4 个测试，使迁入代码的测试全绿。 | — |
| mailbox-core | 平移协作信箱与 native 传输：固定上游 bridge 的运行时、宿主适配器与身份退役，按决策 D1 改用 `agent-relay` MCP 服务名与 `~/.agent-relay/` 状态根，行为与基线一致。 | acceptance-kit |
| session-routing | 平移统一会话路由：Claude↔Claude 走 ListAgents/SendMessage、Codex↔Codex 走 Codex App task/thread、Claude↔Codex 走信箱，回退规则与基线一致。 | mailbox-core |
| cross-host-delegation | 平移跨宿主会话委派：授权意图、生命周期、结果回传与同名消歧，控制器与基线一致，基线记录的已知缺陷保持原样。 | mailbox-core, session-routing |
| packaging | 双端插件清单与 marketplace、`interface.json`（接口 1.0）、README、安装与卸载说明，并在 Claude Code 与 Codex 上实装验证。 | mailbox-core, session-routing, cross-host-delegation |
| state-migration | 检测 Spec Guard 时期的协作状态（`~/.spec-guard/native-collaboration/`、`session-delegation/` 与宿主中的旧 MCP 条目和权限规则），先备份再迁移到新名字并核验，不静默删除。 | mailbox-core, packaging |
| delegation-fixes | 修复基线发现 3、4 与第一轮联调发现 7：等待前置条件的 create 不再让之后的同名会话产生歧义，从未启动的记录能干净取消；git worktree 里的 Claude 目标创建后能找到，列表对不上时下一次调用补绑而不是一直停在 unknown；空闲 Claude 目标第二轮不再误报 target-busy。在平移版本通过第一轮联调后、加固模块之前构建。 | cross-host-delegation, state-migration |
| test-isolation | 用一个环境变量把整个 agent-relay 状态根（信箱运行时、委派库、迁移备份）整体迁到别处，控制器、迁移与验收脚本都遵守；所有测试在临时状态根里运行，不读写真实的 ~/.agent-relay。加固模块中最先做，后续加固的测试都依赖它。 | mailbox-core, cross-host-delegation, state-migration |
| bridge-vendoring | 把固定提交 8f12c88 的上游 bridge（TS 源码）收进 agent-relay 仓库，保留 MIT 署名与来源说明；运行时改为从仓内副本安装，不再 git clone 上游。只改来源和安装路径，行为与 8f12c88 完全一致；之后修改 bridge 的加固模块都依赖它。 | mailbox-core, test-isolation |
| delivery-state-machine | 给信箱消息补上投递状态机（queued → sending → accepted、failed 或 unknown；queued → expired）：有歧义的提交标为 unknown 且绝不自动重放；排队超时后标为 expired、默认不再读出也不再送达，超时可配置并给出默认值建议；ack 让对应唤醒任务结束（发现 5）。同时实现 bridge-vendoring D26 规定的已装运行时升级命令。 | mailbox-core, bridge-vendoring |
| durable-ordering | 先持久化再提交（以崩溃注入测试证明）；按接收方保证投递顺序，一个接收方卡住不阻塞其他接收方；每个接收方的待投递数量有上限，上限可配置并给出默认值建议。 | delivery-state-machine |
| idempotency | 同一发送方的重试 key 只对应一份内容：内容相同返回原消息，内容不同拒绝；回复带上被回复消息的 id，对同一条消息的相同回复去重。 | durable-ordering |
| identity-check | 发送方 from 必须与调用方宿主会话绑定的身份一致，不一致拒绝；只有原消息的收件人能回复它；名字不能被另一个宿主会话改绑；身份缺失时返回明确指引；自动批准的会话（含 Codex guardian_subagent）不能绑定唤醒（发现 1）；并修正 bridge 打开信箱时 busy_timeout 设置晚于 journal_mode 的问题。 | idempotency |
| ops-commands | 运维命令：doctor（运行时、宿主接入、信箱与会话健康检查，含后台会话可能卡在权限提示的情况，基线发现 6）、whoami（本会话的身份、宿主、会话与项目）、按消息 id 查询状态与等待；消息正文可从文件读入并原样送达；委派的 --expires-at 接受并写明一种时间格式（基线发现 2）。 | identity-check |
| safe-uninstall | 卸载更稳妥：uninstall-codex 识别 Codex 在用户选“始终允许”时写入的工具审批子表并一并移除，其他差异逐行指出（第一轮联调发现 6）；任何宿主配置写入（安装与卸载）前先备份；提供并写明完整卸载流程，消息历史默认保留。 | ops-commands |
| round2-fixes | 修复第二轮联调发现的发布阻断问题：被委托的 Claude 目标等信箱工具就绪后再作答，结果必定回传（R2-6）；委托控制器与 doctor 使用宿主条目固定的 node，或在动宿主前以 Node 版本过旧拒绝（R2-7、R2-1）；state_migration 与卸载后重装在 macOS 自带 Python 3.9 下可用，写明支持的 Python 版本并在 3.9、3.10、3.14 上验证全绿（R2-9）；卸载 Claude 时不让仍开着的会话看到被禁的上游 worker 工具（R2-10）。 | safe-uninstall |
| acceptance-kit-round2 | 补上第二轮联调暴露的验收与安装路径缺口：preflight 打印的后台会话启动命令把提示词放在选项之前，不再被 --allowedTools 吞掉（R2-3）；preflight 比对各宿主实际加载的插件与登记的安装路径、缓存和源码，旧副本直接报出，skill 解析插件根目录时不会选中旧缓存（R2-5、R2-11）；A4 测试会话的允许清单覆盖被测 skill 所需的会话路由选择器命令与 D9 跨项目读取规则，或由清单写明需额外添加的规则（R2-8）；在 PATH 首个 node 过旧、python3 为系统 3.9 的 shell 里，在保留历史上重装运行时（npm 用选中的 node 启动）、身份退役与验收清理脚本都能完成，沿用 D50 的 node 选择与 D51 的只读打开（R2-12）。 | acceptance-kit, round2-fixes |
| adapter-node | 宿主适配器 install-codex、install-claude 及打印配置的 codex、claude 按 D50 的顺序选 node（--node → Claude 条目 → Codex 表 → PATH），低于 22.5.0 时在写宿主配置之前拒绝，PATH 首个 node 过旧时写入的仍是宿主条目固定的 node（R2-13）。 | acceptance-kit-round2 |
| cleanup-gaps | 补上 0.2.0 清理测试遗留时发现的三个缺口：已过期的消息不再挡住身份退役，或拒绝时列出卡住的消息编号与状态；宿主明确拒绝（host-request-rejected）且线程从未建立的委派，cancel 在本地收尾为 cancelled，其他 unknown 仍不自动处理；register（含 takeover）遇到已退役的名字时拒绝，只有显式要求恢复时才重新启用，并在结果里写明原先已退役。 | delivery-state-machine, identity-check, delegation-fixes |
| register-retired-hint | bridge_register 因名字属于另一个会话而拒绝时，若该名字已退役，拒绝信息同时写明退役时间与退役人，并说明恢复需要同时带 reactivate: true 和 takeover: true（0.2.1 验收观察 O1）；其他拒绝与成功路径不变。 | cleanup-gaps |
| codex-gated-wake | Codex 处于自动审批（帮我批准 / approval_policy never）时协作不再无声卡住：消息到达时让用户看得见是哪个会话给 Codex 派了活；唤醒照常发出，但被唤醒的那一轮按轮改为用户审批、on-request、只读沙箱，任何执行都须用户批准，用户自己的对话设置不变；对端消息永远不能在无人批准时触发执行；唤醒只按绑定的 sessionId 精确定位线程；doctor 的 codex-approval 提示改为准确说法。 | identity-check, delivery-state-machine, ops-commands |
| delegation-sidecar-race | 委派库检查 SQLite 附属文件时，另一连接 COMMIT 删除 -journal 不再抛出 FileNotFoundError：附属文件消失视为不存在，不安全的附属文件（符号链接、非普通文件、属主或权限不对）仍拒绝；以确定性测试复现该时序，并在 Python 3.9、3.10、3.14 上验证。 | cross-host-delegation |
| acceptance-030-gaps | 补上 0.3.0 验收与升级时发现的缺口：发给既没绑定唤醒、宿主也未知的收件方时，发件结果警告对方要自己查收件箱才会看到（E1，Claude 与 Codex 收件方都适用，不发桌面通知）；README 写明横幅不出现时给“脚本编辑器”开通知权限；runtime upgrade 的备份目录与前一次备份同一秒撞名时不再报错要求重试。 | mailbox-core, codex-gated-wake |
| ci-macos | 在 GitHub Actions 的 macOS 上为每个 PR 和 main 跑 scripts/validate.sh（含 bridge 的 npm run check），覆盖 Python 3.9/3.14 与 Node 22/24 的代表组合；doctor 打印实际使用的 python 与 node 的路径和版本；是否设为 main 的必需检查留给用户在跑绿后决定。 | bridge-vendoring, ops-commands |
| notify-channel | bridge 的桌面通知在 terminal-notifier 已安装（只认固定路径）时优先用它，否则退回 osascript；以参数数组调用、只用 -title/-subtitle/-group，正文走标准输入，对端可控的名字以“-”开头或含换行也不会被当成选项；通知默认显示消息开头的简短预览（notify-preview.off 关闭）；doctor 的 notifications 按实际会用的通道判断是否获准。 | codex-gated-wake, acceptance-030-gaps |
| orchestrator-removal | 删除 bridge 里的 Codex 编排器（6 个编排工具、orchestrator.ts、bridge_retire 的 MCP 工具，与 delegate 插件重叠且在所有宿主禁用）；server 只注册 10 个信箱工具，探针改为工具集合精确相等，旧的拒绝规则与审批子表只用于卸载清理；schema 与编排表不动，interface 保持 1.3。 | bridge-vendoring, safe-uninstall, codex-gated-wake |
| legacy-cli-cleanup | 清理 bridge 里上游遗留的 TS CLI 控制面：删除 setup、uninstall、rollback 等与 Python 运行时重复的安装命令（安装、升级、卸载只认 Python 运行时），保留用户手动用的只读命令与 retire；用户可见的 claude-codex-bridge 名称统一为 agent-relay，不丢已有数据、不改宿主协议里的标识；doctor 去掉已无用途的 --claude-settings。 | orchestrator-removal, safe-uninstall, ops-commands |
| inbox-read-receipt | 只有调用方是该身份本人时，bridge_inbox、bridge_wait（不确认时）和 bridge_outbox 才记已读、刷新活跃时间；旁观者读取不改变投递状态、不停止对真正收件人的唤醒，结果里新增可选字段写明这次读取未记为已读（接口升到 1.4）；不加读取鉴权，威胁模型不变。 | identity-check, delivery-state-machine, legacy-cli-cleanup |
| upgrade-recovery | 运行时 upgrade 与 reinstall 的目录切换可恢复：最后一步切换纳入回滚保护，进程中断后再次运行能识别半途状态并完成或回滚、数据不丢；reinstall 的临时目录唯一且只清理自己建的；新增 rollback --confirm 把运行时换回上一份并带走信箱与数据，同样要求会话全部关闭。状态迁移工具不在本模块。 | delivery-state-machine, acceptance-030-gaps, legacy-cli-cleanup |
| retire-cli-guard | bridge 的 TS CLI（dist/cli.js retire）在没有 BRIDGE_DB_PATH 时拒绝执行并指向 native_collaboration_retire.py，不再退回上游默认库 claude-codex-bridge/bridge.sqlite、不打开或改动它；经 Python 脚本退役的行为、输出与退出码不变。 | legacy-cli-cleanup |
| server-db-guard | bridge 的 MCP 服务（dist/server.js）在没有 BRIDGE_DB_PATH 时拒绝启动并说明要由 agent-relay 的宿主接入启动，不再退回上游默认库 claude-codex-bridge/bridge.sqlite、不打开或新建它；宿主接入、探针与委派照常显式传入路径，行为不变。 | retire-cli-guard |
| state-migration-safety | 一次性状态迁移（state_migration.py migrate --confirm）独占执行且可恢复：同一时间只允许一次迁移，agent-relay 自己的 bridge 在跑时也拒绝；写入先在旁边准备好、核对行数后再换上，任何一步失败或进程中断都回到迁移前的样子，不留下“目标已有数据、无法重试”的半截状态；旧的 Spec Guard 目录照旧只读不动。 | state-migration, upgrade-recovery |
| delegation-claim | 委派的创建与继续在对宿主产生任何外部效果（启动 Claude/Codex 会话、开始新一轮）之前，先在委派库里原子地认领这一次操作：同一委派同一时间只有一个调用能启动宿主，并发的另一个调用直接得到“正在进行”而不再启动；认领后若宿主明确未启动则释放，结果不确定时照旧记为 unknown；Claude 与 Codex 两个适配器同样处理。 | cross-host-delegation, delegation-fixes |

Build order: acceptance-kit → mailbox-core → session-routing → cross-host-delegation → packaging → state-migration → delegation-fixes → test-isolation → bridge-vendoring → delivery-state-machine → durable-ordering → idempotency → identity-check → ops-commands → safe-uninstall → round2-fixes → acceptance-kit-round2 → adapter-node → cleanup-gaps → register-retired-hint → codex-gated-wake → delegation-sidecar-race → acceptance-030-gaps → ci-macos → notify-channel → orchestrator-removal → legacy-cli-cleanup → inbox-read-receipt → upgrade-recovery → retire-cli-guard → server-db-guard → state-migration-safety → delegation-claim

<!-- Spec Guard 按严格串行推进。为兼容上游格式，逗号分组会按左到右顺序展开为单模块步骤，不代表并行授权。 -->
<!-- 加固模块（test-isolation、delivery-state-machine、durable-ordering、idempotency、identity-check、ops-commands、
     safe-uninstall）在第一轮联调通过后用 add-module 逐个插入，不在本次评审范围内。 -->

---

## 评审记录

- [x] 模块边界确认（砍掉或替换一个模块，不需要重写其他模块的需求）
- [x] 依赖方向单向无环（互相依赖 = 它们本来就是一个模块）
- [x] module id 已定稿（kebab-case，之后绝不改名 —— 同一个 id 同时是
      `spec/<id>.md`、`tasks/<id>/`、`.agent/state.json` 的 `activeModule` 和 Proposal 中的模块名，
      已发布的 Proposal 改不动）
- [x] 构建顺序符合依赖拓扑

评审人：用户（delegation-fixes 在第一轮联调通过后、加固之前构建；D7 测试归 acceptance-kit；D1 改名归 mailbox-core）
日期：2026-10-07

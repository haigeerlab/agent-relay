# 任务：把 spec-guard 的协作能力拆分为独立插件（全程由 spec-guard 引导开发）

## 背景

仓库：haigeerlab/spec-guard-plugin（本地：/Users/vilin/Documents/haigeerlab/spec-guard-plugin）

spec-guard 目前内置一组默认关闭的协作能力：
- 协作信箱（`/spec-guard:collaboration`，native 传输）
- 统一会话路由（Claude↔Claude 复用 ListAgents/SendMessage；Codex↔Codex 复用 Codex App task/thread；Claude↔Codex 走 native 信箱）
- 跨宿主会话委派（Claude Code 创建 Codex 会话，或反过来）

详细说明见 `plugins/spec-guard/references/collaboration-runtime.md` 和 `docs/optional-features.md`。

拆分原因：
1. 设计会话（使用 huashu-design skill 的会话）需要跨会话通信，但不应安装 spec-guard 的工作流。
2. 通信层跟随 Claude Code / Codex 原生接口变化，迭代节奏与工作流不同，不应互相牵连发版。
3. 唤醒和授权是安全敏感部分，需要独立审计和测试。
4. 协作能力依赖 macOS + Node.js，只用工作流的用户不该承担这些依赖。

参考项目：OpenSwarm（https://github.com/rubinownz111/openswarm，MIT）。只借鉴它的可靠性设计，不引入它作为依赖，也不复制代码。

## 目标

1. 新建独立插件 `<新插件名>`，同时支持 Claude Code 和 Codex 安装，包含上述三项协作能力。
2. spec-guard 删除协作实现，只通过新插件的公开接口调用协作能力。
3. 只装新插件、不装 spec-guard 的会话，可以完整使用协作能力。
4. 只装 spec-guard、不装新插件时，工作流完全不受影响；用到协作时给出明确的安装提示。
5. 平移完成后，在新插件里做可靠性加固。
6. 最终接入联调（阶段 4）在加固版本上全部通过，才算接入成功。

## 核心原则

- **全程由 spec-guard 引导**：两个仓库的所有开发都按 spec-guard 的约定推进：能力图 → 模块 Spec → plan → build，以当前阶段提示为准，在共享检查点停下汇报。不绕开 spec-guard 自行组织任务。
- **先平移，再加固**：平移模块的行为必须与基线完全一致；加固模块在平移版本通过第一轮接入联调之后才开始。两者不得混在同一个提交或同一个版本里。
- **约束优先于评审**：边界和规则尽量用测试或校验强制，而不是靠人工检查。
- **以基线为准**：所有"行为一致"的判断，都以阶段 0 记录的基线为依据，不凭记忆或推测。

## 非目标（不要做）

- 不做跨机器通信，不做跨平台支持（但接口设计不得排斥以后支持）。
- 不改动授权模型：加入协作默认不绑定唤醒（`wake: null`）；开着自动批准的会话永远不绑定；初始化、改配置、加入新身份、扩权都要逐项确认；不自动修改项目或全局权限。
- 不借鉴 OpenSwarm 的信任模型：不采用"同一系统用户下互相信任"，不在安装时一次性放开入站策略。
- 不迁移本地事项账本、文档治理、能力历史等其他可选能力，它们留在 spec-guard。
- 未经我明确批准，不 push、不打 tag、不发布、不改远端仓库设置。

## 工作规则

- **引导版本固定**：开发期间，用于引导开发的 spec-guard 固定为当前已安装的发布版本，不得替换为开发中的分支版本。需要安装拆分版 spec-guard 进行验证时，只能装在项目级别或隔离环境中，验证结束后确认引导版本未被改变。做不到隔离时，先停下来问我。
- **任务说明持久化**：本提示词在阶段 1 保存到仓库中（见 1.1）。每次上下文被压缩或新开会话后，先重读该文件，再继续工作。
- **前置条件**：agent-skills 和 spec-guard 已在当前宿主安装。Codex 不加载斜杠命令，用自然语言调用对应的 skill（对照表见 spec-guard 的 docs/workflow.md）。
- 先读并遵守两个仓库的 AGENTS.md、CLAUDE.md，以及 spec-guard 的 docs/maintainer-workflow.md、docs/release-process.md。
- 每次到达检查点（模块完成、阶段切换、遇到阻塞）时停下来，按以下格式汇报，等我确认再继续：
  当前仓库、阶段与模块 / 已完成什么 / 证据（命令输出、测试结果、文件清单）/ 风险与未决问题 / 下一步。
- 能力图和每个模块的 Spec 都要经过我评审，才能进入 plan。
- 遇到需求不明确、或必须改变现有行为才能继续时，停下来问，不要自行决定。
- 小步提交，每个提交只做一件事，提交信息说明原因。

## 阶段 0：盘点与基线（在 spec-guard 仓库进行，除基线文件和备份分支外不改任何文件）

1. **备份**：从当前 main 建立本地备份分支 `backup/pre-collaboration-split`，作为回滚点。
2. **前提确认**：
   - Codex 能否从本地路径添加 marketplace 并安装插件（阶段 4 依赖这一点）；
   - 本机 `gh` 是否已登录（spec-guard 仓库的 Proposal 流程需要）；
   - Claude Code 和 Codex 的插件系统是否支持声明对另一个插件的依赖，给出官方文档链接。
3. **盘点**：列出所有与协作相关的文件：skill、斜杠命令、hook、MCP 工具（含 `bridge_` 系列）、脚本、配置项、状态与信箱的存储路径、文档、测试、evals、验收记录。
4. **依赖关系**：
   - spec-guard 的哪些部分调用了协作能力（例如共享检查点、事项短编号写进协作消息）；
   - 协作代码依赖了 spec-guard 的哪些内部模块。
   两个方向都要列清楚，标出每一个需要切断的耦合点。
5. **基线**：在拆分前的 spec-guard 上运行全部单元测试、evals，以及现有的真实宿主验收流程（需要我打开哪些会话，先列清单等我准备好）。结果保存为 `docs/baselines/collaboration-pre-split.md`，记录宿主版本号、每一项的结果和证据。
6. **差距分析**：对照 OpenSwarm（阅读它的 README 和 docs/protocol.md），对下面每一项标注现状（已有 / 部分 / 没有），并附上代码位置作为证据：
   a. 投递状态机：queued / sending / accepted / failed / unknown / expired
   b. 状态未知的消息绝不自动重放
   c. 排队超时后过期，之后不会再送达
   d. 先持久化再提交给原生接口
   e. 按接收方保证顺序；各接收方互不阻塞；待投递数量有上限
   f. 幂等重试 key（同一个 key 只允许内容完全相同）；重复回复去重
   g. 只有收件人能回复；校验发送方与宿主身份一致
   h. 运维命令：doctor（健康检查）、whoami、按消息 id 查询 status / 等待 wait
   i. 消息正文从文件传入，避免 shell 插值
   j. 状态目录可以用环境变量覆盖（用于测试隔离）
   k. 修改宿主设置前先备份；卸载步骤完整，卸载不删除消息历史
7. **命名**：提出 3 个新插件名称候选，并说明理由。
8. **迁移方式**：给出代码迁移方案选项（如 git filter-repo、subtree split），对比它们对 git 历史保留和后续维护的影响。我选定后，阶段 1 按选定方案执行。

## 阶段 1：建立工作流

### 1.1 spec-guard 仓库：登记拆分 Proposal

1. 用 spec-guard 的 Proposal 流程登记"协作能力拆分"，并把本提示词全文保存为该 Proposal 的附件（或 `docs/collaboration-split-brief.md`，由 Proposal 引用）。
2. Proposal 至少包含以下模块：
   1. `collaboration-interface`：编写公开接口文档 `docs/collaboration-interface.md`。内容包括工具清单及输入输出、消息结构、会话状态（registered ≠ online）与投递状态（入箱 ≠ 已读 ≠ 已完成）的正式定义、投递语义声明（不承诺恰好一次，"原生接口已接收"不等于"对方已处理"）、身份规则、spec-guard 调用协作能力的唯一入口、版本策略、检测与降级（含未安装时的提示文案）、状态数据迁移方案（迁移前必须备份，不得丢数据）。每一项都分"现状"和"加固目标"两栏，现状栏以阶段 0 的基线为准。
   2. `collaboration-boundary`：把所有协作调用改为只经过唯一入口；增加边界检查，非协作代码一旦直接引用协作内部实现，检查就失败。完成后跑通全部测试和 evals，并与基线对比。
   3. `collaboration-extraction`：按阶段 0 选定的方案迁出代码，生成新插件仓库（见 1.2）。
   4. `collaboration-dependency`：删除已迁走的代码；`/spec-guard:collaboration` 保留一到两个版本的过渡期，已安装新插件则转交，未安装则提示安装方法和迁移文档；检测到旧版协作状态时引导迁移，不得静默删除；更新 README 功能表、docs/optional-features.md 和约定块。

### 1.2 新插件仓库：迁入代码并用 spec-guard 初始化

1. 由 `collaboration-extraction` 按选定方案生成 /Users/vilin/Documents/haigeerlab/<新插件名>，迁入代码和历史。
2. 迁入之后，再补充插件骨架：
   - `.claude-plugin/` 和 marketplace（Claude Code）；
   - `.codex-plugin/` 和 `.agents/plugins/marketplace.json`（Codex）。
3. 把 `docs/collaboration-interface.md` 和任务说明复制进新仓库。此后新仓库的接口文档是唯一权威版本，spec-guard 只引用它。
4. 在新仓库运行 spec-guard 的 setup-convention：先看预览，经我确认后再写入。
5. 用 /spec 编写能力图 `spec/CAPABILITY-MAP.md`，提交我评审。建议的模块和顺序如下（可根据阶段 0 的结果调整，调整处说明理由）：

   平移模块（代码已迁入，这些模块负责整理、适配、验证；验收标准是"该领域行为与基线一致"）：
   1. `acceptance-kit`：把基线验收流程整理成可复用的脚本或检查清单，供阶段 2 和阶段 4 共用，避免各写一遍、写得不一致。
   2. `mailbox-core`：信箱与 native 传输。
   3. `session-routing`：统一会话路由。
   4. `cross-host-delegation`：跨宿主会话委派。
   5. `packaging`：双端插件清单、marketplace、安装与卸载说明。
   6. `state-migration`：旧版协作状态的检测、备份与迁移。

   加固模块（平移版本通过阶段 4 第一轮后，用 /spec-guard:add-module 插入能力图，提交我逐项批准）：
   7. `test-isolation`：状态目录可以用环境变量覆盖，所有测试在隔离目录运行（先做，后续测试都依赖它）。
   8. `delivery-state-machine`：补齐 unknown 和 expired。有歧义的提交绝不自动重放；排队超时后过期、之后不再送达，超时时长可配置并给出默认值建议。被唤醒的会话会不经确认执行消息里的请求，所以这一项优先级最高。
   9. `durable-ordering`：先持久化再提交；按接收方保证顺序；各接收方互不阻塞；待投递数量有上限。
   10. `idempotency`：幂等重试 key；重复回复去重。
   11. `identity-check`：只有收件人能回复；校验发送方与宿主身份一致；身份缺失时给出明确指引。
   12. `ops-commands`：doctor、whoami、status、wait；消息正文支持从文件传入。
   13. `safe-uninstall`：修改宿主设置前先备份；补全卸载步骤；卸载默认保留消息历史。

### 1.3 全局推进顺序

两个仓库各有自己的能力图，Agent 只能看到各自的阶段提示，因此按以下全局顺序推进，每次汇报时说明当前在哪个仓库、在等哪一侧：

1. spec-guard：`collaboration-interface`
2. spec-guard：`collaboration-boundary`
3. spec-guard：`collaboration-extraction`（生成新仓库）
4. 新仓库：setup-convention 与能力图评审
5. 新仓库：平移模块 1～6
6. spec-guard：`collaboration-dependency`
7. 阶段 4 第一轮联调
8. 新仓库：加固模块 7～13
9. 阶段 4 第二轮联调

## 阶段 2：平移模块的推进与验证

- 每个模块：写 Spec → 我评审 → /plan → /build，到 MODULE_DONE 时停下汇报。
- 每个平移模块完成后都要验证：两个仓库的单元测试、边界检查、evals 全部通过，并与基线对比。任何差异都要列出来并说明原因；没有我的批准，不允许存在差异。
- 全部平移模块完成后，用 `acceptance-kit` 重跑真实宿主验收，记录 Claude Code 和 Codex 的版本号：
  - Claude Code ↔ Claude Code、Codex ↔ Codex、Claude Code ↔ Codex 双向直接回复；
  - 同一个空闲 Claude 会话被重复唤醒；
  - 双向委派创建会话、同一会话第二轮、只读权限负例、停止、精确的 mailbox 结果回传、同名会话短编号消歧。
- 准备平移版本的文档：新插件 README（解决什么问题、安装、口语用法示例、授权与安全说明、明确不做什么）、迁移文档 docs/migrations/<日期>-collaboration-split.md、两个仓库的 CHANGELOG。

## 阶段 3：加固模块的推进与验证

- 平移版本通过阶段 4 第一轮后才开始。
- 每个加固模块：补充针对该项的测试，包括故障注入场景（提交中途进程崩溃、宿主断开、超时）；用 `acceptance-kit` 重跑真实宿主验收，确认没有回退；更新 docs/collaboration-interface.md 的现状栏和 CHANGELOG。

## 阶段 4：真实项目接入联调（最终验收）

相关项目：
- 设计侧：使用 huashu-design 的设计项目，本地路径 <设计项目路径>
- 开发侧：spec-guard-plugin 项目，本地路径 /Users/vilin/Documents/haigeerlab/spec-guard-plugin

安装要求：
- 两个插件都从本地 marketplace 路径安装（尚未发布），记录安装来源和 commit。
- 拆分版 spec-guard 只装在项目级别或隔离环境中，不得覆盖引导开发用的版本。

本阶段跑两轮，都使用 `acceptance-kit`：
- **第一轮**：在平移版本上运行，跳过标记为【加固】的项目。判断标准以 docs/collaboration-interface.md 的现状栏为准。通过后才能开始阶段 3。
- **第二轮**：在加固版本上运行，覆盖全部项目，判断标准以加固目标栏为准。

开始 4.3 之前，先列出需要我手动打开哪些会话（项目 × 宿主），等我开好后再继续。

### 设计项目保护规则

- 联调期间，除测试产物外，不修改设计项目的任何文件。
- 新插件要写入设计项目的任何配置，先列出清单，经我确认后再写。
- 测试产物统一放在一个约定的临时目录中，联调结束后清理，并汇报清理结果。

### 4.1 新插件接入设计项目

在设计项目目录中，只安装新插件，不安装 spec-guard。验证：
1. 新插件在 Claude Code 和 Codex 中都能正常加载。【加固】doctor 检查全部通过。
2. 会话中没有加载任何 spec-guard 的 hook、skill 或工作流约定，CLAUDE.md / AGENTS.md 没有被写入 spec-guard 约定块。
3. 会话身份能正确识别：宿主、会话名称、项目名都正确。
4. 在同一项目内，Claude Code 和 Codex 之间可以互相发送并回复消息。

### 4.2 spec-guard 接入新插件

在 spec-guard-plugin 项目中，按隔离要求安装拆分后的 spec-guard 和新插件。验证：
1. spec-guard 的全部工作流（阶段提示、产物校验、快速插入、Proposal、事项账本等）行为与基线一致。
2. spec-guard 中涉及协作的调用全部经过唯一入口，边界检查通过。
3. `/spec-guard:collaboration` 能正确转交给新插件；临时卸载新插件后，出现正确的安装提示，工作流不受影响。
4. 如果本机存在旧版协作状态，迁移引导正确，迁移前已备份，数据无丢失。

### 4.3 跨项目会话联调

在两个项目中分别打开会话，覆盖以下宿主组合：
- spec-guard 侧 Codex ↔ 设计侧 Claude Code
- spec-guard 侧 Claude Code ↔ 设计侧 Codex
- 两侧同为 Claude Code
- 两侧同为 Codex

每个组合都要验证：
1. 口语触发：在一侧说"去 <宿主> 里找设计项目的会话，跟它联调"，能准确找到目标会话；有同名会话时能正确消歧。
2. 双向消息：发起方发出，对方收到并回复，回复回到发起方；状态流转符合接口文档（第一轮看现状栏，第二轮看加固目标栏）。
3. 真实交接：设计侧把一份设计产物（给出路径）交给 spec-guard 侧，对方能读到产物并回复确认；产物只传引用，不传内容。
4. 空闲唤醒：目标会话空闲时能被唤醒；重复唤醒同一会话正常。
5. 委派：从一侧创建另一侧项目的新会话，第二轮对话正常，停止正常。
6. 授权：未绑定唤醒的会话不会被唤醒；开着自动批准的会话无法绑定唤醒；只读权限的负例被正确拒绝。
7. 【加固】故障场景：投递过程中关闭目标会话，消息被标为 unknown 且不会自动重放；排队超时后被标为 expired，之后不会再送达；相同重试 key 不会产生重复消息。

### 判定规则

- 第二轮的 4.1、4.2、4.3 全部通过，才算最终接入成功。
- 联调中发现的问题，用 spec-guard 的事项流程记录（是否用本地事项账本，开始前先问我），修复后回到对应模块按引导处理。
- 任何一项失败：修复后从失败项所在的小节开始重跑；如果修复动了新插件或 spec-guard 的代码，4.3 要整体重跑。
- 每一项都要记录：宿主类型和版本号、项目、操作步骤、实际结果、证据（截图、日志或消息 id）。
- 联调结束后，确认引导开发用的 spec-guard 版本未被改变。
- 版本发布规则：平移版本在第一轮通过后、加固版本在第二轮通过后，才能按 release-process.md 准备发版。准备好之后等我确认，不要自行发布。

## 最终交付物

- 新插件仓库（本地，未 push），含 spec-guard 的能力图、各模块 Spec / plan / todo、acceptance-kit
- spec-guard 的拆分分支（本地，未 push），含本次 Proposal 的完整记录
- 本地备份分支 `backup/pre-collaboration-split`
- 基线记录 docs/baselines/collaboration-pre-split.md
- docs/collaboration-interface.md（含现状与加固目标）
- 迁移文档、两个仓库的 CHANGELOG
- 平移验收记录、加固验收记录
- 阶段 4 两轮接入联调记录（逐项，含宿主版本号、证据，以及最终"接入成功"的判定结论）
- 一份总结：改了什么、遗留风险、建议的发布顺序

现在从阶段 0 开始。

---

## 阶段 0 已定决策（2026-10-06）

- 新插件名：`agent-relay`
- 迁移方式：git filter-repo（按路径清单过滤并改路径，保留逐文件历史）
- 加固方向：把固定提交的上游 bridge 纳入 agent-relay 自行维护，保留 MIT 署名
- 基线：`docs/baselines/collaboration-pre-split.md`

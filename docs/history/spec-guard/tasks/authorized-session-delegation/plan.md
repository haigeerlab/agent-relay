# Plan: authorized-session-delegation

依据 [`spec/authorized-session-delegation.md`](../../spec/authorized-session-delegation.md)、
已接受的 Proposal #149 和本机宿主预检。本 Plan 与能力图、Spec 可在同一个晋级 PR
评审；本 PR 不创建真实 Claude Code/Codex 会话，也不修改全局宿主配置。任务进度以
本目录的 [`todo.md`](todo.md) 为准。

## 目标与验收口径

第一版只解决一台 Mac 上的双向委派：当前 Claude Code 或 Codex 会话可以在用户直接
提出任务后，创建另一个宿主的新会话并让它在精确项目、基线、权限和期限内工作；同一
授权信封内的后续轮次不中断询问。普通 mailbox 消息仍只是通信内容，不能授予写权限。

完成必须同时满足：

- Claude Code → Codex 与 Codex → Claude Code 都在真实宿主完成创建、自注册、首轮
  结果、第二轮继续和可核实停止；测试替身不能替代宿主证据。
- 默认是单任务授权，不是逐次确认；严格逐次、有限批次和会话生命周期是可选范围。
- 用户可看到带 `[Claude Code]` / `[Codex]` 标签的已加入列表、项目、真实可用状态和
  未读信息，但看不到完整内部 ID、私有路径或令牌。
- 不修改全局 Claude/Codex 配置，不传 `--model`，不恢复旧 tracker/parallel bridge，
  不暴露隐藏 worker、review 或 orchestration 工具，不改变 A10 的 native/XATS 转正门槛。

## 架构决策

### 控制面与消息面分离

- **授权与控制面**保存任务信封并调用目标宿主的正式创建、继续、取消接口。初始任务和
  同范围后续指令通过这个已绑定的宿主路径送达；普通自由文本 mailbox 消息不能冒充授权。
- **消息面**复用 `collaboration-messaging` 的当前已选 backend，承担加入、目录、进度、
  结果、未读和 wake 状态。新模块不切换 transport，也不把消息入队说成目标已执行。
- **本地状态**只在第一次获授权创建时初始化，使用 Python 标准库 SQLite 保存最小控制
  记录；目录为 owner-only，写入为原子事务，稳定唯一键阻止重试重复建会话。状态不写入
  项目仓库，不扫描未注册窗口，也不保存消息正文、密钥或完整诊断输出。

### 宿主不对称

- Codex 优先使用应用管理的当前受支持二进制和官方 app-server/thread API；省略 model，
  让宿主使用配置默认值。不得因为 `PATH` 中旧的 Codex 0.154.0 失败而新增模型绕过。
- Claude Code 使用其受支持的 background/session 生命周期和现有临时、无令牌 MCP 配置
  启动路径。权限映射必须由真实宿主预检证明，不能假设与 Codex 同名或等价。
- Claude 适配器优先读取并复用目标项目已有的 `.claude/settings.json` allow/deny 规则；可用
  `dontAsk` 将未预批准工具硬拒绝，使已明确允许的通信工具无需逐次弹窗。项目 trust、项目级
  MCP 首次批准和工具权限是三个独立前置条件，必须分别核对；缺少任一项时返回
  `held/prerequisite` 和最小配置建议，不自动修改项目或全局设置。
- 适配器记录实际二进制路径来源、版本、创建 primitive、实际权限和宿主 session 引用；
  对外只显示短 disambiguator。版本或协议不兼容时失败关闭，不退回标题猜测或手填 ID。

### 授权与权限

- 一句明确的“创建一个 Codex 审查当前 diff”本身就是一次 task authorization；展示非阻塞
  创建通知，不再重复确认。只有自发建议、含糊目标、扩权、跨项目、超额、超期或另一个
  后果性动作才停下来询问。
- `safe-review`、`bounded-development`、`host-native` 是产品意图；每个适配器将其收窄到
  目标宿主支持的实际设置。目标宿主只能等价或更窄，不能静默扩大。
- 第一版固定 delegation depth 为 0。batch 只允许声明的目标宿主、项目、权限、数量与
  到期时间；session-lifetime 只绑定这次创建的精确宿主会话。

## 实施顺序

```text
真实宿主可行性门槛 → 授权信封与状态机 → Codex 适配器 → Claude 适配器
→ 自然语言入口与目录 → 恢复/取消/清理 → 双向真实验收与完整回归
```

### 1. 真实宿主创建门槛（先做，失败即暂停）

在临时 Git 仓库和隔离 mailbox 中完成只读原型，不修改项目源码或用户配置：

- Claude Code → Codex：固定使用 app-managed Codex 0.160.0（或当时明确验证过的更新版），
  通过官方 app-server/SDK 能力创建指定 cwd 的线程，省略 model，证明会话可继续、能加载
  受限协作入口、精确自注册，并在第二轮仍绑定同一线程。
- Codex → Claude Code：固定记录 Claude Code 2.1.288（或当时明确验证过的更新版），通过
  background/session 接口和临时无令牌 MCP 配置创建指定项目的会话，证明可列出、继续、
  读取结果、精确自注册、第二次唤醒及安全停止。
- 分别记录会话在宿主 UI/CLI 中的真实可见性、实际 permission mode、进程退出与遗留状态；
  若任何一端只能靠标题猜测、手填内部 ID、全局配置或隐藏 bridge 工具才能完成，则形成
  no-go 记录并回到 Spec 评审，不进入任务 2。

**验收标准：**

- 两个方向各有一份脱敏的首轮、第二轮、自注册、结果和停止证据；每项标为通过、失败、
  未运行或环境不可用。
- PATH 中 Codex 0.154.0 不会被误选，未传 model，失败不被归因为账户不支持默认模型。
- 没有项目写入、全局配置写入、真实事项读取或 transport 切换。

**预计文件：**

- `tasks/authorized-session-delegation/host-creation-preflight-<date>.md`

### 2. 授权信封、私有状态与纯状态机

2026-10-03 的真实宿主门槛记录见
[`host-creation-preflight-2026-10-03.md`](host-creation-preflight-2026-10-03.md)。判决为有条件
通过并进入本任务；已确认的实现约束是：Codex 后续轮次由控制面精确 `thread/resume`，不能把
native offline wake 当成已唤醒；Claude 目标项目必须已受宿主信任，且停止后的恢复只复用保存
选项。两个适配器都要剥离对方的环境会话变量。

以红态测试固定 task/strict/batch/session 四种 horizon、三种 permission intent、项目与
baseline 绑定、depth=0、期限、撤销、剩余额度、权限降级和扩权拒绝。实现最小 SQLite
控制记录，目录与文件 owner-only，schema 只保留调度事实和宿主引用，不存 prompt 正文。

状态至少区分 `authorized`、`creating`、`created`、`registered`、`running`、`completed`、
`cancelled`、`expired`、`unknown`；任何状态都不能由更早的 mailbox 投递事实自动跃迁。

**验收标准：**

- 明确用户请求无需第二次确认；自发创建、含糊目标、超额、超期、跨项目和权限升级会返回
  精确缺失决策。
- 同一 idempotency key 在并发/重试中最多保留一个 host creation claim；owner、symlink、
  部分写入和损坏数据库失败关闭。
- 普通 mailbox 文本、friendly name 和自称 batch ID 均不能创建或扩展授权记录。

**预计文件：**

- `plugins/spec-guard/hooks/session_delegation.py`
- `plugins/spec-guard/hooks/test_session_delegation.py`

**2026-10-03 实施结果：** 18 个聚焦用例与仓库完整校验通过。已固定四种授权范围、三种
权限意图（包含 `bounded-development` 向 `safe-review` 收窄）、单跳、期限、撤销、并发启动
认领和可信证据状态迁移；owner-only SQLite 在打开前拒绝不安全目录、数据库与 sidecar，且
不保存 prompt/message body。对 mailbox、friendly name、伪 batch id、真值伪确认、跨项目、
超额和扩权均失败关闭。Task 3 可以只消费精确 envelope/claim，不再自行解释授权文本。

### 3. Codex 创建与继续适配器

在任务 1 选定的官方接口上做一个垂直切片：安全解析 app-managed current binary，执行版本
和协议预检，按 permission intent 映射 `cwd`、sandbox、approval policy，创建 thread/turn，
继续同一 thread，读取终态并停止。协议事件仅抽取必要字段，完整 event/log 不落控制库。
启动前必须用同一个 app-managed binary 枚举有效 MCP 配置，生成一次性的进程内覆盖：禁用
所有继承 server 及 Apps/plugins/browser/computer-use/multi-agent 能力，只启用所选后端的精确通信工具；
只复制禁用项的非秘密 transport identity，不复制 token/header，无法完整收紧就失败关闭。
`thread/start` 返回的精确 ID 由控制器写入初始信封并保存；后续使用 `thread/resume`，不依赖
现有 native transport 对 App Server 线程的后台唤醒。

**验收标准：**

- 假 app-server 覆盖初始化、创建、事件乱序、响应丢失、重连、继续、取消、窄化权限和不兼容
  版本；同 key 不会启动第二个 thread。
- 所有请求省略 model；测试明确拒绝 PATH 旧版被当作 app-managed current，并验证不接受比
  信封更宽的 sandbox/approval 结果。
- 只暴露 create/continue/status/cancel 所需面，不注册隐藏 worker/review/orchestration 工具。

**预计文件：**

- `plugins/spec-guard/hooks/session_delegation_codex.py`
- `plugins/spec-guard/hooks/test_session_delegation_codex.py`
- `plugins/spec-guard/hooks/session_delegation.py`

**2026-10-04 实施结果：** 20 个 Codex 适配器聚焦用例与仓库完整校验通过。适配器只解析
app-managed `current`，拒绝 PATH 旧版，使用同一 0.160.0 二进制读取有效 MCP 清单；真实只读
复查发现并修正了清单中相对 `cwd` 的兼容边界，最终读取 10 个继承项并全部生成禁用覆盖。委派服务自身
按后端使用不同目录：native 是十个 `bridge_*`，XATS 是七个真实的注册、收发、目录与投递状态工具；
测试拒绝把 `ask_codex` 或 review/orchestration 工具混入任一目录。
线程创建、精确绑定、乱序事件、响应丢失、重连继续、状态、取消、独立工作树、有效权限及
工具目录均失败关闭；请求不传 model，也不注册 worker/review/orchestration 面。Codex 离线线程
仍由控制器通过精确 `thread/resume` 恢复，不宣称 native mailbox 自动唤醒。

### 4. Claude Code 创建与继续适配器

在现有 `collaboration_claude.py` 的临时无令牌配置和参数过滤基础上，添加受管 background
session 路径；解析真实 session identity，按 permission intent 选择已验证的最窄宿主模式，
支持 logs/status/continue/stop。不得放宽现有 `--mcp-config`、token 和隐藏工具限制。
启动时剥离继承的 Codex session 环境变量。未受 Claude Code 信任的项目返回 held/prerequisite，
不得代替用户接受信任。活跃 background 会话优先用其原生 ping；精确 stop 后只用保存选项恢复，
不得重复附加启动参数，因为宿主会据此创建副本；每次都要核对实际返回 ID。

**验收标准：**

- 假 CLI 覆盖 background 创建、响应丢失、列表对账、第二轮、busy、退出、停止失败和重试；
  不从标题、进程列表或同项目候选中猜 identity。
- 已预配置的项目级通信工具权限可以无提示完成两轮；缺少项目 trust、MCP 项目批准或必要
  allow 规则时分别进入可诊断的 held 状态，且适配器不会替用户写入 `.claude/settings.json`
  或接受 trust。
- `safe-review` 不可写源码；`bounded-development` 默认只在指定独立 worktree；宿主要求的人工
  prompt 会真实暴露为 held，而不是自动绕过。
- 现有无令牌环境、临时 MCP 文件权限、参数拒绝和通信工具 allowlist 回归保持通过。

**预计文件：**

- `plugins/spec-guard/hooks/session_delegation_claude.py`
- `plugins/spec-guard/hooks/test_session_delegation_claude.py`
- `plugins/spec-guard/hooks/collaboration_claude.py`
- `plugins/spec-guard/hooks/test_collaboration_runtime.py`

**2026-10-04 实施结果：** 23 个 Claude 适配器聚焦用例和 43 个既有 launcher/runtime 用例通过。
适配器复用项目 `.claude/settings.json` / `.claude/settings.local.json` 中已有的 allow/deny，默认
`dontAsk + permission-prompts none`；安全审查只要求预批准所选后端的精确通信 MCP 工具，开发会话才额外
要求编辑、写入与至少一条 Bash allow，并限定到干净独立 worktree。缺少项目 allow、trust、
MCP 项目批准或宿主人工权限时分别返回可诊断 held，不写设置也不代替用户接受信任。

真实格式探针在已受信项目创建并清理了一个无工具测试会话：Claude Code 2.1.288 的 `--bg`
会忽略调用方提供的 `--session-id` 并返回 8 位 background id；停止后若用该短 ID `--resume`
会创建副本，只有 `claude agents --json` 返回的完整 `sessionId` 才会按原 ID 唤醒并复用保存的
权限、工具与名称。因此适配器只以首轮输出中的精确短 ID 对账完整 ID，响应丢失时不按标题或
同项目候选猜测；恢复命令只传完整 `sessionId` 与新 prompt，不重放启动选项。当前仓库未预配
通信 allow，真实只读预检如实返回 `held/project-allow-rules`，未修改项目或全局 Claude 配置。
无可用的原生 active wake 时，空闲会话先用精确短 ID 停止并确认，再用完整 `sessionId` 恢复；
stop 结果不确定时不调用 resume。XATS 默认后端只读核对精确注册名和 Claude 进程 PID，不读取
消息正文或推进游标；注册证据不足时不把初始轮次升级为 completed。

### 5. 自然语言入口、非阻塞授权和已加入目录

新增用户面 skill，将“创建 Claude/Codex 审查/开发会话”“继续该会话”“取消委派”“查看已
加入会话”映射到同一控制器。更新 `collab` 只读目录展示，让每行包含宿主标签、friendly
name、项目、真实 registration/wake/stale/unread 事实；同名只给最短 disambiguator。

创建通知显示目标宿主、项目、baseline、权限 intent、数量和到期范围。task/batch/session
范围内不阻塞；strict 模式与必需升级才等待用户。entry skill 不读取未注册应用窗口。

**验收标准：**

- 入口契约测试覆盖默认 task、strict、batch、session、同名、无匹配、stale、wake-held 和
  unread；输出不含完整 UUID、PID、private path、token 或数据库位置。
- 列表严格区分 registered、wakeable、recently-active 和 online；未知事实显示未知，不靠
  会话标题补全。
- 现有普通 `collab` 读/写/回复行为不变，未授权委派请求不会创建运行时或身份。

**预计文件：**

- `plugins/spec-guard/skills/session-delegation/SKILL.md`
- `plugins/spec-guard/skills/collab/SKILL.md`
- `plugins/spec-guard/hooks/test_skill_entrypoints.py`
- `docs/optional-features.md`

**2026-10-04 实施结果：** 已新增 `session-delegation` 自然语言契约、统一的已加入目录展示规则和
9 个入口契约用例；普通 `collab` 行为保持不变。统一控制入口只接受 friendly name，对外返回脱敏 JSON，
prompt 只走 stdin，origin session 只从宿主环境读取。控制记录新增 friendly name，所选 backend 显式映射到
Codex/Claude 的单一进程内通信配置，4 个用例证明 XATS/native 不混用、invalid 不回退、不复制 token，且
XATS 注册核对只读精确身份。后续真实预检发现并修正了 native/XATS 工具名并不相同的缺口；两套目录、注册
指令和证据现分别失败关闭，隐藏 worker/review/orchestration 工具在两端都被负例拒绝。列表在空状态下不初始化目录，在已有状态下也不启动宿主或消息后端。默认 task
使用八小时安全上限；更宽 batch/session 必须由用户明确给出数量和期限。完整仓库校验通过。
只读 `permissions` 动作按当前后端返回精确 `requiredAllow`、ready/prerequisite 和候选项目设置文件，明确
`writesPerformed: false`；它不创建控制状态或修改配置。当前实际选择为 native，本项目预检返回
`held/project-allow-rules`，所需清单为十个 `mcp__spec-guard-native-collaboration__bridge_*` 规则。

### 6. 恢复、取消、到期与精确清理

为 create-before-register、结果丢失、宿主重启、held wake、超时和 origin 重启加入对账。
恢复先按 envelope/idempotency/精确 host reference 查回原会话；只有证明原会话不存在或用户
明确授权 replacement 才能新建。取消先冻结新 launch/follow-up，再请求宿主停止并报告确认。

**验收标准：**

- 故障注入覆盖每个状态边界，未知结果不会重复创建、虚报完成或丢弃 unread result。
- 到期/取消后普通 mailbox 消息不能继续受权工作；host 未确认停止时保持 truthful 状态。
- cleanup 只处理精确创建的 session/worktree/temp config；不删除用户项目、未读结果或其他
  同名会话。

**预计文件：**

- `plugins/spec-guard/hooks/session_delegation.py`
- `plugins/spec-guard/hooks/test_session_delegation.py`
- `plugins/spec-guard/hooks/session_delegation_codex.py`
- `plugins/spec-guard/hooks/session_delegation_claude.py`
- `plugins/spec-guard/hooks/test_session_delegation_recovery.py`

**2026-10-04 实施结果：** 11 个控制器恢复用例以及 Codex 20、Claude 23、状态机 21 个聚焦用例通过。
控制器先持久化唯一 launch claim 再启动宿主；重启复用 claim，unknown 不自动重建，held 重试不消耗额外
容量，到期在接触宿主前阻断，取消只命中唯一绑定。Claude 空闲二轮采用“精确 stop 确认 → 完整 sessionId
resume”，stop 不确定时保持 unknown；控制进程重启后仍只清理按 delegation id 派生的 owner-only 临时配置。
列表、状态和取消不删除消息或推进收件游标，replacement 仍只允许在证明原会话不存在或另获用户授权后实现。
`scripts/validate.sh` 已纳入恢复用例并完整通过。真实双向宿主结果仍由任务 7 单独裁决。

### 7. 双向真实验收、文档和完整回归

先安装独立、可回滚的本地候选，不替换日常插件；在临时 Git 仓库完成两条真实链路：
Claude Code 创建 Codex、Codex 创建 Claude Code。每条链路完成首轮任务、mailbox 结果、同一
授权内第二轮、busy/held 或不可达场景、取消/停止和清理。另做一次 safe-review 写入负例和
一次同名目录消歧。真实测试前若涉及安装候选、创建会话或宿主提示，按当时边界取得授权。

**验收标准：**

- 验收记录包含脱敏的宿主版本、binary provenance、实际 permission mode、项目/baseline、
  session 创建 primitive、两轮状态和 cleanup；每项结果使用通过/失败/未运行/环境不可用。
- 聚焦测试、`scripts/validate.sh`、phase、artifact、diff 检查全部通过；全绿不替代上述宿主
  证据，任一方向未通过则模块保持未完成。
- 使用文档和 changelog 只声明已证明范围；不宣称跨机器、A10 native 转正、XATS 删除、
  模型选择、自动合并发布或普通 mailbox 的高权限 wake。

**预计文件：**

- `tasks/authorized-session-delegation/live-acceptance-<date>.md`
- `docs/optional-features.md`
- `CHANGELOG.md`
- `tasks/authorized-session-delegation/plan.md`
- `tasks/authorized-session-delegation/todo.md`

**2026-10-04 部分验收：** 独立源码候选已在真实 Claude Code 2.1.288 与 app-managed Codex
0.160.0 完成双向创建、自注册、首轮、同一会话第二轮、safe-review 写入拒绝、取消和停止读回；
修复了 Claude 创建 prompt 被可变长 `--tools` 吞掉、完成态 `blocked/idle` 无法二次唤醒，以及停止后
`done/null/null` 无法读回三个兼容问题。完整证据见
[`live-acceptance-2026-10-04.md`](live-acceptance-2026-10-04.md)。任务仍保持未完成：控制器公开 JSON
不含目标回复，本次只能额外读取 Claude logs / Codex thread 取得结果；任务信封还没有可信的 origin
mailbox recipient，mailbox result 因产品入口缺失而未运行。该缺口属于本模块 Task 7，不另建能力模块。

## 检查点与停止条件

| 检查点 | 必要证据 | 失败后的动作 |
| --- | --- | --- |
| 任务 1 | 两方向真实创建、自注册、两轮继续、停止；版本与权限可追溯 | 暂停实施，修订 Spec；不做半边产品化 |
| 任务 2 | 授权/状态机/私有存储负例通过 | 不接宿主，先收紧信封和并发边界 |
| 任务 3–4 | 两个适配器的假宿主及最小真实复查通过 | 保留已通过适配器但不开放用户入口 |
| 任务 5–6 | 入口、目录、恢复、取消的契约和故障注入通过 | 不安装候选，不把未知状态写成完成 |
| 任务 7 | 双向真实验收与完整仓库回归通过 | 明确未验证项，模块保持未完成 |

## 当前晋级 PR 的验证

当前 PR 只纳入能力图、Spec、Plan 和任务清单，不把计划中的真实会话或实现用例说成已
通过。评审通过后运行：

```text
/bin/bash plugins/spec-guard/hooks/verify-artifacts.sh
/bin/bash plugins/spec-guard/hooks/phase-guard.sh
/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh
/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh
git diff --check
```

合并后从最新远端默认分支运行 Proposal promotion proof，保留 Proposal 的历史快照。不得
自行合并 main 或发布版本。

## 规划依据

- Codex 官方 App Server 文档提供 `thread/start`、`thread/resume`、`thread/fork`、
  `turn/start`、sandbox/approval 和事件流；实现优先直接使用该本地协议，避免为第一版新增
  SDK 运行时依赖。
- Codex 官方 SDK 文档确认省略 model 时使用配置默认模型，并支持本地 thread 的 start、
  continue 和 resume。
- Claude Code 官方权限文档确认项目 `.claude/settings.json` 的 allow/deny 规则可预批准工具；
  `dontAsk` 会硬拒绝未预批准工具。项目 trust 与项目级 MCP 首次批准仍是独立前置条件，不能
  由 allow 规则代替。
- 2026-10-03 本机预检：app-managed current 为 Codex 0.160.0；PATH 首命中仍是 0.154.0，
  因此实现必须校验 provenance。Claude Code 为 2.1.288，帮助信息提供 background、agents、
  attach/logs/stop、session-id/resume 和 permission-mode；这些只是能力候选，任务 1 的真实
  双向证据才决定 go/no-go。

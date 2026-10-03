# Plan: host-native-session-routing

依据 [`spec/host-native-session-routing.md`](../../spec/host-native-session-routing.md)。本 Plan 只实现
一台 Mac 上的统一会话路由：同宿主复用 Claude Code/Codex 支持的原生会话能力，跨宿主复用
Spec Guard 的现有持久 bridge。任务进度以本目录的 [`todo.md`](todo.md) 为准。

## 目标与验收口径

完成后，用户只需给出宿主、会话名称和项目描述，就能通过同一个自然语言入口发现、创建、发送、
回复、等待、查看状态或取消。系统必须展示真实 transport 和独立状态事实，并在已有授权范围内保持
连续，不为同一个任务逐条重复询问。

完成必须同时满足：

- Claude Code ↔ Claude Code 使用宿主支持的原生目录/消息能力，Codex ↔ Codex 使用 Codex App
  task/thread 能力；二者都不通过 Spec Guard 再存一份完整正文。
- Claude Code ↔ Codex 双向继续使用当前已选的持久 bridge；同宿主 fallback 只能在既有 bridge
  已就绪、两端已唯一加入且当前授权覆盖时自动执行，并展示原因。
- 三条链路均完成同一台 Mac 上的双向两轮真实验收；busy/offline、同名、权限拒绝、超时、fallback
  与精确取消的证据分别标为通过、失败、未运行或环境不可用。
- 不修改全局 Claude/Codex 配置，不传 `--model`，不读取或扫描未注册真实会话，不恢复旧 tracker
  bridge，不改变 A10 的转正门槛或删除 XATS。

## 架构决策

### 薄控制层，不重写宿主协议

- 新增无副作用的路由策略模块，只根据可信 origin/target host、当前宿主 capability 与 bridge 就绪
  事实返回 `use-native`、`use-bridge` 或 `stop`。它不接收消息正文，不读宿主私有数据库或 socket，
  也不自行执行发送。
- 新的自然语言 routing skill 是统一调度面。Claude Code 同宿主动作直接调用该宿主当前公开的
  session tools；Codex 同宿主动作直接调用 Codex App 提供的 task/thread tools。仓库内 Python
  子进程不代理这些宿主工具，也不以私有 IPC 模拟它们。
- 现有 `collab` 继续拥有 bridge 加入、收发和未读语义；`session-delegation` 继续拥有创建、授权、
  继续、状态与取消。二者把路由决策和公开状态交给同一契约，不复制第二套状态机。

### 消息 transport 与宿主 lifecycle 分离

- `transport` 只取 `host-native-claude`、`host-native-codex`、`spec-guard-bridge`，描述消息、回复、
  等待和通信状态路径。
- `create`/`cancel` 仍调用目标宿主的正式生命周期接口，并单独报告 `hostOperation`。bridge 只承载
  跨宿主消息/结果，不制造、停止或授权宿主会话。
- 公开状态保留 `dispatch`、`wake`、`receipt`、`response` 四个独立维度。适配器缺少证据时返回
  `unknown`/`unavailable`，不把 enqueue、wake、进程退出或超时升级成更强事实。

### 流畅授权与显式 fallback

- 用户直接要求联系或创建会话时，沿用 task authorization，不重复确认。batch/session 授权在既定
  数量、项目、权限和期限内连续复用。
- 同宿主原生能力不可用且两端已经唯一 bridge-joined 时，可在原授权内自动 fallback；结果必须带
  `fallbackFrom` 和稳定 `routeReason`。若需要初始化服务、改配置、加入新身份或扩权，则只问这一项。
- 原生 dispatch 结果不确定时绝不立即 fallback，避免同一正文投递两次；用原幂等键对账后再决定。

## 实施顺序

```text
宿主能力门槛 → 路由策略与状态契约 → Claude 原生切片 → Codex 原生切片
→ bridge/fallback 与目录统一 → 委派生命周期接入 → 真实验收与文档收尾
```

## Task 1：固定真实宿主能力门槛

**描述：** 在不修改用户或全局配置的前提下，读回当前 Claude Code 与 Codex App 的受支持能力，
并用隔离测试会话证明可调用边界。记录工具来源、宿主版本、可见目录字段、发送/回复/等待语义、权限
要求以及不可用状态。只使用宿主公开能力；若需要私有 IPC、标题猜测或扫描窗口，判为该路径不可用，
后续只实现诚实 fallback。

**验收标准：**

- Claude 和 Codex 各有一份脱敏能力表，明确哪些事实可证明、哪些永远只能 unknown。
- 不发送到无关真实会话；创建隔离测试会话前按现有 task authorization 发出非阻塞通知。
- 结果逐项标记通过、失败、未运行或环境不可用；环境不可用不伪装为产品失败。

**验证：**

- 人工读回记录中的版本、primitive 与实际宿主结果。
- `git diff --check`

**依赖：** 无。

**预计文件：**

- `tasks/host-native-session-routing/host-capability-preflight-2026-10-04.md`

**预计规模：** S（1 个文件）。

**2026-10-04 实施结果：** 真实门槛记录见
[`host-capability-preflight-2026-10-04.md`](host-capability-preflight-2026-10-04.md)。Claude Code
2.1.288 的两个安全模式 background 会话只开放 `ListAgents`/`SendMessage`，完成 A→B ping、B→A
reply address 回送、A 被唤醒处理和精确 stop。Codex App 管理版 0.160.0 完成 task 创建、当前会话
向目标的第二轮和 wait/read 回复；目标 task 尝试主动跨 task 发回时，宿主正确拒绝把来源转述当成
直接人类授权。因此实现必须保留 Claude peer-message 与 Codex task/turn 的不对称，不能用私有 IPC
抹平，也不能选 PATH 中 0.154.0 或增加 model 绕过。

## Task 2：路由策略与公开状态契约

**描述：** 先写红态测试，再新增标准库 Python 的纯路由模块。它接收可信 host/capability/bridge
事实并返回唯一 action、transport、route reason 与 fallback 元数据；另校验公开状态枚举。模块不接收
消息正文、不调用宿主、不初始化运行时、不持久化 transcript。命令入口通过 JSON stdin/stdout 传递，
避免把内部引用放进 argv。

**验收标准：**

- 四格路由矩阵、能力缺失、bridge ready/invalid/unavailable、两端 joined/ambiguous 全有正反用例。
- 原生结果 unknown 时停止对账，不 fallback；既有授权且 bridge 已就绪时才给出显式 fallback。
- 非法 transport、过强状态映射、额外字段和消息正文输入失败关闭。

**验证：**

- `python3 -B plugins/spec-guard/hooks/test_session_routing.py`
- 手工将一条 route 判据改坏，确认对应反例变红后恢复。

**依赖：** Task 1。

**预计文件：**

- `plugins/spec-guard/hooks/session_routing.py`
- `plugins/spec-guard/hooks/test_session_routing.py`
- `scripts/validate.sh`

**预计规模：** M（3 个文件）。

**2026-10-04 实施结果：** 新增纯标准库路由契约与 JSON stdin/stdout 入口。四格矩阵始终只返回一个
transport；同宿主 native capability unavailable 只有在当前授权、bridge ready、两端唯一 joined
同时成立时才显式 fallback。native dispatch unknown 返回 `reconcile` 而不换路。公开状态校验拒绝
非法枚举、强于 dispatch 证据的 wake/receipt/response、额外内部字段和消息正文。聚焦测试 15 项通过；
临时破坏 target joined 判据后，目标端未加入的反例按预期失败，恢复后重新全绿。

## Checkpoint A：路由基础

- Task 1–2 聚焦检查全部通过。
- 真实宿主缺失能力已转换为明确的 unavailable 路径，没有私有 IPC 替代方案。
- 路由模块对消息正文和宿主状态零副作用。

## Task 3：Claude Code 同宿主原生双向切片

**描述：** 新增统一 routing skill 的 Claude 同宿主路径：按当前 Claude Code 支持的会话目录解析唯一
目标，使用宿主原生 send/reply/wait 操作，并把宿主证据映射到公开状态。无原生能力时将事实交给路由
策略；不直接打开 per-session socket，不把正文写入 bridge，不自动注册每个 Claude 会话。

**验收标准：**

- 唯一目标完成 A→B 与 B→A 的 send/reply 契约；同名、缺失、busy/held 和权限拒绝均保守处理。
- 测试证明原生成功路径没有调用 bridge 收发指令，也没有要求内部 session ID。
- native capability 缺失只产生稳定 route reason，不触发双写或隐藏 fallback。

**验证：**

- `python3 -B plugins/spec-guard/hooks/test_session_routing_entry.py`
- Task 1 记录中的 Claude 隔离会话最小手工读回。

**依赖：** Task 2。

**预计文件：**

- `plugins/spec-guard/skills/session-routing/SKILL.md`
- `plugins/spec-guard/hooks/test_session_routing_entry.py`
- `plugins/spec-guard/skills/collab/SKILL.md`

**预计规模：** M（3 个文件）。

## Task 4：Codex 同宿主原生双向切片

**描述：** 在同一 routing skill 中加入 Codex 路径，严格使用 Codex App 暴露的 list/read/send/wait
task/thread 能力或现有受支持 app-server 生命周期。目标必须来自宿主返回的精确引用；不从标题、项目路径、
最近活动或进程猜测。发送授权遵循宿主要求：用户当前明确请求可直接执行，自发联系先询问一次。

**验收标准：**

- 唯一 task 完成 A→B 与 B→A 的 send/reply 契约；同名、隐藏/不可访问 task 与 wait timeout 保持真实。
- 响应丢失不自动重发；重试先读回同一 task/turn，无法证明时返回 unknown。
- 测试证明没有模型参数、私有状态读取、标题猜测或 bridge 正文副本。

**验证：**

- `python3 -B plugins/spec-guard/hooks/test_session_routing_entry.py`
- Task 1 记录中的 Codex 隔离 task 最小手工读回。

**依赖：** Task 2。

**预计文件：**

- `plugins/spec-guard/skills/session-routing/SKILL.md`
- `plugins/spec-guard/hooks/test_session_routing_entry.py`
- `plugins/spec-guard/skills/session-delegation/SKILL.md`

**预计规模：** M（3 个文件）。

## Task 5：跨宿主 bridge、显式 fallback 与统一目录

**描述：** 把 Claude↔Codex 强制路由到现有 `collaboration-messaging`，并让同宿主 unavailable 路径
只在既有 bridge ready/唯一加入/授权覆盖时 fallback。统一目录展示 `native-visible` 与
`bridge-joined` 来源、宿主标签和独立 liveness/wake/unread 事实；语义名称解析仍由 Agent 完成，不新增
固定别名数据库或项目拓扑。

**验收标准：**

- 两个跨宿主方向都只选择一个 bridge backend，selector invalid/unavailable 不切另一 mailbox。
- 自动 fallback 显示 `transport`、`fallbackFrom`、`routeReason`；需配置或注册时只给一个下一步。
- 目录同名消歧、不把 registered 当 online、不暴露完整 ID/PID/path/token，并且不扫描未注册窗口。

**验证：**

- `python3 -B plugins/spec-guard/hooks/test_session_routing.py`
- `python3 -B plugins/spec-guard/hooks/test_session_routing_entry.py`
- `python3 -B plugins/spec-guard/hooks/test_collab_entry.py`

**依赖：** Task 3、Task 4。

**预计文件：**

- `plugins/spec-guard/skills/session-routing/SKILL.md`
- `plugins/spec-guard/skills/collab/SKILL.md`
- `plugins/spec-guard/hooks/test_session_routing_entry.py`
- `plugins/spec-guard/hooks/test_collab_entry.py`

**预计规模：** M（4 个文件）。

## Checkpoint B：三条消息路径

- Claude 原生、Codex 原生和跨宿主 bridge 的契约测试全部通过。
- 每条路径都只有一个 dispatch，状态字段不互相冒充。
- fallback 不需要逐条确认，也不能初始化服务、改配置或扩大授权。

## Task 6：接入委派生命周期、幂等与恢复

**描述：** 让现有委派控制器调用路由契约并分别公开 `hostOperation` 与消息 `transport`。保留 Codex
精确 thread 和 Claude 精确 session 生命周期；补齐同授权后续轮次、结果 route、busy/unknown、到期、撤销
和取消对账。不得把 native 消息内容或宿主原始日志写入 delegation SQLite。

**验收标准：**

- create/cancel 始终命中精确宿主引用，bridge 不制造或终止会话；公开结果不再混淆生命周期和消息路径。
- 同一 idempotency key/turn 在响应丢失、timeout、进程重启和 late receipt 下不重复创建或投递。
- task/batch/session 范围内继续不中断；扩项目、扩权、超额、过期和 consequential action 仍停止。

**验证：**

- `python3 -B plugins/spec-guard/hooks/test_session_delegation_recovery.py`
- `python3 -B plugins/spec-guard/hooks/test_session_delegation_backend.py`
- `python3 -B plugins/spec-guard/hooks/test_skill_entrypoints.py`

**依赖：** Task 5。

**预计文件：**

- `plugins/spec-guard/hooks/session_delegation_control.py`
- `plugins/spec-guard/hooks/session_delegation_backend.py`
- `plugins/spec-guard/hooks/test_session_delegation_recovery.py`
- `plugins/spec-guard/hooks/test_session_delegation_backend.py`
- `plugins/spec-guard/hooks/test_skill_entrypoints.py`

**预计规模：** M（5 个文件）。

## Task 7：真实双向验收、文档和完整回归

**描述：** 用可回滚候选和隔离测试会话完成三条链路的同机双向两轮验收，再覆盖 busy/offline、同名、
权限拒绝、fallback、response loss 与精确取消。更新用户文档和 changelog，只声明实际证明的范围。
真实验收前若需要安装候选、创建额外会话或处理宿主权限，按现有授权边界给出具体通知或取得授权。

**验收标准：**

- 三条链路各有版本、primitive、两轮双向状态与 cleanup 证据；测试全绿不能替代宿主结果。
- 同宿主原生成功时 bridge 中不存在重复正文；fallback 案例证明只投递一次并显示原因。
- A10 的两版本/两主机/upstream revision/无开放 P1/P2 门槛原样保留，XATS 未删除、未宣称跨机器。

**验证：**

- 所有新增聚焦测试。
- `/bin/bash scripts/validate.sh`
- `/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh`
- `/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh`
- `git diff --check`

**依赖：** Task 6。

**预计文件：**

- `tasks/host-native-session-routing/live-acceptance-2026-10-04.md`
- `docs/optional-features.md`
- `CHANGELOG.md`
- `tasks/host-native-session-routing/plan.md`
- `tasks/host-native-session-routing/todo.md`

**预计规模：** M（5 个文件）。

## Checkpoint C：完成

- todo 全部有对应代码、测试或真实宿主证据，不以“零任务”判完成。
- 新检查的正反用例均真实运行，失败路径可观察。
- 完整仓库回归通过，未验证宿主边界仍明确标记。
- 分支只包含本模块改动，准备独立 PR；不自行合并或发布。

## 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Claude 或 Codex 当前版本未暴露预期 native tool | 高 | Task 1 先做门槛；标为 unavailable，使用受约束 fallback，不接私有 IPC |
| 同名会话或 stale 引用导致误投 | 高 | 只使用宿主目录返回的精确引用；多匹配必须最小消歧 |
| primary 响应丢失后 fallback 造成双发 | 高 | unknown 时停止并以同一幂等键对账，证明未接受前不换路 |
| skill、控制器与 bridge 各自解释状态导致漂移 | 中 | `session_routing.py` 固定 transport/action/schema；入口契约测试同时覆盖两个 skill |
| “native”一词被误解为 A10 transport 转正 | 中 | 公开名称固定为 `host-native-*`；文档与测试明确 A10/XATS 不变 |
| 全绿但未真正调用宿主 | 高 | Task 1 与 Task 7 单列真实宿主证据，结果使用四态报告 |

## 开放问题

无。若 Task 1 发现某个宿主缺少受支持的必要 primitive，该路径按 Spec 记录为环境不可用并进入受约束
fallback，不以私有接口补齐，也不阻止其他已证明路径继续实现。

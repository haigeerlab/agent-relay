# host-native-session-routing live acceptance — 2026-10-04

本记录裁决 `host-native-session-routing` 的同机真实宿主范围。候选基线是当时最新的
`origin/main` `7e32ca798e15`，验收直接运行本分支源码与宿主公开能力；没有替换日常安装、修改
Claude/Codex 全局配置、传 Codex `--model`、扫描真实 Local 账本或切换协作后端。完整
session/thread ID 不写入记录。

## 环境与证据口径

| 项目 | 实际证据 | 结果 |
| --- | --- | --- |
| Claude Code | `claude --version` → `2.1.288 (Claude Code)` | 通过 |
| Codex App | app-managed `current/codex --version` → `codex-cli 0.160.0`；PATH 旧版不参与验收 | 通过 |
| 当前 bridge | `collaboration_backend.py` → `{"backend":"native"}` | 通过 |
| 路由候选 | `session_routing.py select` 在 native unavailable、授权有效、bridge ready、两端唯一 joined 时返回 `transport=spec-guard-bridge`、`fallbackFrom=host-native-claude`、`routeReason=native-capability-unavailable` | 通过 |
| A10 边界 | 本记录只有一台 Mac、Claude 2.1.288、Codex 0.160.0，未执行第二版本、第二主机或上游 revision 升级验收 | 条件未触发 |

测试结果只证明代码契约；下文另列宿主实际结果。`delivered`、wake、ack 和 reply 仍是不同事实，
没有用模型回显或测试全绿代替宿主证据。

## Claude Code ↔ Claude Code：host-native-claude

两个精确命名的临时 background 会话在 `--safe-mode` 下运行，只开放 `ListAgents` 和
`SendMessage`，临时 settings 只允许 cross-session inbound。bridge MCP 和插件均未加载。

| 验收项 | 实际证据 | 结果 |
| --- | --- | --- |
| A → B 首轮 | A 用 `ListAgents` 唯一解析 B 并发送 `PING_1`；B 日志中该 token 出现在初始 prompt 之外 | 通过 |
| B → A 首轮回复 | B 按来信 reply address 返回 `PONG_1`；A 日志中该 token 出现在初始 prompt 之外 | 通过 |
| B → A 第二轮主动消息 | B 再用 `ListAgents` 唯一解析 A 并发送 `PING_2`；A 在新 turn 收到 | 通过 |
| A → B 第二轮回复 | A 按 reply address 返回 `PONG_2`；B 在新 turn 收到并完成 | 通过 |
| 完成证据 | A、B 的各自完成 token 都在日志中出现两次：一次来自初始 prompt，一次来自最终回合；不再把 prompt 本身当作通过 | 通过 |
| 无 bridge 副本 | 精确四个正文 token 在当前 bridge `messages` 表中计数为 `0` | 通过 |
| 清理 | 两个精确 background 会话均 `claude stop` 成功 | 通过 |
| busy/held/refused | 当前临时 settings 固定 inbound accept；未再制造拒绝会话 | 未运行 |

这证明 Claude 同宿主路径直接复用公开的 peer directory/message/reply/wake 能力，不需要 Spec
Guard 重写 socket 或保存正文。

## Codex ↔ Codex：host-native-codex

通过 Codex App 创建一个隔离 task；prompt 明确禁止文件、命令、配置变更和子任务。当前 task 对该
精确目标启动两个连续 turn，分别用 `wait_threads` 取得完成事件和目标回复，最后将目标归档。

| 验收项 | 实际证据 | 结果 |
| --- | --- | --- |
| 首轮 | `create_thread` 后 `wait_threads` 返回 completed/idle，目标精确回复 `SG_CODEX_ROUND1_OK` | 通过 |
| 第二轮再次唤醒 | `send_message_to_thread` 发送固定 follow-up；同一 task 再次 completed/idle 并精确回复 `SG_CODEX_ROUND2_OK` | 通过 |
| 回复读取 | 两轮都由目标的普通 assistant turn 回复，来源使用 wait/read 取得；未要求目标另发跨 task 消息 | 通过 |
| 目标主动跨 task 发送 | Task 1 的隔离验证中，目标正确拒绝把另一会话转述的授权当成直接人类授权 | 环境不可用（发送 task 缺少直接人类授权） |
| 无 bridge 副本 | 两轮 token 在当前 bridge `messages` 表中计数为 `0` | 通过 |
| 清理 | 隔离 task 已按精确引用归档；未删除项目 | 通过 |

因此 Codex 的“双向”是 task/turn 语义：当前获得用户授权的发送 task 可向另一精确 task 发起 turn，
目标在该 turn 内正常回复；用户位于另一 task 并直接授权时，方向反转。它不是 Claude 的任意 peer
主动发送语义，插件不绕过这条宿主授权边界。

## Claude Code ↔ Codex：spec-guard-bridge

本模块没有改写已选 bridge 的协议或宿主适配器。两方向真实创建、同一会话第二轮、精确结果回传、
权限负例、同名消歧和取消已由同日记录
[`../authorized-session-delegation/live-acceptance-2026-10-04.md`](../authorized-session-delegation/live-acceptance-2026-10-04.md)
完成；本轮复用该宿主证据，避免为提高评级重复创建会话或写入邮箱。

| 验收项 | 实际证据 | 结果 |
| --- | --- | --- |
| Codex → Claude | 创建、首轮、同会话第二轮、safe-review 写入拒绝、精确停止均有真实宿主记录 | 通过（复用同日证据） |
| Claude → Codex | 创建、自注册、两轮继续、精确结果回传和取消均有真实宿主记录 | 通过（复用同日证据） |
| 当前候选未改变目标路径 | 路由契约把两个跨宿主方向都固定为当前 selector 的唯一 `spec-guard-bridge`；控制器保留原 backend/result route | 通过（代码与回归） |
| XATS 真实宿主 | 当前选择的是 native；未切换后端重复实机写入 | 未运行 |

## 受控 fallback

同宿主 native capability 被明确设为 unavailable，两端先以精确名称加入当前 bridge，且只开放
`bridge_register`、`bridge_send`、`bridge_wait` 等十个通信工具；`ListAgents`/`SendMessage` 未提供。

| 验收项 | 实际证据 | 结果 |
| --- | --- | --- |
| 可见路由原因 | 候选 CLI 返回 `spec-guard-bridge`、`fallbackFrom=host-native-claude` 和 `native-capability-unavailable` | 通过 |
| 双向两轮传输 | 两个隔离 Claude 前台进程保持活动；bridge 数据库中 `PING_1/PONG_1/PING_2/PONG_2` 各恰好一条 | 通过 |
| receipt | 四条消息均有精确 acknowledgement，共 `4` 条 | 通过 |
| 无 native 双写 | 会话没有 `ListAgents`/`SendMessage`；每个逻辑正文在唯一 bridge thread 中只出现一次 | 通过 |
| 后台 fallback wake | Claude 2.1.288 的一次隔离 `--background` 探针没有挂载命令行临时 MCP，真实日志报告 `bridge_register` 不可用；探针已停止 | 环境不可用 |
| 清理 | 三个实际注册的 `sg-fallback-*` 测试身份均通过 `bridge_retire` 精确退休；读回均为 retired | 通过 |

前台回退证明 transport、双向两轮、确认和无双写；它不冒充后台 wake 通过。后台探针失败只说明本次
临时宿主挂载条件不可用，不推翻同日跨宿主真实 bridge 证据，也不授权修改全局 Claude 配置。

## 负例与覆盖对账

| 场景 | 证据 | 结果 |
| --- | --- | --- |
| 同名目标 | 入口契约拒绝多匹配；同日委派验收用两个真实同名 Codex task 验证短编号消歧 | 通过 |
| 权限拒绝 | Codex 反向主动发送缺少直接人类授权时被宿主拒绝；Claude safe-review 写入负例已有真实记录 | 通过 |
| response loss | route/controller 测试确认 unknown 只 reconcile，不重发、不 fallback | 通过（代码契约） |
| busy | 同日真实委派创建/继续出现 `busy` 后对账到同一会话 | 通过（复用同日证据） |
| offline/held | 状态映射与停止路径有测试；本轮未制造离线真实会话 | 未运行 |
| 精确取消 | 同日两宿主委派验收均按精确引用 cancel/status 读回 | 通过（复用同日证据） |

## 判决

`host-native-session-routing` 的第一阶段同机范围通过：Claude 同宿主复用 Claude 原生双向消息，
Codex 同宿主复用 task/turn + wait/read，Claude↔Codex 复用当前唯一 bridge；受控 fallback 只在授权、
bridge ready 与两端唯一 joined 同时成立时选择，且不双写正文。

以下边界继续保留：Codex 目标 task 主动跨 task 发送需要该发送 task 的直接人类授权；Claude 临时
background fallback MCP 挂载本轮环境不可用；XATS 没有重复实机验收；不声明跨机器。本结论不推进
A10。A10 的连续两版本、至少两主机、上游 revision 升级后唤醒仍有效、无开放 P1/P2 四项门槛仍须
由独立 Proposal 和新鲜证据满足，XATS 继续保留。

## 仓库校验

| 校验 | 结果 |
| --- | --- |
| `test_session_routing.py` | 通过（16 tests） |
| `test_session_routing_entry.py` | 通过（19 tests） |
| `test_collab_entry.py` | 通过（14 tests） |
| `unittest discover -p 'test_session_delegation*.py'` | 通过（94 tests） |
| `test_skill_entrypoints.py` | 通过（11 tests） |
| `/bin/bash scripts/validate.sh` | 通过 |
| `/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh` | 通过（80 cases） |
| `/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh` | 通过（19 cases） |
| `git diff --check` | 通过 |

完整校验全绿只证明源码、文档和仓库契约；它不替代上面的真实宿主结果，也不改变列为未运行、
环境不可用或条件未触发的边界。

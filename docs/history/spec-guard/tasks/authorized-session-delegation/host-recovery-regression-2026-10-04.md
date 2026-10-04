# authorized-session-delegation host recovery regression — 2026-10-04

本记录补充同日真实宿主验收后的两项兼容性修复，不改写
[`live-acceptance-2026-10-04.md`](live-acceptance-2026-10-04.md) 的历史时点事实。两项修复均属于
现有 `authorized-session-delegation` 模块的恢复与取消契约，不新增能力模块、Spec、Plan 或能力图。

## 发现与修复

| 场景 | 实际问题 | 修复后的裁决 | 验证 |
| --- | --- | --- | --- |
| Claude Code 空闲会话恢复 | 精确 stop/resume 成功后，background 元数据仍可能短暂处于不完整状态；恢复确认只读一次会把同一会话误报为 `background-entry-invalid` | 创建绑定和恢复确认共用只针对精确短 ID 的有限重试；持续无效时返回 `unknown`，不重复 resume、不创建替代会话 | 回归先复现单次读取失败，再证明第二次读取绑定原完整 session；完整 Claude 适配器用例通过 |
| Codex Desktop 已接管的 thread | 控制面 `thread/resume`、`turn/interrupt` 或 `thread/archive` 可能被宿主明确拒绝；旧实现会把脱敏不足的协议异常直接抛给入口 | follow-up 返回 `held / host-request-rejected` 并保留原完成 claim；取消先冻结授权，再返回 `unknown / host-request-rejected`，不虚报中断或归档成功 | 回归覆盖 follow-up 和 cancel 拒绝；JSON-RPC 用例证明只保留标准整数 code，非整数降为 `unknown`，不暴露宿主 message/data |

这里的 Codex 修复不把 `notLoaded` 当作可唤醒成功，也不改变 Codex Desktop 自身的 thread 所有权。
它只把宿主拒绝转成可诊断、可恢复且不虚报成功的结果。真实 Desktop 空闲唤醒仍由发布后宿主验收单独证明。

## 边界与 A10

- 没有修改全局 Claude/Codex 配置、消息后端、模型选择或宿主权限。
- 没有清理既有 native 身份、未确认消息或其他用户会话。
- 这次回归修复不是一次新的 A10 发布轮次，也没有执行被既有未确认消息阻断的 rollback rehearsal。
- 因此 v0.39.0 的 A10 连续发布计数仍为 `0/2`，XATS 继续作为默认后备传输层。

## 校验

| 命令 | 结果 |
| --- | --- |
| Claude 聚焦回归 | 通过（新增 1 个恢复确认用例） |
| Codex 聚焦回归 | 通过（新增 4 个拒绝与脱敏用例） |
| `python3 -m unittest discover -s plugins/spec-guard/hooks -p 'test_session_delegation*.py'` | 通过（98 tests） |

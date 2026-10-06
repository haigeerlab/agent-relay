<!-- BEGIN:spec-guard-codex-convention -->
## Spec Guard 项目约定

> 由 `setup-convention local --host=codex` 生成。

- 能力图：`spec/CAPABILITY-MAP.md`；模块 spec：`spec/<module-id>.md`
- 每个模块隔离使用 `tasks/<module-id>/plan.md` 和 `tasks/<module-id>/todo.md`
- 活跃模块在 `.agent/state.json` 的 `activeModule`；不要共用 `tasks/plan.md`
- 若项目已启用 Local 事项账本，确认要实现的需求或修复在动代码前先用 `spec-guard:ticket`
  查重并取得事项 ID；探索和无需追踪的小操作例外
- 项目级审查按 `spec-guard:spec-guard-ops` 的共享检查点规则限定批次、收束发现并交接缺陷；
  审查完成后的“继续”推进已预告的问题处理步骤，不重新泛扫
- 明确选用 GitHub/GitLab 普通 Issue 时，用 `spec-guard:hosted-ticket-workflow` 逐项查重、授权写入与交付对账；
  Local 事项仍走 `spec-guard:ticket`，不凭 Git remote 改目标
- 阶段交接或停止时，加载 `spec-guard:spec-guard-ops` 的共享检查点规则，预告已授权下一步。
- Plan 的检查点标 `gate`（停下等确认）或 `report`（记入 todo 后继续），未标注按 `gate`；按需求批量前置审与
  UI 自验按 `spec-guard:spec-guard-ops` 的共享检查点规则
<!-- END:spec-guard-codex-convention -->

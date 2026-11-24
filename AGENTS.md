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

<!-- shared:begin -->
## 提交与 PR 的语言

本项目的提交信息、PR 标题和 PR 描述一律用中文，不能是全英文。

- 用中文写清楚改了什么、为什么改。
- 文件路径、命令、代码标识符（函数名、变量名、配置项）和 `fix:`、`feat:`、`docs:`、`chore:` 这类前缀保持原样，不翻译。
- 末尾自动附加的署名行（如 `Co-Authored-By`、`Signed-off-by`）保持原样。
- 代码和代码注释仍按仓库原有语言，不因为这条规则改动。
- 已有的英文提交历史不改。
- 例外：给不归本团队的外部开源项目提 PR 时，跟随对方仓库的语言；这种情况要先问用户。

## autopr（自动维护）

`CLAUDE.md` 与 `AGENTS.md` 的本节逐字一致，两处一起改；改本节的“先问”边界要先问用户。

- 检查入口：`bash scripts/validate.sh`（先在 `plugins/agent-relay/bridge` 里 `npm ci`）。它与 `.github/autopr/interface.yml` 的 `check.run`、CI 的 Validate 步骤是同一个命令。
- 先问：合并 PR、推送 `main`、打 tag、建 Release 或发版（见 `RELEASING.md`）、改 `.github/`（CI、autopr 登记文件、准入与降级 workflow）、改分支保护或规则集、改 `scripts/ci_scope.py` 的豁免名单、改本节的“先问”边界，一律先问用户，拿到明确同意再做。
- autopr 例外：agent 身份可以在 `autopr/*` 分支上提交、推送并开 PR，不用逐次先问；合并 PR、`main`、tag、发版仍然先问。
- 合并方式（插件开发规范 F3）：开完 PR 就问用户“PR #N 已开，CI 正在跑，可以合并吗”，不等 CI 跑完再问，也不用后台 `gh pr checks --watch`、定时或循环等任何办法自己等 CI。用户在对话里回“合并”后，会话先看 PR 状态：必需检查已全部通过（`mergeStateStatus` 为 `CLEAN`）时直接执行 `gh pr merge --merge`；检查还没跑完时执行 `gh pr merge --auto --merge`，由 GitHub 等 `CI required` 通过后合并，CI 不过就不合（`CLEAN` 时 `--auto` 会被 GitHub 拒绝）。同时为这个 PR 打开桌面版的 Auto-fix（Claude Code 用 `ccd_pr` 的 `set_monitor`，Codex 没有就跳过），CI 失败、冲突或评审意见会叫醒会话去修。下次被叫醒或用户下次来时，核实 PR 已合并、记下合并提交，再告诉用户；用户不用去 GitHub 点，也不用回来报“合完了”。

### 规则 ↔ 执行者

| 规则 | 执行者 |
|---|---|
| 本地检查与 CI 跑同一个入口 | `.github/workflows/ci.yml:100`（Validate 步骤直接跑 `bash scripts/validate.sh`） |
| Claude 与 Codex 两份插件清单版本一致 | `plugins/agent-relay/hooks/test_packaging.py:22` |
| CI 豁免路径不被测试读到 | `plugins/agent-relay/hooks/test_ci_exempt_guard.py:112`；名单增减是判断题，由用户定 |
| bridge 的文件都登记在 `UPSTREAM.sha256` | `plugins/agent-relay/hooks/test_bridge_vendoring.py:16` |
| Spec Guard 约定（能力图、模块 spec、tasks 隔离） | `/spec-guard:verify-artifacts` 查目录结构，手动跑，不在 CI；其余是判断题 |
| 提交与 PR 用中文 | 判断题，仓库里没有检查 |
| 先问边界与 autopr 例外 | 判断题，没有检查 |
<!-- shared:end -->

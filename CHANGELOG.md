# Changelog

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

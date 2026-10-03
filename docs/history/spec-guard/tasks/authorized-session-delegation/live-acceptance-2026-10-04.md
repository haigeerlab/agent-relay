# authorized-session-delegation live acceptance — 2026-10-04

本记录裁决任务 7 的本机真实宿主证据。候选直接从独立 worktree 的源码运行，控制状态与临时
MCP 配置位于独立私有临时目录；没有替换日常安装的 spec-guard，没有修改全局 Claude/Codex
配置，没有传 `--model`，也没有读取真实 Local 事项或切换消息后端。当前后端是 native；这不
构成 A10 native 转正，XATS 仍保留。

## 环境与候选

| 项目 | 证据 | 结果 |
| --- | --- | --- |
| 候选基线 | `origin/main` 基线 `861dce7`；真实复测包含修复提交 `c8ae174` | 通过 |
| Claude Code | `claude --version` → `2.1.288 (Claude Code)` | 通过 |
| Codex | app-managed `current` 指向 `0.160.0-aarch64-apple-darwin`；控制请求省略 model | 通过 |
| Claude 项目权限 | `permissions --project . --permission safe-review` → `backend=native`、`ready=true`、`permissionMode=dontAsk`、`writesPerformed=false` | 通过 |
| 项目设置范围 | 仅忽略的 `.claude/settings.local.json` 允许十个 native `bridge_*` 通信工具；没有 Bash/Edit/Write | 通过 |
| 候选隔离 | 每条链路使用独立 `/private/tmp` 控制状态；日常插件未替换 | 通过 |

## Codex → Claude Code

目标 `[Claude Code] accept-claude-final`，项目 `spec-guard-plugin`，baseline `3e4b442306bb`，
`safe-review/dontAsk`。

| 验收项 | 实际证据 | 结果 |
| --- | --- | --- |
| 创建与首轮投递 | 控制器返回 `created / busy`；随后 native 精确注册把状态推进为 `running` | 通过 |
| 首轮结果 | 精确会话日志含分支 `codex/authorized-session-delegation`、`ACCEPT-CLAUDE-ROUND1`、`READ_ONLY_OK` | 通过 |
| 同会话第二轮 | 对同一 friendly name 执行 `continue`，返回 `running / busy`；完成后日志同时保留 ROUND1 并新增 `ACCEPT-CLAUDE-ROUND2` | 通过 |
| 第二次唤醒兼容 | Claude 2.1.288 的完成会话实际为 `blocked/idle`；适配器经精确 stop 确认后只用完整 sessionId resume，没有复制会话 | 通过 |
| 取消与读回 | `cancel` → `cancelled`；随后 `status` → `cancelled / done` | 通过 |
| 写入负例 | 独立 `safe-review` 会话被要求创建 `safe-review-negative.tmp`；日志返回 `WRITE_DENIED_OK`，文件持续不存在，随后 `cancelled / done` | 通过 |

真实复测发现并修复三个 Claude 2.1.288 兼容问题：

1. `--tools` 是可变长 CLI 参数，prompt 必须置于 `--` 之后，否则会被吞成工具名，后台会话只停在
   `blocked/idle`；
2. 首轮完成后的真实 `blocked/idle` 是可安全继续的空闲状态；
3. 精确 stop 后的条目可能是 `state=done,status=null,pid=null`，应规范化为 `hostStatus=done`。

最初在 Codex 文件沙箱内启动 Claude background 时出现 `EPERM`（Claude 需要写自己的
`~/.claude/jobs`）；在用户已授权的真实宿主权限下重跑后通过。这是验收环境权限，不是项目
allow 缺失，也没有使用 bypass。

## Claude Code → Codex

真实 Claude origin 只获准执行固定临时 wrapper，由它调用控制器创建
`[Codex] accept-codex-final`。目标项目 `spec-guard-plugin`，baseline `c8ae1745c785`，
`safe-review`。

| 验收项 | 实际证据 | 结果 |
| --- | --- | --- |
| 创建、自注册、首轮终态 | Claude origin 收到控制器公开 JSON：`completed`；native 注册由 Codex app-server 事件核实 | 通过 |
| 首轮结果 | 精确 Codex thread 含 `ACCEPT-CODEX-ROUND1`、`READ_ONLY_OK`、分支和短 baseline | 通过 |
| 同会话第二轮 | 同一 Claude origin 调用 `continue`；同一 thread 同时保留 ROUND1 并新增 `ACCEPT-CODEX-ROUND2` | 通过 |
| 取消与读回 | 同一 Claude origin 调用 `cancel` → `cancelled`；同权限宿主读回 `cancelled / notLoaded` | 通过 |
| 默认模型 | 请求未携带 model；没有使用 PATH 中旧版 Codex，也没有新增 `--model` 绕过 | 通过 |

取消后的第一次附加 `status` 从 Codex 文件沙箱运行，app-server 初始化超时并返回
`protocol-result-unknown`；同一只读命令在与创建/取消一致的宿主权限下返回
`cancelled / notLoaded`。前者记为环境不可用，不作为目标 thread 失败。

## 契约与未完成项

| 验收项 | 证据 | 结果 |
| --- | --- | --- |
| 同名消歧 | `test_session_delegation_recovery.py::test_same_name_lists_short_disambiguators_and_never_guesses` | 通过（测试）；真实双会话未重复创建 |
| 控制器公开结果 | create/continue 公开 JSON 只有状态，不含目标的回复正文；本次必须额外读取 Claude logs / Codex thread 才取得标记 | 失败 |
| mailbox 结果回传 | 两端都完成精确注册，但当前任务信封没有可信的 origin mailbox recipient，也没有自动把最终回复送回 origin | 未运行（产品入口缺失） |

因此任务 7 **保持未完成**。双向创建、两轮继续、权限负例和精确停止已经有真实证据，但“一句话
委派后结果自动回到发起方”尚未成立。最小后续工作属于本模块原 Plan，不需要新建能力模块：先明确
受控 return recipient／结果 provenance 契约，再用测试实现，最后重跑两端 mailbox result 与真实同名
目录验收。在此之前不得把本模块或 A10 native 宣布为完成，也不得删除 XATS。

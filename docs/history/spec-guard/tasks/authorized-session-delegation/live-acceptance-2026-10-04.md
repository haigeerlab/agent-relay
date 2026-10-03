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

## 精确结果回传与同名消歧

| 验收项 | 证据 | 结果 |
| --- | --- | --- |
| Codex → Claude 最小回传 | `[Claude Code] result-claude-min` 完成后，控制器初始为 `pending`；精确 origin inbox 收到来自该目标的单条结果，thread 使用本轮独立 route，随后目标 `cancelled` | 通过 |
| Claude → Codex 最小回传 | 固定 Claude origin wrapper 创建 `[Codex] result-codex-min`；公开 JSON 为 `completed / enqueued / RESULT-CODEX-MIN-OK`，Claude origin 精确 inbox 实到并确认，随后目标 `cancelled` | 通过 |
| 控制器公开结果 | Codex 同步最终回复只取 app-server `final_text`，脱敏内部 ID、控制字符和绝对私有路径；不再从 Claude 原始日志补正文 | 通过（测试＋Codex 真实宿主） |
| 同名消歧 | 隔离状态中创建两个 `[Codex] 同名验收`；`list` 返回两个不同 6 位短编号，不带编号的 `status` 返回 `session-name-ambiguous`，按各自 `--disambiguator` 均精确 `cancelled` | 通过 |
| 结果消息清理 | 当前 Codex origin 收到的最小回传和同名验收消息均按精确 message id 确认；未扫描其他会话或推进未知游标 | 通过 |
| XATS 结果回传 | 单元测试覆盖精确 agent type、delivery kind/payload、team、sender/recipient/subject；本次真实后端为 native，未切换后端重复实机写入 | 未运行（当前后端未选择 XATS） |

Codex → Claude 的第一次结果回传使用了范围过大的代码审查 prompt，目标运行超过验收等待窗口后被精确
中断并取消；该次记为**失败（任务规模超时）**，不作为通讯链路失败，也不拿它替代后续最小回传证据。
这次执行同时暴露并修复了 Claude background 元数据短暂未落盘时过早报
`background-entry-invalid` 的问题：适配器只对精确短 ID 做有限重试；持续无效时保留精确 host reference 并
报告 `unknown`，不重建会话。

结果回传只接受 `origin session → 唯一注册身份`。零个或多个匹配均返回
`recipient-unavailable`，不会按标题、项目、最近活动或用户输入的名字猜收件人。每轮 route 独立，控制器只读
核对 sender/recipient/thread 或 subject 元数据，不读取消息正文、不推进 inbox 游标；普通 mailbox 消息仍不
授予开发权限。

因此任务 7 的本机验收完成。这个结论只覆盖当前源码候选、同一台 Mac、已选择的 native 后端，以及表中列出的
Claude Code/Codex 版本；不构成插件发布、XATS 实机结果回传、跨机器能力或 A10 native 转正。A10 的“两版本、
两主机、上游 revision 升级、无开放 P1/P2”门槛保持不变，XATS 继续保留。

## 收尾校验

| 校验 | 结果 |
| --- | --- |
| `python3 -m unittest discover -s plugins/spec-guard/hooks -p 'test_session_delegation*.py'` | 通过（91 tests） |
| `/bin/bash scripts/validate.sh` | 通过 |
| `/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh` | 通过（80 cases） |
| `/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh` | 通过（19 cases） |
| `git diff --check` | 通过 |

测试全绿只证明源码与仓库契约；双向宿主结果和 XATS 未运行边界仍以本记录上表单独裁决。

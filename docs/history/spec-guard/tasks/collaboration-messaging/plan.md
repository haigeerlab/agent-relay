# Plan: collaboration-messaging

Design: `docs/research/2026-09-17-agent-collaboration-design.md`

Local Proposal candidate: `spec/proposals/collaboration-messaging.md`. It has passed local
contract validation against the current remote-main baseline, but has not been published,
reviewed, or accepted; this plan must not represent it as a completed tracker stage.

## Overview

交付一个可选、同机的 Spec Guard 协作消息能力。它让不同 Claude Code/Codex 任务在一个本地通讯录中
交换自由文本消息与可选引用，不负责 Ticket、Git 或 tracker 写入。本地 Ticket 账本另立模块，不能借此
计划偷偷扩大范围。

## Architecture decisions

- 使用已验证的 XATS 作为锁版本的本机消息运行时；Spec Guard 负责安装检查、私有配置、生命周期和
  宿主适配，不 fork 或重写传输协议。
- ChatGPT in Chrome 是 Codex Desktop 的硬约束：当前只支持原生邮箱模式，不启用隔离
  `CODEX_HOME`、Desktop 受管 app-server 或主动唤醒链路。
- 协作面是同机 Agent 通讯录。会话身份用于投递；项目路径、当前工作、角色和模型只用于自我介绍与
  人／Agent 的自然判断，绝不参与自动路由。
- 消息正文自由；`kind`、Ticket、Issue、commit、branch、验证命令均为可选引用，不能触发写入。
- 所有 token 只经用户私有文件／环境传递。项目文件、插件 manifest、日志和 argv 禁止出现 token。
- 第一阶段仅支持同一台 Mac 的 loopback 服务。跨机器模式必须新建安全设计和验收。

## Implementation slices

### Slice 1: Fixed runtime contract and private configuration

**Acceptance criteria:** 明确锁定 XATS 版本与校验来源；实现用户级运行时目录、私有 token 文件、启动／
健康检查／停止诊断。拒绝非 loopback bind、缺失或权限过宽的 token 文件。

**Verification:** 夹具证明版本固定、token 不出现在 stdout/stderr/argv，未认证请求被拒绝；重启后健康
检查给出准确状态。

**Likely files:** 新增受管 runtime helper、配置 schema、聚焦测试、安装／安全参考文档。

**Dependencies:** None.

**Status (2026-09-17):** In progress. `collaboration_runtime.py` pins
`cross-agent-teams-mcp@0.8.6`, creates a fresh private loopback configuration only by explicit
`init`, and starts the daemon with a child-only environment token. Focused fixtures cover
absent/valid/unsafe modes, symlink rejection, initialization, and command secrecy. Stop/restart
recovery remains intentionally unimplemented.

### Slice 2: Narrow Claude Code and Codex transport adapters

**Acceptance criteria:** 两个宿主均能通过各自最小的 MCP 接入注册当前任务、发送消息、读取收件箱和确认已读；
适配器不泄漏 token，也不提供 Git/Issue/Ticket 写工具。Codex 使用官方 `http_headers_helper` 从私有文件
动态取得请求头；Claude Code 由受管启动包装器临时注入环境变量，绝不把 token 固化进 `.mcp.json`。

**Verification:** 协议夹具覆盖无效输入、过期注册、守护进程重启和未知收件人；在真实 Claude Code 与真实
Codex 各完成一次单项目双向投递。

**Likely files:** 适配器、MCP 定义、宿主配置生成器、测试。

**Dependencies:** Slice 1.

**Status (2026-09-17):** 已实现并在真实当前用户 LaunchAgent 验证：服务以无 secret plist 启动固定版
XATS，`service-status` 与宿主域 `/health` 均确认 running。实现同时覆盖 launchd 默认 PATH 缺少 nvm Node
以及因测试环境回收造成的 stale PID 文件恢复。Claude 仍需通过受管包装器启动新会话后注册；这不是后台服务
可替代的步骤。

#### Slice 4b: Claude 的普通用户级接入

**Acceptance criteria:** 用户明确选择后，未来 Claude Code 会话可按普通方式启动并加载协作 MCP；用户配置、
项目文件、日志和进程 argv 不得含 token，且不能影响正在运行的会话或 Codex Desktop 的 Chrome 能力。

**Verification:** 夹具证明 `claude mcp add --scope user` 只写无 secret stdio helper 参数、同名配置拒绝覆盖；
bridge 固定开源 MIT `mcp-remote@0.1.38`，将 bearer token 仅传入子进程环境。

**Status (2026-09-17):** 已在当前用户明确授权后安装并真实验证。`collaboration_claude_stdio.py` 以固定版
`mcp-remote` 桥接 Claude stdio 与本机 XATS HTTP endpoint；`install-claude` 通过 Claude 的 user-scope
配置命令写入无 secret 条目。一个未使用包装器的新 Claude Code 会话已成功注册并注销临时身份；现有 Claude
会话仍须重启。`collaboration_claude.py` 保留用于一次性诊断／验证。

随后以单一持续连接的普通 Claude Code 会话和原生 Codex Desktop 完成了真实双向邮箱验证：Claude 注册、
Codex 投递、Claude 读取并回信、Codex 实际读取回信、双方注销。短命 `claude -p --continue` 会另建 MCP
连接，不能假设自动继承已注册工具会话；Claude 注册应在可用时携带由当前会话 `$PPID` 取得的 `ui_pid`，
持续的 Desktop 会话不受该 CLI 测试边界影响。

针对断连且无法自行注销的测试身份，已复用 XATS 的精确 `DELETE /api/agents/<agent_id>` registry API，提供
显式 `remove-agent --agent-id <UUID>`。它只删除已由用户确认的单条身份行，不能按名字猜测、不能杀进程或
改写消息；实现与夹具覆盖 UUID 校验、上游确认和 token 不进入命令输出。

**Status (2026-09-17):** 核心邮箱链路已完成：Codex 的无 secret 用户级 MCP 配置通过
`http_headers_helper` 动态读取私有 token；Claude 使用临时配置与受管环境启动。真实 Claude Code 与
原生 Codex Desktop 已分别完成注册、收件箱读取和双向持久投递；原生 Desktop 以
`custom/codex-desktop-native` 降级为邮箱式收发，以保留 ChatGPT in Chrome。过期注册、守护进程
重启与恢复边界仍留给 Slice 5 验收。

### Slice 3: Self-description and direct session discovery

**Acceptance criteria:** 任务注册唯一会话身份、可读名字、当前项目路径和可选当前工作／角色；通讯录显示这些
事实。任何可见会话都可直接投递，插件不推断项目关系或按角色自动路由。

**Verification:** 夹具和本机集成测试覆盖同／不同项目、同名显示名、会话重启、过期会话和自由文本工作描述；
确认项目路径只影响展示，绝不阻止消息。

**Likely files:** 注册包装、通讯录展示、命令／参考文档、测试。

**Dependencies:** Slice 2.

**Status (2026-09-17):** 基础能力已完成。XATS 的注册与通讯录直接展示自由的名称、项目路径和角色；
固定技术 namespace 不表达项目层级。此前的 `group/project/task` 地址编码已在评审后移除，因为它会把
正常协作过度建模为项目层级。会话重启、陈旧注册与同名边界仍留给 Slice 5 验收。

### Checkpoint: 通信桥梁可安全试用

- 同机 runtime 与两类宿主的原生 MCP 连接路径均已实证；产品层没有 group 隔离或项目路由概念。
- 消息只产生运行时数据，不写仓库或远端 tracker。
- 故障、未确认投递和歧义都有准确可操作诊断。

### Slice 4: Minimal Spec Guard operator experience

**Acceptance criteria:** 提供 start、register、status 和诊断入口；其输出区分“运行时未启动、目标未知、
任务离线、消息未确认、可投递”。命令不自动注册其他项目的 Agent。

**Verification:** 命令快照、错误路径和权限测试；真实两个项目的 Claude↔Codex 联调闭环记录。

**Likely files:** commands、hooks/CLI helpers、references、adapter tests、README。

**Dependencies:** Slices 1–3.

#### Slice 4a: Explicit per-user background service

**Acceptance criteria:** 用户明确调用 `service-enable` 后，插件只在当前用户的
`~/Library/LaunchAgents/` 创建受管 plist，并由 launchd 维持固定版 XATS。plist、启动参数、日志和诊断
不得含 token；未知同名 plist 必须拒绝覆盖。`service-status` 需区分未启用、路径陈旧、服务未加载和健康服务；
`service-disable` 仅删除已验证受管服务。

**Verification:** 小型单元测试覆盖 plist 结构、私有日志权限、token 不泄露、未知 plist 拒绝覆盖及
bootstrap／bootout 命令构造；在真实用户终端完成 enable → health → disable 的人工验收。不得把受控测试
环境回收后台子进程误判为 LaunchAgent 失败。

**Likely files:** `collaboration_runtime.py`、`test_collaboration_runtime.py`、协作命令与运行时参考文档。

**Dependencies:** Slice 1.

### Slice 5: Security and recovery review

**Acceptance criteria:** 完成 loopback、文件权限、日志脱敏、重启、遗留注册、重复消息与宿主退出的审查和回归。
将 XATS 已知测试进程悬挂现象记录为上游风险，不把未终止测试误报为完整通过。

**Verification:** 全量相关回归、`scripts/validate.sh`、真实宿主重启/重新注册场景，以及 diff 中无 secret 的检查。

**Likely files:** 安全测试、恢复文档、风险记录。

**Dependencies:** Slice 4.

## Dependency graph

```text
fixed runtime + private config
              ↓
Claude/Codex narrow adapters
              ↓
self-description + direct session discovery
              ↓
operator commands and real two-project flow
              ↓
security + recovery acceptance
```

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| 本机 token 被配置文件或日志泄露 | 使用私有用户级文件／环境注入；测试 argv 与输出；项目配置只存非秘密 ID。 |
| 同机会话的通讯录暴露过多信息 | 仅在同一 macOS 用户、loopback 和私有 token 下运行；通讯录只显示注册者自愿提交的最小简介。跨用户／跨机器另建权限设计。 |
| 把自我介绍误做成工作锁 | 当前工作与角色只是自由描述；代码写入冲突继续交给现有 worktree／Git 安全机制。 |
| 消息失败被当作已送达 | 区分 accepted、delivered、read、unknown；重试只在幂等消息 ID 下进行。 |
| 把本地 Ticket 发展成第二套 GitHub | 此模块不创建 Ticket；另立 `local-ticket-ledger` 设计并保留最小边界。 |
| 宿主 API 差异 | 每个宿主单独做真实验收；能力缺失时明确降级，不伪造支持。 |

## Current checkpoint

**Type:** 安全的同机持久邮箱已可试用。真实 Claude Code 与原生 Codex Desktop 已完成双向投递；
Codex 保留 ChatGPT in Chrome，因此当前不提供主动唤醒。

**Next implementation step:** 完成 Slice 4 的最小运维体验与 Slice 5 的重启／遗留注册／重复消息验收；
不得将原生 Codex Desktop 切换为受管 app-server 模式。

**Stop condition:** 实施中若 XATS 的固定版本、许可证、token 注入方式或 Claude/Codex 官方接入点与设计
证据不一致，停止并提交更新后的设计裁决；不得以不安全的明文项目配置作为替代。

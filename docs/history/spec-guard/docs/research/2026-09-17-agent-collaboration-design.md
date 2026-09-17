# Agent 协作通信与本地 Ticket：设计提案

状态：已确认设计方向，尚未实施。

## 决策摘要

Spec Guard 增加一个**可选的本机协作桥梁**，让 Claude Code 与 Codex 的不同任务可以在同一台
Mac 上、跨项目或同项目互发消息。它服务于自然语言协商，不充当任务调度器、权限系统或 Git
控制器。

日常 Bug 和普通需求使用一个将来独立交付的**本地 Ticket 账本**；不复用 Candidate Proposal
Pool。Proposal Pool 继续只治理独立新能力进入能力图的高约束场景。

## 问题与目标

当前 Agent 间若要联调或交接，需要用户复制粘贴消息。没有 GitHub/GitLab 时，普通 Bug／需求
又缺少可持续追踪的本地闭环。目标是使下列交流自然发生：

```text
发现流协议问题
  → 给故障注入项目的任务发消息并追问
  → 对方确认归属、修复或提出反问
  → 需要追踪时建立 Bug/需求 Ticket
  → 修复者通知 commit、分支或验证方式
  → 发起者验证并回复
```

同一项目内的主开发、Bug 修复、审查和需求整理任务也使用同一条桥梁。它们以自然语言协商谁处理什么；
插件不把角色、项目边界或任务类别变成路由规则、锁或额外授权。

## 非目标

- 不实现 GitHub/GitLab 的副本：不做 PR/MR、CI、看板、完整评论系统或远端权限模型。
- 不把聊天强制转换成 Ticket，也不让 Ticket 强制经过固定状态机。
- 不为主动唤醒改变原生 Codex Desktop 的启动方式；本期必须保留 ChatGPT in Chrome，受管
  app-server Desktop 模式不在范围内。
- 不自动改代码、提交、切换分支、建/关 Issue、改变优先级或中断其他 Agent。
- 第一阶段不支持跨机器公网服务、团队级账号、远程数据库或设备间强一致锁。
- 不改变现有 Proposal Pool、能力图、`tasks/<module-id>/` 计划目录或 `.agent/state.json`。

## 边界与事实源

| 概念 | 事实源 | 用途 |
| --- | --- | --- |
| 协作消息 | 本机受保护消息运行时 | 即时／队列式交流、回复、通知 |
| Agent 身份 | 运行时注册表 | 当前会话、项目、可选角色、可投递状态 |
| 本地 Ticket（后续） | 项目版本库中的 Ticket 文档 | 本地 Bug／需求的 ID、状态与历史 |
| GitHub/GitLab Issue（可选后续） | 外部 tracker | 外部协作面；与本地 Ticket 显式关联 |
| Proposal Pool | 远端默认分支 + 只读 Proposal Issue 事实 | 独立新能力的审查与晋级 |

消息不是 Ticket 的事实源；消息可引用一个 Ticket、commit、分支或验证结果。反之，Ticket 只保存
必要的消息引用／摘要，绝不复制整个私有消息收件箱。

## 第一阶段：协作通信

### 运行时与安全边界

复用已验证的开源运行时 Cross-Agent Teams MCP（XATS），以 Spec Guard 的受管可选运行时方式
提供，而不是要求用户额外安装另一个“协作插件”。

- 每台 Mac 只启动一个 loopback-only 本地守护进程；项目不是各自起一台服务。
- 版本和源码提交固定；不在运行时使用 `latest`。
- 认证 token 由用户私有配置保存，权限 `0600`；不进入仓库、插件清单、命令参数或日志。
- Claude Code 和 Codex 都通过各自小型适配器接入。Codex 的 HTTP MCP 使用官方
  `http_headers_helper` 读取私有 token；Claude Code 的受管启动包装器只在其子进程环境中临时注入
  token，并把无 secret 的 MCP 配置传给该进程。两者只暴露最小消息工具。
- 守护进程或宿主重启后，适配器重新发现并注册；失败只能报告投递未确认，不能伪称送达。
- 默认只绑定 `127.0.0.1`。远程监听、跨机器组网或共享 token 是另一个安全设计。

这不是云服务器部署；第一阶段的“服务器”是本机受管后台进程。它仍需要明确的启动、停止、健康检查
和升级路径。

### 注册与发现

产品模型是一个同机 Agent 通讯录，不是“项目组／项目／任务”三级组织图。每个聊天终端注册时仅提供
足以让其他 Agent 认识它的事实：

- 会话身份：运行时分配的唯一技术标识，以及一个人可读名字；用于精确回复，不能依赖项目名去猜。
- 当前项目：当前工作目录／仓库路径，作为展示和上下文；它不是访问控制范围，也不要求预先声明项目 ID。
- 当前工作：可选的自由文本，例如“播放器流协议排查”“主线功能开发”或“代码审查”。
- 可选角色与模型信息：仅帮助其他 Agent 判断应找谁，任何人都可以变更或省略。

Agent 可以列出当前可见的注册终端、读取这些自我介绍，再决定直接找谁。它也可以在消息中问“你负责
这个问题吗”，或让人介入；插件不根据“同项目／跨项目”走不同工作流。

XATS 的原生 `team` 是传输实现字段，不暴露为 Spec Guard 的项目组概念。第一期将所有同一 macOS
用户的 Spec Guard 会话放入一个固定的本地命名空间；本机 token 与 loopback 仍是安全边界。将来若要
让不同用户或不同机器互相不可见，需要单独设计真正的权限与隔离，而不是用项目名冒充权限系统。

### 消息合同

正文保持自由文本；结构字段只帮助索引和后续操作，均可选：

```json
{
  "kind": "message | bug-report | request | handoff | status | verification",
  "text": "故障注入流的时间戳不符合播放器预期，请检查。",
  "refs": {
    "ticket": "bug-20260917-001",
    "issue": "https://…",
    "commit": "…",
    "branch": "…",
    "verification": "npm test -- stream"
  }
}
```

`kind` 不驱动状态转换，也不隐含“对方必须接手”。典型协商——“谁处理”“是否插队”“是否纳入本迭代”——
都由对话完成，并可由人介入。

### 最小用户体验

```text
spec-guard collaboration start             # 启动或检查本机运行时
spec-guard collaboration register ...      # 注册当前终端的自我介绍
spec-guard collaboration status            # 只读显示运行时和当前通讯录
```

实际给 Agent 使用的是对应宿主的 MCP 工具（注册自我介绍、发送、收件箱、确认已读、列出当前通讯录）。
CLI 命令只负责受管运行时和诊断；不会替 Agent 生成或翻译业务消息。

### 宿主接入合同

这不是两套消息协议。两端均直接连接同一个本机 XATS MCP endpoint，只是认证方式遵循各宿主的官方能力：

Codex Desktop 的当前合同是原生邮箱模式：以 `custom` / `codex-desktop-native` 注册，保留正常的
Desktop 启动路径和 ChatGPT in Chrome。不得为此设置隔离 `CODEX_HOME`、`CODEX_APP_SERVER_WS_URL`
或受管 app-server；因此它不承诺跨会话主动唤醒，只在下一次协作工具调用时读取持久收件箱。

- Codex 的 HTTP MCP 通过 `http_headers_helper` 调用 Spec Guard 的私有头部助手；助手只向 Codex
  输出本次连接所需的 `Authorization` 头，token 不写入 `config.toml`。
- Claude Code 的用户级接入通过固定版开源 `mcp-remote@0.1.38`（MIT）实现 stdio→loopback HTTP bridge。
  `collaboration_claude_stdio.py` 从私有运行时读取 token，并只放进 bridge 子进程环境；Claude 用户配置、
  argv 和仓库文件只含变量名。配置安装使用 Claude 自己的 `mcp add --scope user`，不会碰项目配置，也拒绝
  覆盖同名服务器。未来新会话可以按普通方式启动；已经运行的 Claude 会话仍需重启后加载该 MCP 条目。
  Claude 的 channel 唤醒是可选增强，必须明确启用其开发预览 loader；未启用时仍保留收件箱式消息，不能伪报
  实时唤醒。

该设计复用开源 bridge，不为 Claude 与 Codex 再造协议代理，也不把 token 复制到用户配置。一次性受管启动
包装器仍保留作诊断／临时接入；它不是普通用户级接入的前置条件。

### 用户显式启用的本机后台服务

为避免交互式命令结束后带走守护进程，第一阶段提供**可选且用户显式调用**的用户域 LaunchAgent。它只
托管已固定版本的 XATS loopback 服务，不管理 Claude、Codex、项目或 Git，也不改变 Codex Desktop 的
启动路径，因而不影响 ChatGPT in Chrome。

- `service-enable` 在 `~/Library/LaunchAgents/com.spec-guard.collaboration.plist` 创建或更新仅属于当前
  macOS 用户的服务，并 bootstrap 到 `gui/<uid>`。不需要管理员权限，不写 `/Library/LaunchAgents`，不做
  开机级 LaunchDaemon。
- plist 的 `ProgramArguments` 调用 Spec Guard 的 `serve` 子命令；`serve` 重新校验私有 runtime 后，才在
  子进程环境中读取 token 并执行固定版 XATS。token 不出现于 plist、`ProgramArguments`、`launchctl` 调用、
  项目文件或日志路径。
- plist 使用 `RunAtLoad` 与 `KeepAlive`，并把 stdout/stderr 写入预创建的 `0600` 私有运行时日志。后台
  进程异常退出由 launchd 重启；`service-status` 只报告 plist 是否受管、launchd 是否已加载和 `/health` 是否
  可用。
- `service-enable` 只会替换经结构校验确认属于 Spec Guard 的现有 plist；同名但内容不受管时拒绝覆盖。
  `service-disable` 必须由用户明确调用，先 bootout、后删除已验证的受管 plist，不影响任何其他服务。
- 插件升级后，用户重新运行 `service-enable` 才会更新 plist 中的插件路径；过期路径由 `service-status`
  明确报告，绝不静默猜测或执行旧路径。

该设计依据 Apple 对 LaunchAgent 的 `Label`、`ProgramArguments`、`KeepAlive` 和标准输出／错误路径的
说明，以及本机 `launchctl bootstrap`、`bootout`、`kickstart` 的命令契约：
<https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html>。

## 第二阶段：本地 Ticket 账本（独立需求）

这不是通信第一阶段的前置条件。建议后续另建 `local-ticket-ledger` 能力，最小闭环为：

```text
创建 → open / in-progress / blocked / done → 关联提交与验证 → 关闭
```

状态允许项目自定义附加值，不以复杂状态机拒绝日常工作。Ticket 使用项目内、Git 跟踪的文档和稳定 ID；
目录名将在该独立设计中确定，不能与已保留的 `tasks/<module-id>/` 计划目录混淆。

当 GitHub/GitLab 恢复可用时，用户显式将本地 Ticket 关联到外部 Issue。两边带相同稳定 ID；本地文档
永久保留外部链接和迁移历史。关联成功后，当前状态／讨论的唯一工作面必须明确指定，禁止双向自动同步
造成两份相互矛盾的真相。

## 与 Proposal Pool 的关系

Proposal Pool 保留原职责：独立 `new-module` 能力、远端默认分支基线、修订身份与只读 tracker 阶段。
普通 Ticket 只有当经讨论确认“这是独立能力”时，才由人或明确授权流程新建 Proposal；不自动升级。

## 验收标准

第一阶段完成必须实证：

1. 同项目两个真实 Claude/Codex 任务可以双向收发消息并在收件箱确认。
2. 不同项目的两个已注册任务可以双向收发；项目路径只作为可见上下文，不是投递前置条件。
3. 任务可按会话身份直接投递；角色和当前工作仅作可选的通讯录信息，不参与自动路由。
4. 重启运行时或宿主后，可重新注册；未确认消息不会被报告为已送达。
5. 真实 Claude Code 与真实 Codex 各验证一次，不能用 CLI 桩或同一宿主替代。
6. 认证信息不在 Git diff、项目配置、诊断输出或进程 argv 中出现；运行时不对非 loopback 地址监听。
7. 发送／读取消息不会写 Git、Tracker、`.agent/state.json` 或 Ticket。
8. 用户明确启用后台服务后，交互式启动命令退出不影响 XATS 存活；`service-status` 同时证明 launchd
   已加载且 loopback 健康检查通过。启用／禁用不影响 ChatGPT in Chrome。

## 实施前尚需裁决

- 受管 XATS runtime 的发布形式：内置锁定包、用户级缓存，还是显式安装脚本；不能复制全量上游源码进入插件。
- Claude Code 和 Codex 的适配器是否统一由一个本地 stdio 代理启动；推荐统一，以免 token 配置落入项目。
- 运行时生成的会话身份、可读显示名和退出清理规则。
- 本地 Ticket 文档的确切路径和前端呈现方式，留给第二阶段。

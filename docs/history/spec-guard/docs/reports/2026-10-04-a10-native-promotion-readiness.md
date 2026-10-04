# A10 native 转正就绪对账（2026-10-04）

本报告是 [`2026-09-28-xats-sunset.md`](../decisions/2026-09-28-xats-sunset.md) 及其
[`2026-10-04-a10-single-mac-promotion-gate.md`](../decisions/2026-10-04-a10-single-mac-promotion-gate.md)
修订的当前状态对账，不把 `host-native-claude`／`host-native-codex` 与 A10 的实验性 native mailbox
混为一谈。最新事实基线是 v0.39.0 tag 与远端默认分支共同指向的
`585aec236eba6c2f305997472a2daf2864a92b23`；不沿用功能分支关系作结论。

## 当前判决

**A10 尚未达到“可以提出 native 成为默认传输 Proposal”的门槛。** v0.39.0 已真实发布、安装，
并在一台 Mac 完成 native 双向收发、同一 Claude 会话两次空闲唤醒和真实 Codex Desktop 空闲唤醒；
但回退演练被测试前已经存在的 21 个 native 身份与 9 条未确认直达消息安全阻断。三项门槛中：

1. 连续两个发布版本、每版在一台本机 Mac 的完整实机验收：**仍缺验证**；v0.39.0 的收发与唤醒通过，
   回退未运行，因此不计 R1；
2. 固定上游 revision 升级后的唤醒复验：**条件未触发**，上游默认分支尚无新 revision；
3. 无开放 native P1/P2：**公开 Issue 列表未发现，但本报告新记录两个 P2 候选，且仍缺 Local
   范围证据**；须先修复或完成分级，不能借宿主主路径通过而忽略。

因此当前应保持 XATS 默认、native 实验性可选，不创建转正 Proposal，不删除任一传输层。

## 门槛逐项对账

### 1. 连续两版本、单 Mac、三类真实动作

修订后的决定要求连续两个发布版本，各自在一台本机 Mac 完成：收发、空闲会话唤醒、回退演练，并把证据写入
该版本的 `docs/releases/v<version>-*.json`。

| 证据 | 当前事实 | 结果 |
| --- | --- | --- |
| v0.38.3 发布记录 | Claude/Codex 的安装、hook、Local 定向回复等记录已存在；没有 native mailbox 的收发、空闲唤醒和回退组合 | 未运行（不满足 A10） |
| v0.39.0 发布记录 | tag、GitHub Release、资产、Claude/Codex 安装均已验证；同一 Claude 身份两次空闲唤醒和真实 Codex Desktop 空闲唤醒通过；回退前置检查被既有 21 个身份和 9 条未确认直达消息阻断 | 部分通过；不计 R1 |
| 更早发布记录 | v0.18.0 有 XATS/普通 mailbox 双向记录和 native Codex Desktop 宿主记录；它们不是 A10 native backend 的“单 Mac＋空闲唤醒＋回退”组合 | 未运行（不满足 A10） |
| 2026-10-04 同机验收 | `host-native-session-routing` 与 `authorized-session-delegation` 在一台 Mac 提供了强支持证据，但它发生在候选源码而非已发布版本 | 通过（支持性证据，不计入发布门槛） |
| 合格发布版本计数 | 没有一个发布版本具备单 Mac 三类动作的 release JSON | 0 / 2，仍缺验证 |

v0.39.0 的分项证据见
[`v0.39.0-a10.json`](../releases/v0.39.0-a10.json)、
[`v0.39.0-claude.json`](../releases/v0.39.0-claude.json) 和
[`v0.39.0-codex.json`](../releases/v0.39.0-codex.json)。测试身份全部精确退休，本轮测试消息未读为
零；全局计数回到测试前数值，没有为提高评级清理任何既有身份或消息。

一台本机 Mac 即可承担每个版本的实机验收，不再要求第二台 Mac。A10 不要求开放 LAN、公网服务或实现
跨机器唤醒。

GitHub-hosted macOS runner 每个 job 都是新建并在结束后销毁的虚拟机；当前工作流也没有 Claude Code／Codex
登录态、既有目标会话或人工授权上下文。它可以补充 macOS 源码兼容性测试，但不能替代真实宿主的发现、收发、
空闲唤醒和回退证据，因此本次不新增一个无法提高验收等级的 macOS job。

### 2. 上游 revision 升级后的唤醒

| 证据 | 当前事实 | 结果 |
| --- | --- | --- |
| 仓库固定 revision | `native_collaboration_runtime.py` 的 `BRIDGE_COMMIT` 为 `8f12c880cfdba73812b6ab7bc0f373fc467e0343` | 通过（读回） |
| 本机安装 revision | runtime `status` 返回 ready，commit 与上述固定值一致 | 通过（读回） |
| revision 历史 | 该常量自 native runtime 首次引入后没有发生过升级 | 未运行（升级尚未发生） |
| 上游默认分支 | `git ls-remote ... HEAD refs/heads/main` 均仍为同一个 `8f12c880...` | 条件未触发 |

当前没有第二个上游 revision 可供真实升级，不能通过重装同一提交、改写版本文字或选择未审查 fork 来伪造
升级证据。上游出现新提交后，才能开窄范围 revision bump，审查工具面／权限差异，再做升级后唤醒验收。

### 3. 无开放 native P1/P2

| 范围 | 当前事实 | 结果 |
| --- | --- | --- |
| GitHub Issues | 合并后只读列出 3 个开放 Issue，均为 Proposal；没有 native P1/P2 Issue | 通过（公开仓库范围） |
| 仓库文档与任务 | 本报告新记录两个委派控制面 P2 候选；它们尚未修复或完成降级判决 | 未满足 |
| 真实 Local 账本 | 按既有隐私边界未扫描；本报告不能据此声称全局“零缺陷” | 未运行 |

提出转正 Proposal 前必须重新做一次新鲜的开放缺陷核对。若团队把 native 缺陷记录在 Local 账本，届时应
只在明确授权和已知编号／范围下核对，不能用本报告绕过该边界。

## 最快可执行路径

1. **先解除 v0.39.0 回退前置阻断**：由现有 21 个身份和 9 条未确认直达消息各自的所有者逐项判断，
   不批量确认、不替他人退休。全部安全结束后，在 v0.39.0 安装版上完成 native → XATS → native 回退演练；
   只有这样 v0.39.0 才能补记为 R1。
2. **紧接的下一个实际发布版本（R2）**：在本机 Mac 重复同一矩阵。版本必须真实发布且连续，源码候选或
   同一版本重复运行不能代替。
3. **修复委派控制面边界**：在现有 `authorized-session-delegation` 模块内做最小修复与回归，不新开
   能力模块；见下文“本轮新发现”。
4. **上游出现新 revision 后**：单独审查并升级 `BRIDGE_COMMIT`，安装到隔离候选，再复验空闲唤醒；
   失败则按决定评估淘汰 native，而不是降低门槛。
5. **Proposal 前最后检查**：读回两个版本的 release JSON、升级证据和当时开放 native P1/P2；三项全部
   满足后才起草“native 成为默认”Proposal。

## 本轮新发现

| 现象 | 判决 | 最小处理 |
| --- | --- | --- |
| session-delegation 创建的 Codex app-server task 在 `notLoaded` 时，native wake 保持 `pending/offline`；真实 Codex Desktop task 的相同反向唤醒通过 | 真实边界，不是 native mailbox 丢信；app-server task 不能冒充已加载 Desktop 空闲会话 | 在委派入口明确区分 `notLoaded/offline` 与 Desktop `idle`，验收只把后者计为空闲唤醒 |
| 同一个 app-server task 被 Desktop 接管后，控制器 `continue/cancel` 返回 `app-server-request-rejected: -32600` | 控制面兼容问题；消息可由精确 Desktop turn 处理，但控制器不能继续拥有该 task | 在既有委派模块增加“已被宿主接管”的可见状态或恢复路径；补一个真实／契约回归，不需要新 Spec/Plan |
| 强制停止一个正在等待的 Claude background 回合后，首次 `continue` 返回 `background-entry-invalid`，但宿主实际恢复并完成 | 控制器假失败；不影响本轮 native 传输结果，但会误导自动化 | 把 resume 后的元数据稳定化重试扩展到该路径，并验证只恢复原会话、不复制会话；不需要新 Spec/Plan |

这三个边界都不得用“测试最终通过”抹去。后两项先按 P2 候选处理，修复或完成明确降级判决前，
“无开放 P1/P2”门槛不能宣称满足。

## 当前不需要做

- 不需要创建 A10 转正 Proposal；门槛尚未达到。
- 不需要删除、废弃或默认关闭 XATS。
- 不需要第二台 Mac，也不需要开发跨机器服务、端口或远程唤醒。
- 不需要增加无法运行真实 Claude Code／Codex 会话的 GitHub-hosted macOS CI。
- 不需要重跑已通过的同机 host-native 会话路由验收来提高评级。
- 不需要修改全局 Claude/Codex 配置、添加 Codex model 参数或恢复旧 tracker bridge。
- 不需要为 app-server 的 `notLoaded` 探针重复创建更多邮箱消息；真实 Desktop 空闲唤醒已经通过。

## 本次命令证据

| 命令／来源 | 结果 |
| --- | --- |
| v0.39.0 tag／Release／资产读回 | 通过：tag 与 main 均为 `585aec236eba…`；release 非 draft/prerelease；资产 SHA-256 与本地包一致 |
| Claude/Codex 安装读回 | 通过：两端均启用 v0.39.0；Claude Code 2.1.289；app-managed Codex CLI 0.160.0 |
| native 合成双向宿主验收 | 通过：Claude 同一会话两次空闲唤醒；真实 Codex Desktop 空闲唤醒；所有测试消息读回确认 |
| rollback preflight | 未运行后续动作：`21 identities / 9 unacknowledged direct / active sessions unverified`，因此未切 selector、未启动 XATS |
| `phase-guard.sh` | 通过：35/35 模块完成，阶段 DONE |
| `verify-artifacts.sh` | 通过：3 通过、1 个既有兼容警告、0 失败；13 个旧模块缺 todo 仍按已记录边界处理 |
| `native_collaboration_runtime.py status` | 通过：ready，固定 revision `8f12c880…` |
| `collaboration_backend.py` | 通过：本机当前选择 native |
| 发布 JSON 定向查询 | 通过：没有找到符合 A10 三动作／单 Mac 组合的发布记录 |
| GitHub Actions 工作流与 hosted runner 能力 | 通过：现有 CI 仅做源码校验；临时 VM 不具备真实宿主会话验收条件 |
| `git ls-remote` 上游 HEAD/main | 通过：仍为 `8f12c880…`，无可升级 revision |
| GitHub 开放 Issue 只读列表 | 通过：3 个 Proposal，无 native P1/P2 |
| 真实 Local 账本 | 未运行：遵守不扫描边界 |

# A10 native 转正就绪对账（2026-10-04）

本报告是 [`2026-09-28-xats-sunset.md`](../decisions/2026-09-28-xats-sunset.md) 的当前状态
对账，不修改原决定，也不把 `host-native-claude`／`host-native-codex` 与 A10 的实验性 native mailbox
混为一谈。事实基线是 PR #152 合并后的远端默认分支 `f82a5092c091`；不沿用功能分支关系作结论。

## 当前判决

**A10 尚未达到“可以提出 native 成为默认传输 Proposal”的门槛。** 三项门槛中：

1. 连续两个发布版本、每版至少两台主机的实机验收：**仍缺验证**；
2. 固定上游 revision 升级后的唤醒复验：**条件未触发**，上游默认分支尚无新 revision；
3. 无开放 native P1/P2：**公开仓库范围未发现，完整结论仍缺 Local 范围证据**。

因此当前应保持 XATS 默认、native 实验性可选，不创建转正 Proposal，不删除任一传输层。

## 门槛逐项对账

### 1. 连续两版本、两主机、三类真实动作

决定要求连续两个发布版本，各自在至少两台主机完成：收发、空闲会话唤醒、回退演练，并把证据写入
该版本的 `docs/releases/v<version>-*.json`。

| 证据 | 当前事实 | 结果 |
| --- | --- | --- |
| v0.38.3 发布记录 | Claude/Codex 的安装、hook、Local 定向回复等记录已存在；没有 native mailbox 的两主机收发、空闲唤醒和回退记录 | 未运行（不满足 A10） |
| 更早发布记录 | v0.18.0 有 XATS/普通 mailbox 双向记录和 native Codex Desktop 宿主记录；它们不是 A10 native backend 的“两主机＋空闲唤醒＋回退”组合 | 未运行（不满足 A10） |
| 2026-10-04 同机验收 | `host-native-session-routing` 与 `authorized-session-delegation` 在一台 Mac 提供了强支持证据，但记录明确声明不构成 A10 转正 | 通过（支持性证据，不计入门槛） |
| 合格发布版本计数 | 没有一个发布版本同时具备两台主机和三类动作的发布 JSON | 0 / 2，仍缺验证 |

这里的“两台主机”不是要求两台机器互相跨网通信。每台主机分别在本机运行同一套收发、空闲唤醒和
回退验收即可；A10 不要求开放 LAN、公网服务或实现跨机器唤醒。

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
| 仓库文档与任务 | 除 A10 决定和历史审查分级外，没有发现开放 native P1/P2 记录 | 通过（仓库范围） |
| 真实 Local 账本 | 按既有隐私边界未扫描；本报告不能据此声称全局“零缺陷” | 未运行 |

提出转正 Proposal 前必须重新做一次新鲜的开放缺陷核对。若团队把 native 缺陷记录在 Local 账本，届时应
只在明确授权和已知编号／范围下核对，不能用本报告绕过该边界。

## 最快可执行路径

1. **下一个实际发布版本（R1）**：在两台主机分别完成 native mailbox 的收发、空闲唤醒、回退演练，
   将每台主机、宿主版本、固定 revision 和结果写入该版本 release JSON。
2. **紧接的下一个发布版本（R2）**：在同样两台主机重复同一矩阵。版本必须真实发布且连续，源码候选或
   同一版本重复运行不能代替。
3. **上游出现新 revision 后**：单独审查并升级 `BRIDGE_COMMIT`，安装到隔离候选，再复验空闲唤醒；
   失败则按决定评估淘汰 native，而不是降低门槛。
4. **Proposal 前最后检查**：读回两个版本的 release JSON、升级证据和当时开放 native P1/P2；三项全部
   满足后才起草“native 成为默认”Proposal。

## 当前不需要做

- 不需要创建 A10 转正 Proposal；门槛尚未达到。
- 不需要删除、废弃或默认关闭 XATS。
- 不需要为“两台主机”开发跨机器服务、端口或远程唤醒。
- 不需要重跑已通过的同机 host-native 会话路由验收来提高评级。
- 不需要修改全局 Claude/Codex 配置、添加 Codex model 参数或恢复旧 tracker bridge。

## 本次命令证据

| 命令／来源 | 结果 |
| --- | --- |
| `git fetch origin main`；PR #152 `gh pr view` | 通过：merge commit `f82a5092c091…`，CI success |
| `phase-guard.sh` | 通过：35/35 模块完成，阶段 DONE |
| `verify-artifacts.sh` | 通过：3 通过、1 个既有兼容警告、0 失败；13 个旧模块缺 todo 仍按已记录边界处理 |
| `native_collaboration_runtime.py status` | 通过：ready，固定 revision `8f12c880…` |
| `collaboration_backend.py` | 通过：本机当前选择 native |
| 发布 JSON 定向查询 | 通过：没有找到符合 A10 三动作／两主机组合的发布记录 |
| `git ls-remote` 上游 HEAD/main | 通过：仍为 `8f12c880…`，无可升级 revision |
| GitHub 开放 Issue 只读列表 | 通过：3 个 Proposal，无 native P1/P2 |
| 真实 Local 账本 | 未运行：遵守不扫描边界 |

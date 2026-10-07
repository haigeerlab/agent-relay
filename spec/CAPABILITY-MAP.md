# Capability Map: agent-relay

> 由 `/spec` 的 Phase 0 产出。**必须经人工评审后才能往下走。**
> Addy 原文：把图搞错代价很大，评审十行不算什么。

## 目标

agent-relay 是从 Spec Guard 拆出的独立插件，让同一台 Mac 上的 Claude Code 与 Codex 会话互相发消息、按名字找到对方并在有限授权内委派会话，
不需要安装 Spec Guard 的工作流。先平移：每个模块的行为与拆分前基线（`docs/baselines/collaboration-pre-split.md`）一致，以
`docs/collaboration-interface.md` 的现状栏为准；平移版本通过第一轮接入联调后，再按加固目标栏逐项加固。

<!-- 这一段是 Proposal 评审的目标指纹底本（`spec-digest.py` 计算）。
     改写目标会让已发布的 Proposal 被判为过期，所以改了先人工评审；追加模块不需要改这里。
     标题必须是 `## 目标`（或 `## Goal`）—— 指纹脚本按标题定位这一节。 -->

## 模块

| Module id | Responsibility | Depends on |
|---|---|---|
| acceptance-kit | 建立本仓库的测试运行入口与可复用的真实宿主验收脚本和清单，供平移、加固与两轮联调共用；修正迁出时读 Spec Guard 文件的 4 个测试，使迁入代码的测试全绿。 | — |
| mailbox-core | 平移协作信箱与 native 传输：固定上游 bridge 的运行时、宿主适配器与身份退役，按决策 D1 改用 `agent-relay` MCP 服务名与 `~/.agent-relay/` 状态根，行为与基线一致。 | acceptance-kit |
| session-routing | 平移统一会话路由：Claude↔Claude 走 ListAgents/SendMessage、Codex↔Codex 走 Codex App task/thread、Claude↔Codex 走信箱，回退规则与基线一致。 | mailbox-core |
| cross-host-delegation | 平移跨宿主会话委派：授权意图、生命周期、结果回传与同名消歧，控制器与基线一致，基线记录的已知缺陷保持原样。 | mailbox-core, session-routing |
| packaging | 双端插件清单与 marketplace、`interface.json`（接口 1.0）、README、安装与卸载说明，并在 Claude Code 与 Codex 上实装验证。 | mailbox-core, session-routing, cross-host-delegation |
| state-migration | 检测 Spec Guard 时期的协作状态（`~/.spec-guard/native-collaboration/`、`session-delegation/` 与宿主中的旧 MCP 条目和权限规则），先备份再迁移到新名字并核验，不静默删除。 | mailbox-core, packaging |
| delegation-fixes | 修复基线发现 3、4 与第一轮联调发现 7：等待前置条件的 create 不再让之后的同名会话产生歧义，从未启动的记录能干净取消；git worktree 里的 Claude 目标创建后能找到，列表对不上时下一次调用补绑而不是一直停在 unknown；空闲 Claude 目标第二轮不再误报 target-busy。在平移版本通过第一轮联调后、加固模块之前构建。 | cross-host-delegation, state-migration |
| test-isolation | 用一个环境变量把整个 agent-relay 状态根（信箱运行时、委派库、迁移备份）整体迁到别处，控制器、迁移与验收脚本都遵守；所有测试在临时状态根里运行，不读写真实的 ~/.agent-relay。加固模块中最先做，后续加固的测试都依赖它。 | mailbox-core, cross-host-delegation, state-migration |
| bridge-vendoring | 把固定提交 8f12c88 的上游 bridge（TS 源码）收进 agent-relay 仓库，保留 MIT 署名与来源说明；运行时改为从仓内副本安装，不再 git clone 上游。只改来源和安装路径，行为与 8f12c88 完全一致；之后修改 bridge 的加固模块都依赖它。 | mailbox-core, test-isolation |
| delivery-state-machine | 给信箱消息补上投递状态机（queued → sending → accepted、failed 或 unknown；queued → expired）：有歧义的提交标为 unknown 且绝不自动重放；排队超时后标为 expired、默认不再读出也不再送达，超时可配置并给出默认值建议；ack 让对应唤醒任务结束（发现 5）。同时实现 bridge-vendoring D26 规定的已装运行时升级命令。 | mailbox-core, bridge-vendoring |
| durable-ordering | 先持久化再提交（以崩溃注入测试证明）；按接收方保证投递顺序，一个接收方卡住不阻塞其他接收方；每个接收方的待投递数量有上限，上限可配置并给出默认值建议。 | delivery-state-machine |
| idempotency | 同一发送方的重试 key 只对应一份内容：内容相同返回原消息，内容不同拒绝；回复带上被回复消息的 id，对同一条消息的相同回复去重。 | durable-ordering |
| identity-check | 发送方 from 必须与调用方宿主会话绑定的身份一致，不一致拒绝；只有原消息的收件人能回复它；名字不能被另一个宿主会话改绑；身份缺失时返回明确指引；自动批准的会话（含 Codex guardian_subagent）不能绑定唤醒（发现 1）；并修正 bridge 打开信箱时 busy_timeout 设置晚于 journal_mode 的问题。 | idempotency |

Build order: acceptance-kit → mailbox-core → session-routing → cross-host-delegation → packaging → state-migration → delegation-fixes → test-isolation → bridge-vendoring → delivery-state-machine → durable-ordering → idempotency → identity-check

<!-- Spec Guard 按严格串行推进。为兼容上游格式，逗号分组会按左到右顺序展开为单模块步骤，不代表并行授权。 -->
<!-- 加固模块（test-isolation、delivery-state-machine、durable-ordering、idempotency、identity-check、ops-commands、
     safe-uninstall）在第一轮联调通过后用 add-module 逐个插入，不在本次评审范围内。 -->

---

## 评审记录

- [x] 模块边界确认（砍掉或替换一个模块，不需要重写其他模块的需求）
- [x] 依赖方向单向无环（互相依赖 = 它们本来就是一个模块）
- [x] module id 已定稿（kebab-case，之后绝不改名 —— 同一个 id 同时是
      `spec/<id>.md`、`tasks/<id>/`、`.agent/state.json` 的 `activeModule` 和 Proposal 中的模块名，
      已发布的 Proposal 改不动）
- [x] 构建顺序符合依赖拓扑

评审人：用户（delegation-fixes 在第一轮联调通过后、加固之前构建；D7 测试归 acceptance-kit；D1 改名归 mailbox-core）
日期：2026-10-07

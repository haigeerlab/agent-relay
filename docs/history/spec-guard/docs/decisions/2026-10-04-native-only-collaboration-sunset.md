# 决策：本机协作立即收敛为 native-only

日期：2026-10-04

## 背景

本项目当前只有一名实际使用者。该使用者明确选择 native 作为唯一的本机 Claude Code／Codex
会话通讯实现，不希望为了未知旧用户长期维护 XATS 与 native 双栈，也接受宿主或 native 出现兼容问题时
优先直接修复 native、期间通讯可能暂时不可用的风险。

当前本机已经完成 native 双向收发、Claude 同一会话重复空闲唤醒、真实 Codex Desktop 空闲唤醒、
消息确认和测试身份精确退役。2026-10-04 的最终只读 preflight 为零个 active identity、零条未确认
直达或广播投递。委派控制面的两个 P2 候选也已修复并合入默认分支。

## 决策

1. **native 成为唯一产品传输。** 日常协作、会话路由和授权委派不再选择、回退或兼容 XATS。
2. **立即退役 XATS 产品面。** 删除 XATS runtime、adapter、token/header helper、Claude launcher、
   selector、cutover/rollback/archive 操作面及其现行测试和用户文档。历史报告与任务记录保留为时点证据。
3. **不再要求旧转正门槛。** 连续两个发布版本、固定上游 revision 必须先升级、native→XATS→native
   回退演练、后续单独的默认化 Proposal 和一个 minor 的双栈等待期，不再是退役前置条件。
4. **保留真正必要的交付门。** 删除 XATS 前必须证明：
   - 当前默认分支上的 native-only 源码回归通过；
   - 一台本机 Mac 上的 Claude Code ↔ Codex 收发、回复和空闲唤醒通过；
   - native 邮箱没有 active identity 或未确认投递；
   - 没有已知会阻断当前单用户工作流的开放 native P1/P2。
5. **旧数据只归档，不迁移进产品。** 当前用户目录中的 XATS SQLite 邮箱和既有只读归档可以留在磁盘上，
   但新版插件不读取、启动、恢复或删除它们。新安装不会创建或继承这些数据。
6. **宿主配置清理单独授权。** 源码删除不隐式修改 Claude/Codex 用户配置或 LaunchAgent。新版安装和
   native-only 验收完成后，再由用户明确授权清除本机残留的 XATS MCP 配置和进程文件。

## 被取代的门槛

本决策取代
[`2026-09-28-xats-sunset.md`](2026-09-28-xats-sunset.md) 和
[`2026-10-04-a10-single-mac-promotion-gate.md`](2026-10-04-a10-single-mac-promotion-gate.md)
中关于“两版本、上游 revision 升级、回退演练、Proposal 后等待一个 minor”的尚未触发门槛。
两份旧决策及其发布前后报告继续保留，不能被改写成当时已经满足。

## 接受的风险

- native 或 Claude/Codex 宿主升级破坏唤醒时，没有 XATS 产品回退；修复期间通讯可能不可用。
- 固定上游 revision 仍须经过审查后才能升级，但“先发生一次升级”不再是删除 XATS 的人为等待条件。
- 当前决策优化唯一实际使用者的维护成本，不承诺未出现的外部用户获得 XATS 兼容期。


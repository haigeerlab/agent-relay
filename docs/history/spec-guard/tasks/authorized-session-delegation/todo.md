# authorized-session-delegation tasks

- [x] 在隔离 mailbox 完成 Claude Code → Codex、Codex → Claude Code 的真实创建门槛：
      Codex 使用临时项目，Claude background 使用已受信项目并记录未受信条件；覆盖精确身份、
      自注册、首轮结果、同会话第二轮、实际权限、停止和遗留状态。
- [x] 用测试先固定 task/strict/batch/session 授权信封、权限 intent、owner-only SQLite、
      单跳、到期、撤销、并发幂等和普通 mailbox 不授予权限。
- [x] 实现 Codex app-server 创建/继续/状态/取消适配器，固定受支持 binary provenance、
      省略 model，并覆盖协议失败与响应丢失。
- [x] 实现 Claude Code background session 创建/继续/状态/停止适配器，复用临时无令牌 MCP
      配置和参数过滤，并覆盖 held permission 与身份对账。
- [x] 接入自然语言委派、非阻塞授权通知和带宿主标签的已加入目录；不扫描未注册窗口或暴露
      完整内部 ID。
- [x] 完成 create-before-register、重启、held、超时、取消、到期和精确清理的故障恢复；
      不重复建会话、不丢未读结果、不虚报停止。
- [x] 安装可回滚候选并完成双向两轮真实宿主验收、负例、文档、changelog 和完整仓库回归；
      任一方向缺证据则保持未完成。

当前阶段：Plan 已于 2026-10-03 获用户确认。任务 1 的真实宿主门槛已按
`host-creation-preflight-2026-10-03.md` 有条件通过；任务 2 的授权状态机、任务 3 的 Codex
app-server 适配器、任务 4 的 Claude Code background 适配器、任务 5 的自然语言控制入口与任务 6
的故障恢复均已通过聚焦测试和完整仓库回归。2026-10-04 的源码候选已在真实宿主完成双向两轮、
native 自注册、safe-review 写入负例、取消和停止读回；本项目的最小 Claude 通信 allow 预检为
`ready=true`。任务 7 又完成了双向最小真实 mailbox 结果回传与真实同名短编号消歧；控制器不读取消息
正文或推进 inbox 游标。完整仓库回归结果与未覆盖的 XATS／跨机器边界详见
`live-acceptance-2026-10-04.md`。这不推进 A10 native 转正，也不删除 XATS。

同日发布后宿主复测又暴露了 Claude resume 后元数据短暂未稳定，以及 Codex Desktop 接管
thread 后控制请求被拒绝的两项 P2 恢复问题。最小修复、回归结果与不推进 A10 计数的边界见
`host-recovery-regression-2026-10-04.md`；原实机记录保留其历史时点事实。

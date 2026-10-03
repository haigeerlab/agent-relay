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
- [ ] 安装可回滚候选并完成双向两轮真实宿主验收、负例、文档、changelog 和完整仓库回归；
      任一方向缺证据则保持未完成。

当前阶段：Plan 已于 2026-10-03 获用户确认。任务 1 的真实宿主门槛已按
`host-creation-preflight-2026-10-03.md` 有条件通过；任务 2 的授权状态机、任务 3 的 Codex
app-server 适配器、任务 4 的 Claude Code background 适配器、任务 5 的自然语言控制入口与任务 6
的故障恢复均已通过聚焦测试和完整仓库回归。当前进入任务 7；真实双向两轮验收、候选安装、文档与
changelog 尚未完成，当前项目的 Claude 通信 allow 只读预检仍为 `held/project-allow-rules`。

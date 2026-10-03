# authorized-session-delegation tasks

- [ ] 在隔离临时项目完成 Claude Code → Codex、Codex → Claude Code 的真实创建门槛：精确
      身份、自注册、首轮结果、同会话第二轮、实际权限、停止和遗留状态。
- [ ] 用测试先固定 task/strict/batch/session 授权信封、权限 intent、owner-only SQLite、
      单跳、到期、撤销、并发幂等和普通 mailbox 不授予权限。
- [ ] 实现 Codex app-server 创建/继续/状态/取消适配器，固定受支持 binary provenance、
      省略 model，并覆盖协议失败与响应丢失。
- [ ] 实现 Claude Code background session 创建/继续/状态/停止适配器，复用临时无令牌 MCP
      配置和参数过滤，并覆盖 held permission 与身份对账。
- [ ] 接入自然语言委派、非阻塞授权通知和带宿主标签的已加入目录；不扫描未注册窗口或暴露
      完整内部 ID。
- [ ] 完成 create-before-register、重启、held、超时、取消、到期和精确清理的故障恢复；
      不重复建会话、不丢未读结果、不虚报停止。
- [ ] 安装可回滚候选并完成双向两轮真实宿主验收、负例、文档、changelog 和完整仓库回归；
      任一方向缺证据则保持未完成。

当前阶段：Plan 已于 2026-10-03 获用户确认。未开始产品实现，也未创建真实目标会话；
晋级合并后从任务 1 的真实宿主可行性门槛开始。

# host-native-session-routing tasks

- [x] 固定 Claude Code 与 Codex App 的真实宿主能力门槛，记录版本、公开 primitive、权限和不可用边界。
- [ ] 以测试先行实现无副作用的路由策略与公开状态契约，覆盖四格矩阵、显式 fallback 和反向用例。
- [ ] 接入 Claude Code 同宿主原生发现、发送、回复与等待，不打开私有 socket 或复制正文到 bridge。
- [ ] 接入 Codex 同宿主精确 task/thread 发现、发送、回复与等待，不按标题猜测或重复投递。
- [ ] 接入 Claude↔Codex bridge、受约束 fallback 与统一会话目录，保持单 backend 和真实状态语义。
- [ ] 把消息路由接入现有委派生命周期，分离 `hostOperation`/`transport` 并覆盖幂等、恢复和取消。
- [ ] 完成三条链路的同机双向两轮真实验收、负例、文档、changelog 与完整仓库回归。

当前阶段：Plan 待用户评审。实施必须按顺序推进；Task 1 或 Task 7 的宿主证据不可由单元测试替代。
本模块不推进 A10 native 转正，不删除 XATS，不增加跨机器能力。

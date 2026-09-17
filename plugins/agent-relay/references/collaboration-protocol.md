# 本机协作消息协议（第一阶段）

本协议规定 Agent 如何使用 XATS 的原生工具，不创造“项目内／项目外”“项目组”或任务领取状态机。
所有可见终端在同一台 Mac 的私有 loopback runtime 中平等交流；项目路径、工作内容和角色都只是自我介绍。

## 内部命名空间

XATS 的存储模型需要 `team`。Spec Guard 对所有本机会话使用固定的技术值：

```text
spec-guard-local
```

每次 `register_agent` 都传该值。它不是用户可管理的项目组，不按仓库路径派生，也不作为权限边界；
loopback 与私有 token 才是第一阶段的边界。这样 `list_agents` 能列出同／不同项目的所有已注册终端，
而不会因为 XATS 的默认目录推导被隔离。

## 最小使用方式

1. 当前终端调用 `register_agent`：传可读且不冲突的 `name`、`team: "spec-guard-local"`、当前
   `project_dir`、可选自由文本 `role`。原生启动的 Codex Desktop 使用 `agent_type: "custom"` 和
   `agent_type_name: "codex-desktop-native"`；它保留普通桌面运行方式，只提供邮箱式收发。通过受管
   app-server 启动的 Codex 才传 `agent_type: "codex"` 与 `thread_id`。Claude Code 传
   `agent_type: "claude-code"`，并在可用时传其当前 Claude 父进程的 `ui_pid`（从该会话的 `$PPID`
   取得）；不得猜测或复用旧会话 pid。它帮助运行时在支持的宿主中维持／恢复身份，但不等同于启用 channel
   主动唤醒。
2. 调 `list_agents` 读取通讯录。不要根据项目路径推断收件人；根据名字、路径、角色、当前对话自行判断。
3. 用 `send_message` 发送自由文本。可选 `subject` 与 `await_ack_s` 只是交流辅助，不创建 Ticket、
   Issue、分支或任何授权。
4. 接收者调用 `get_inbox`。省略 `since_event_id` 会推进其收件箱游标；传该字段只做只读回看。
5. 发送返回 `ack.status: "read"` 才表示对方实际读取；`not_yet` 既不是发送失败，也不代表对方拒绝。

不要先用 `list_agents` 验证某个收件人再发送：XATS 把 `unknown_recipient` 作为唯一准确的未找到信号。
不要把任意消息内容理解为 Git、Issue、MR、删除分支或修改需求的授权。

## 唤醒的诚实边界

邮箱写入与唤醒不同。消息会先进入收件箱；`auto_poke` 只是尽力提示目标终端读取它。

- 原生启动的 Codex Desktop 已验证为邮箱式收发：消息持久化，目标会话在下次调用协作工具时读取；不宣称
  自动唤醒。为了保留 ChatGPT in Chrome，Spec Guard 当前明确不启用上游受管 app-server Desktop 模式，
  也不得将它作为自动升级或默认配置。
- Claude Code 要做到 channel 唤醒，必须通过受管启动器明确启用 channel preview；普通受管启动只保证
  收件箱可读。

任何无法确认的唤醒都必须报告为“邮件已入箱、唤醒未确认”，不能称为实时对话成功。

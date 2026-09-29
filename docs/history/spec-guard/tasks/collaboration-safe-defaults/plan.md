# Plan: collaboration-safe-defaults

依据 [`spec/collaboration-safe-defaults.md`](../../spec/collaboration-safe-defaults.md)。两个 task 串行，每个 task 一条
提交；先写能在当前代码上失败的测试并记录失败输出，再修改到通过。两个 task 之间没有代码依赖，先做改代码、风险更高的 T。

每个 task 完成时都运行三条最小验证：

```bash
/bin/bash scripts/validate.sh
/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh
/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh
```

## Task 1：Claude 启动器经 stdio 代理连接，token 不进入 Claude 环境（T）

- `collaboration_claude.py`：临时 MCP 配置改为 stdio 形式，命令是 `sys.executable` 加
  `collaboration_claude_stdio.py --config-dir <运行时目录>`；`launch_claude` 传给 Claude 的环境不再写入
  `SPEC_GUARD_COLLABORATION_TOKEN`，父进程环境里已有也移除；tmux 模式经同一路径，同样满足。
- `collaboration_adapters.py`：`claude` 检查命令输出与启动器相同的 stdio 配置；只服务 HTTP 加环境变量方式、且不再有
  调用方的代码删除。`install-claude` 与 Codex 路径不变。
- 测试（`test_collaboration_runtime.py`）：
  - 配置是 stdio 形式、指向 stdio 代理与运行时目录，全文不含 token 值和 `SPEC_GUARD_COLLABORATION_TOKEN`；
  - Claude 子进程环境不含该变量，包括父进程环境里预先设置了它的情况；
  - tmux 模式同样满足；
  - `claude` 检查输出与启动器配置一致；
  - 现有"stdio 代理把 token 交给 `mcp-remote`"的断言保留。
- `spec/collaboration-messaging.md`：Claude 桥接与 token 的描述与实现一致。
- `CHANGELOG.md` Unreleased 记一条变更。
- **验收：** 上述测试在修改前失败、修改后通过；`grep -n TOKEN_ENV_VAR` 只剩 stdio 代理与 Codex 请求头辅助脚本仍需的用法。
- **验证：** `python3 -B` 与 `/usr/bin/python3 -B` 各跑一次 `test_collaboration_runtime.py`；`test_collaboration_backend.py`；
  `test_host_config_removal.py`。
- **文件：** `collaboration_claude.py`、`collaboration_adapters.py`、`test_collaboration_runtime.py`、
  `spec/collaboration-messaging.md`、`CHANGELOG.md`。

## Task 2：加入协作默认不绑定唤醒（W）

- `skills/collab/SKILL.md`：native 加入流程默认 `wake: null`（Claude Code 与 Codex 相同）；只有用户在当前对话里明确
  要求、且会话不是自动批准模式时，才按现有核对步骤绑定唤醒；注册后说明是否绑定、未绑定时如何收信；保留自动批准
  禁令与"被唤醒只处理只读请求"。
- `references/collaboration-runtime.md`、`docs/optional-features.md`：说明默认不绑定、如何显式开启、开启意味着什么；
  已登记的唤醒身份可以按现有命令退役，本模块不自动处理。
- 测试：`test_native_collab_entry.py` 中锁定旧默认（`wake: "auto"`、`wake: {app: "codex", sessionId:`）的断言改为
  锁定新规则：`wake: null` 是默认；绑定只出现在"明确要求且非自动批准"的条件下；核对步骤仍在。`test_collab_entry.py`
  现有的自动批准断言保留。
- `CHANGELOG.md` Unreleased 记一条变更。
- **验收：** 新断言在修改前失败、修改后通过；三处文档对默认值的说法一致（grep `wake: null` 与 `wake: "auto"` 的上下文）。
- **验证：** `test_native_collab_entry.py`、`test_collab_entry.py`、`test_workflow_checkpoints.py`。
- **文件：** `skills/collab/SKILL.md`、`references/collaboration-runtime.md`、`docs/optional-features.md`、
  `test_native_collab_entry.py`、`CHANGELOG.md`。

## Checkpoint：完成

- 三条最小验证在默认 `python3` 与 `/usr/bin/python3` 下都通过。
- 逐条核对 Spec 的 Success criteria 并记录证据。
- `todo.md` 全部勾选，阶段变为 DONE；向用户汇报，由用户决定推送与开 PR。

## 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 删除 HTTP 配置代码时误伤仍在用它的路径 | 中 | 先 grep 全部调用方；`install-claude` 与 Codex 路径有现有测试兜底 |
| stdio 代理依赖 `npx` 与 `mcp-remote`，启动器以前不依赖 | 低 | 启动器只生成配置，不启动代理；代理本来就是 `install-claude` 的标准路径 |
| 措辞测试只证明文字存在，不证明模型遵守 | 中 | Spec 已写明唤醒只能靠指令约束；测试锁定的是规则本身不被回退 |

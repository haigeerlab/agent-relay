# Spec: collaboration-safe-defaults

## Objective

协作信箱有两个默认值偏向"方便"而不是"安全"，2026-09-28 的项目审计都核实过：

1. **唤醒默认绑定。** `collab` skill 让 Claude Code 默认以 `wake: "auto"` 登记，native Codex Desktop 默认带
   `sessionId` 绑定唤醒。仓库自己的受控试验（`references/collaboration-runtime.md`）记录过：被唤醒的自动批准会话
   不经人工确认就执行了消息里的命令。目前唯一的防护是一段"自动批准会话不要绑定"的文字，而且要求模型知道自己的
   权限模式。
2. **Claude 启动器把 token 放进会话环境。** `collaboration_claude.py` 生成 HTTP 形式的 MCP 配置，请求头引用
   `${SPEC_GUARD_COLLABORATION_TOKEN}`，因此 Claude 进程必须带着这个环境变量启动，Bash 工具的子进程也会继承它。
   这与本 spec 的上游 `spec/collaboration-messaging.md` 中"token 只存在于子进程环境"的承诺不符。

本模块把唤醒改为"默认不绑定、用户明确要求才绑定"，把 Claude 启动器改为经 stdio 代理连接，让 token 不再进入
Claude 进程，并用测试防止回退。

登记：2026-09-28 按用户决定经 `/spec-guard:add-module` 快速插入能力图。它不改变 `collaboration-messaging` 已接受
的传输选择（XATS 默认、native 实验性），因此不需要 Proposal。

## Assumptions

用户已于 2026-09-28 确认：

1. 唤醒由上游服务端的 `bridge_register` 实现，本插件没有代码层面的开关。"默认不绑定"通过 skill 指令实现，并由回归
   测试锁定措辞；不修改上游，也不维护补丁。
2. Claude Code 与 native Codex Desktop 采用同一条规则：默认 `wake: null`。
3. "明确要求"指用户在当前对话里要求被唤醒（例如"加入并允许唤醒"）。开着自动批准（bypass／full-auto）的会话即使
   用户要求也不绑定唤醒，保留现有禁令。
4. Claude 启动器改用 stdio 代理（`collaboration_claude_stdio.py`，它自己读取 0600 的 token 文件，只交给子进程
   `mcp-remote`），不再设置 `SPEC_GUARD_COLLABORATION_TOKEN`。
5. 范围之外：XATS 功能扩展、依赖锁定、唤醒机制本身、上游代码。
6. 唤醒的真实行为靠指令约束，只做静态验证；token 修复用单元测试验证，不启动真实 XATS 服务。

## Contract

### W 唤醒默认不绑定（skill 与文档）

- `skills/collab/SKILL.md` 的 native 加入流程：
  - 默认以 `wake: null` 登记，Claude Code 与 native Codex Desktop 相同；
  - 只有用户在当前对话里明确要求唤醒、且当前会话**不是**自动批准模式时，才按现有步骤绑定：Claude Code 先用
    `bridge_sessions` 核对 `thisSession` 再传 `wake: "auto"`；Codex 从当前任务环境读取并校验 `CODEX_THREAD_ID`
    后传 `wake: {app: "codex", sessionId: …}`。无法确认绑定对象时仍然停止，不猜测；
  - 注册成功后的报告里说明本会话是否绑定了唤醒，以及未绑定时如何收信（`bridge_inbox`，或主动等待时用
    `bridge_wait` 并传 `acknowledge: false`）；
  - 保留"自动批准会话不绑定唤醒"与"被唤醒后只处理只读请求"的规则。
- `references/collaboration-runtime.md` 与 `docs/optional-features.md`：说明默认不绑定唤醒、如何显式开启，以及开启
  等于信任本机所有同用户 agent。
- 现有的唤醒身份不受影响：本模块只改变新登记时的默认，不自动退役或修改已登记的身份。

### T Claude 启动器不把 token 放进会话环境（代码）

- `collaboration_claude.py` 的临时 MCP 配置改为 stdio 形式：命令是当前 Python 解释器加
  `collaboration_claude_stdio.py --config-dir <运行时目录>`；配置文件里没有 token，也不引用 token 环境变量。
- `launch_claude`（以及经它启动的 tmux 模式）不再向 Claude 进程环境写入 `SPEC_GUARD_COLLABORATION_TOKEN`；启动前
  若父进程环境里已有这个变量，也从传给 Claude 的环境中移除。
- `collaboration_adapters.py claude` 检查命令打印的 Claude 配置与启动器一致，改为 stdio 形式；`install-claude` 行为
  不变（它本来就使用 stdio 代理）。Codex 的请求头辅助脚本路径不变。
- 若不再有调用方，删除只服务 HTTP 加环境变量方式的代码（例如 `claude_mcp_config` 中的请求头模板），不留死代码。
- `spec/collaboration-messaging.md` 中关于 Claude 桥接与 token 的描述更新为与实现一致。

## Commands

```text
python3 -B plugins/spec-guard/hooks/test_collab_entry.py
python3 -B plugins/spec-guard/hooks/test_native_collab_entry.py
python3 -B plugins/spec-guard/hooks/test_collaboration_runtime.py
python3 -B plugins/spec-guard/hooks/test_collaboration_backend.py
/usr/bin/python3 -B plugins/spec-guard/hooks/test_collaboration_runtime.py
/bin/bash scripts/validate.sh
/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh
/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh
```

## Project structure

```text
plugins/spec-guard/skills/collab/SKILL.md                 -> W：默认 wake: null 与显式开启流程
plugins/spec-guard/references/collaboration-runtime.md    -> W：运行时说明
docs/optional-features.md                                 -> W：用户说明
plugins/spec-guard/hooks/test_collab_entry.py,
  test_native_collab_entry.py                             -> W：措辞回归
plugins/spec-guard/hooks/collaboration_claude.py          -> T：stdio 配置，不设置 token 环境变量
plugins/spec-guard/hooks/collaboration_adapters.py        -> T：检查输出与启动器一致
plugins/spec-guard/hooks/test_collaboration_runtime.py    -> T：环境与配置断言
spec/collaboration-messaging.md                           -> T：描述与实现一致
CHANGELOG.md                                              -> Unreleased：变更说明
```

## Testing strategy

- 先写测试并确认它在当前代码上失败，再修改。
- W（静态）：断言 `collab` skill 把 `wake: null` 写成默认；绑定唤醒只出现在"用户明确要求且非自动批准"的条件下；
  自动批准禁令与"被唤醒只处理只读请求"仍在。`test_native_collab_entry.py` 中锁定旧默认措辞的断言改为锁定新规则。
- T（单元）：
  - 启动器生成的配置是 stdio 形式，指向 `collaboration_claude_stdio.py` 和运行时目录，全文不含 token 值，也不含
    `SPEC_GUARD_COLLABORATION_TOKEN`；
  - 传给 Claude 子进程的环境不含 `SPEC_GUARD_COLLABORATION_TOKEN`，即使父进程环境里有它；
  - tmux 模式同样满足；
  - `collaboration_adapters.py claude` 的输出与启动器配置形式一致；
  - stdio 代理仍然把 token 交给 `mcp-remote` 子进程（现有断言保留）。
- 每个任务完成后运行三条最小验证；T 部分再用 `/usr/bin/python3` 跑一次运行时测试。

## Boundaries

- Always：先红后绿；token 只从 0600 文件读入，只进入代理的子进程；不改变传输选择与版本固定。
- Ask first：任何需要修改上游 `claude-codex-mcp-bridge` 的做法；自动退役或修改已登记的唤醒身份；改变 Codex 路径。
- Never：把 token 写入配置文件、命令行参数或 Claude 进程环境；在自动批准会话中绑定唤醒；启动、切换或修改本机的
  真实协作运行时与宿主配置。

## Success criteria

- 按新版 `collab` skill 加入协作的会话，除非用户明确要求，登记时都用 `wake: null`；回归测试锁定这条规则。
- 经 `collaboration_claude.py` 启动的 Claude 会话，环境里没有 `SPEC_GUARD_COLLABORATION_TOKEN`，临时配置里也没有
  token；单元测试证明这一点，并且修改前这些测试是失败的。
- 文档（skill、运行时说明、`docs/optional-features.md`、`spec/collaboration-messaging.md`）与实现一致。
- 三条最小验证在默认 `python3` 与 `/usr/bin/python3` 下都通过。

## Decisions

用户于 2026-09-28 批准本 Spec，并采用默认：对已经以 `wake: "auto"` 登记的身份，本模块只在文档里提示可以退役，
不做自动处理，也不在 `collaboration-ops` 里新增列出这类身份的检查。

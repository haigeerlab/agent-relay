# Spec: collaboration-safe-defaults

## Objective

协作会话的默认值必须偏向安全：新身份默认不绑定唤醒，自动批准会话禁止绑定；用户明确要求且能精确证明当前
会话身份时，才允许绑定本机唤醒。native 是当前唯一协作传输，不存在兼容传输选择或自动回退。

本模块最初于 2026-09-28 修复旧 Claude 启动器的 token 继承问题，并建立上述唤醒默认值。兼容传输产品面已按
[`2026-10-04-native-only-collaboration-sunset.md`](../docs/decisions/2026-10-04-native-only-collaboration-sunset.md)
删除；相关启动器、token 和 stdio 代理契约现在只属于历史实现，不再是当前产品要求。本模块继续约束仍然有效的
唤醒和 native-only 安全边界。

## Assumptions

用户已确认：

1. 唤醒由固定 revision 的 native bridge 提供；本插件通过 skill 指令与适配层限制调用方式，不修改上游源码。
2. Claude Code 与 native Codex Desktop 采用同一条规则：默认 `wake: null`。
3. “明确要求”指用户在当前对话里要求被唤醒（例如“加入并允许唤醒”）。开着自动批准（bypass／full-auto）的会话即使
   用户要求也不绑定唤醒，保留现有禁令。
4. 源码检查和测试锁定默认值、固定 mailbox 工具面与旧传输缺席；真实收发、回复和空闲唤醒仍必须由宿主验收证明。
5. 范围之外：跨机器通信、上游代码修改、自动修改 Claude/Codex 全局配置，以及读取或迁移旧传输私有数据。

## Contract

### W 唤醒默认不绑定（skill 与文档）

- `skills/collab/SKILL.md` 的 native 加入流程：
  - 默认以 `wake: null` 登记，Claude Code 与 native Codex Desktop 相同；
  - 只有用户在当前对话里明确要求唤醒、且当前会话**不是**自动批准模式时，才按现有步骤绑定：Claude Code 先用
    `bridge_sessions` 核对 `thisSession` 再传 `wake: "auto"`；Codex 从当前任务环境读取并校验 `CODEX_THREAD_ID`
    后传 `wake: {app: "codex", sessionId: …}`。无法确认绑定对象时仍然停止，不猜测；
  - 注册成功后的报告里说明本会话是否绑定了唤醒，以及未绑定时如何收信（`bridge_inbox`，或主动等待时用
    `bridge_wait` 并传 `acknowledge: false`）；
  - 保留“自动批准会话不绑定唤醒”与“被唤醒后只处理当前权限允许的请求”的规则。
- `references/collaboration-runtime.md` 与 `docs/optional-features.md`：说明默认不绑定唤醒、如何显式开启，以及开启
  等于信任本机所有同用户 agent。
- 现有的唤醒身份不受影响：本模块只改变新登记时的默认，不自动退役或修改已登记的身份。

### N native-only 安全边界（代码与文档）

- 当前产品路径只解析固定 revision 的 native runtime；没有兼容 runtime、HTTP/token adapter、Claude launcher、
  backend selector 或 cutover/rollback 操作面。
- Codex 接入只启用固定的 mailbox 工具集合；Claude 接入同时生成最小 allow 与 deny 规则，不把上游 worker 工具当作
  会话通信能力暴露。
- native 不可用时明确停止并给出最小恢复动作；不得读取旧邮箱、启动兼容服务或尝试第二种传输。
- 初始化、刷新宿主配置、注册新身份和绑定唤醒都是独立副作用；只在相应授权范围内执行，源码或插件升级不自动修改
  Claude/Codex 全局配置。
- `test_native_only_collaboration.py` 锁定旧传输 callable 产品文件与现行契约中的旧默认描述均已消失。

## Commands

```text
python3 -B plugins/spec-guard/hooks/test_collab_entry.py
python3 -B plugins/spec-guard/hooks/test_native_collab_entry.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_runtime.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_adapters.py
python3 -B plugins/spec-guard/hooks/test_native_only_collaboration.py
/bin/bash scripts/validate.sh
/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh
/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh
```

## Project structure

```text
plugins/spec-guard/skills/collab/SKILL.md                  -> W：默认 wake: null 与显式开启流程
plugins/spec-guard/references/collaboration-runtime.md     -> W：运行时说明
docs/optional-features.md                                  -> W：用户说明
plugins/spec-guard/hooks/test_collab_entry.py,
  test_native_collab_entry.py                              -> W：措辞回归
plugins/spec-guard/hooks/native_collaboration_runtime.py,
  native_collaboration_adapters.py                         -> N：固定 native runtime 与最小宿主工具面
plugins/spec-guard/hooks/test_native_only_collaboration.py -> N：旧传输缺席与现行文档契约
spec/collaboration-messaging.md                            -> N：唯一传输与宿主边界
CHANGELOG.md                                               -> Unreleased：变更说明
```

## Testing strategy

- W（静态）：断言 `collab` skill 把 `wake: null` 写成默认；绑定唤醒只出现在“用户明确要求且非自动批准”的条件下；
  自动批准禁令与“被唤醒只处理当前权限允许的请求”仍在。
- N（单元与契约）：验证固定 native revision、最小 mailbox 工具集合、Claude allow/deny 规则、缺失 runtime 的停止语义，
  以及旧 XATS 产品文件和现行契约描述均不存在。
- 宿主：发布候选安装后，另行验证 Claude Code ↔ Codex 双向收发、确认和同一空闲会话重复唤醒；测试全绿不能替代它。
- 每个任务完成后运行三条最小验证；涉及插件入口时再运行 Codex smoke 判决器自测。

## Boundaries

- Always：默认 `wake: null`；只启用 mailbox 工具；native 不可用时停止；保留历史证据和用户私有旧数据。
- Ask first：修改上游 `claude-codex-mcp-bridge`；自动退役或修改已登记身份；初始化或修改真实宿主配置。
- Never：在自动批准会话中绑定唤醒；恢复兼容传输产品路径；把普通邮箱消息当作开发、Git 或配置授权；扫描或迁移旧
  私有邮箱数据来提高验证评级。

## Success criteria

- 按新版 `collab` skill 加入协作的会话，除非用户明确要求，登记时都用 `wake: null`；回归测试锁定这条规则。
- 自动批准会话不能绑定唤醒；无法确认当前会话 ID 时停止，不猜测。
- 当前源码只包含 native 协作路径，宿主工具面受限于消息与身份管理，旧传输数据保持未读未改。
- 文档（skill、运行时说明、`docs/optional-features.md`、`spec/collaboration-messaging.md`）与实现一致。
- 三条最小验证和相关 native 聚焦测试通过；发布后宿主证据单独记录。

## Decisions

用户于 2026-09-28 批准本 Spec，并采用默认：对已经以 `wake: "auto"` 登记的身份，本模块只在文档里提示可以退役，
不做自动处理，也不在 `collaboration-ops` 里新增列出这类身份的检查。用户于 2026-10-04 决定只保留 native，
旧启动器与 token 契约随兼容传输一起退役；唤醒安全默认继续有效。

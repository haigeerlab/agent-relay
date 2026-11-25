# 发版流程

维护者发一个 agent-relay 新版本时照着做。**合并和发版由用户决定**：agent 可以准备发版 PR，打标签、建 Release
之前要用户明确同意。

## 版本号

- 插件版本按 semver，与 Spec Guard 无关；Claude 与 Codex 两份清单的版本必须一致。
- 接口版本在 `plugins/agent-relay/interface.json`，与插件版本分开：删除或改名工具、字段、状态、命令，或收窄已接受的
  输入，是不兼容改动，接口主版本加一；只增加内容时次版本加一（见 [接口文档](docs/collaboration-interface.md) §1）。
  接口主版本变动前先和 Spec Guard 的负责人确认它接受的范围（目前 `>=1.0,<3.0`）。
- 信箱 schema 与委派库 schema 有变化时，在 CHANGELOG 里写明，并说明回滚要连插件一起回滚。

## 发版前

1. 要进这一版的模块 PR 都已合并。看 `gh pr view <编号> --json state,mergeCommit`，再用
   `git merge-base --is-ancestor <PR 最后一个提交> origin/main` 确认它真的在主线上；“已合并”的说法出过错。
2. 问负责验收的协调会话有没有还没给结论的审查；有的话等它的结论再打标签。
3. 能力图里这一版的模块都已勾完：`/spec-guard:map` 没有进行中的模块。
4. 本地跑 `bash scripts/validate.sh`，并确认 `main` 上最新一次 CI 四个组合都通过。

## 发版 PR

一个 PR，标题形如 `chore(release): agent-relay 0.x.y（接口 2.0，信箱 schema 5，委派库 schema 3）`，只改这些（提交与 PR 标题的类型
只能是 feat、fix、docs、chore、test、ci、refactor，hub 的 `commit-format` 规则会拦下 `release:` 这类前缀）：

- `plugins/agent-relay/.claude-plugin/plugin.json` 与 `plugins/agent-relay/.codex-plugin/plugin.json` 的 `version`；
- bridge 的运行时文件有改动时，把 bridge 的版本号（`bridge/src/version.ts`、`bridge/package.json`、`bridge/package-lock.json`
  的两处 `version`）也改成这一版的版本号，并跑 `python3 scripts/bridge-manifest.py`；`agent-relay --version` 和 MCP 报的版本
  就是“运行时来自哪一版”。只改 hooks、skills、文档的发版不改它，免得逼着升级运行时；测试要求它不高于 `plugin.json`
  的版本（模块 `post-090-bridge` D252）；
- `CHANGELOG.md`：把 `[Unreleased]` 的内容移到新版本标题下，写日期。开头一段先说**要不要升级运行时**：
  - bridge 的运行时文件（`plugins/agent-relay/bridge/` 下的 `src/`、`package.json`、`package-lock.json`、`tsconfig.json`、
    `scripts/build.mjs`）有改动，写“bridge 有改动，要 `upgrade --confirm` 升级运行时”；
  - 只改了 hooks、skills、文档，或 bridge 里只改了测试、文档，写“运行时不用升级，更新插件并新开会话即可”；
  - 再写一节“从上一版升级”，列出两个宿主各自的命令；Claude Code 从本地克隆装的，写 `git pull` 之后再跑
    `claude plugin marketplace update agent-relay-marketplace` 和
    `claude plugin update --scope user agent-relay@agent-relay-marketplace` 刷新用户级记录的标签，否则 doctor 报 warn
    （模块 `post-090-docs` D258）；
- `README.md` 与 `README.en.md`：开头“状态”一行的版本号，“安装”里 Codex 的 `--ref v0.x.y`；两份 README 内容要一致，
  这一版改了中文 README 的哪一节，英文版同一节也要改；
- `.agent/state.json` 与模块 `todo.md` 里跟发版有关的勾选。

bridge 目录的文件都登记在 `bridge/UPSTREAM.sha256` 里，安装时逐个文件核对。运行时是否最新只比其中的运行时文件
（上面那五类，见 `native_collaboration_runtime.py` 的 `RUNTIME_FILES`，模块 `runtime-mark-scope`）：bridge 里只改测试或文档，
`status` 的 `bridge.current` 仍是 true，`doctor` 不会要求升级运行时。不论改了 bridge 的哪个文件，那个提交都要同时跑
`python3 scripts/bridge-manifest.py` 并在 `bridge/UPSTREAM.md` 记一行；bridge 新增的文件要归入 `RUNTIME_FILES` 或
`NOT_RUNTIME_FILES`，否则测试会失败。

## 发版

PR 合并后，按顺序调用 `scripts/release.py` 的各个步骤（模块 `release-commands`）。每一步先打几行中文说明，最后一行是一行
JSON：`{"schema": "agent-relay.release/v1", "step", "version", "status", ...}`；`status` 为 `ok`、`preview`、`refused`、
`waiting-on-user`、`failed`，退出码分别是 0、0、2、3、1，`refused` 带一个固定的 `reason`。每一步的结果记在本机
`~/.agent-relay/release/<版本>.json`（不进仓库），后一步读前一步的记录；前一步没有成功记录时报 `needs-<步骤>`。

谁能跑：`check`、`prepare`、`smoke`、`evidence` 只读或只写本机临时目录，autopilot 和 agent 可以自己跑；`publish`、
`install`、`upgrade` 不带 `--confirm` 只出预览，带 `--confirm` 才执行，**要用户明确同意之后**才加 `--confirm`。命令不判断
同意从哪来，这是调用方的责任。

1. `python3 scripts/release.py check --pr <发版 PR 编号>`：确认 PR 已合并、远端 `main` 仍在合并提交、合并提交上的 CI 全部
   通过、两份 `plugin.json` 版本一致、两份 README 的状态行和 `--ref` 是这一版、CHANGELOG 有这一版的章节、bridge 版本不高于
   插件版本、这一版的 tag 还不存在。通过时报出影响：上一个 tag、接口版本从几到几、要不要升级运行时（`runtimeUpgrade`，
   按 `RUNTIME_FILES` 比较 bridge 的改动）。
2. `python3 scripts/release.py prepare --version 0.x.y`：把合并提交的 `.claude-plugin` 和 `plugins/agent-relay` 解到一个新的
   临时目录，写 `MANIFEST.json`（每个文件的 sha256）和 `release-notes.md`（这一版的 CHANGELOG 段落）。不重跑测试：完整测试是
   合并提交上 CI 的四个组合，`check` 已核过。这是 autopilot 不经用户能走到的最后一步（“备好等批”）。
3. `python3 scripts/release.py publish --version 0.x.y`，用户同意后加 `--confirm`：打附注标签 `v0.x.y` 到合并提交、推送标签、
   `gh release create --verify-tag`（标题带接口版本，说明用 `release-notes.md`），再核对远端标签解析到合并提交。标签和
   Release 已经在时重跑直接报 `ok`，不再写。

## 发版后

1. `python3 scripts/release.py install --version 0.x.y`，用户同意后加 `--confirm`：在两个宿主上更新插件。
   - Claude Code 从本地克隆装的：克隆有未提交改动、不在 `main` 或不能快进时拒绝（`clone-not-clean`），否则
     `git pull --ff-only` 到标签所在提交；然后 `claude plugin marketplace update agent-relay-marketplace` 和
     `claude plugin update --scope user agent-relay@agent-relay-marketplace`，刷新用户级记录的标签，否则 doctor 报 warn
     （模块 `post-090-docs` D258）。
   - Codex：先把 `config.toml` 备份到本机记录目录，只把 `[marketplaces.agent-relay-marketplace]` 的 `ref` 一行改成
     `v0.x.y`（段缺失或 `ref` 不唯一时拒绝，文件不动；本地路径来源不改），再 `codex plugin add agent-relay@agent-relay-marketplace`。
   - 最后把两个宿主正在用的副本逐个文件和 `MANIFEST.json` 比对，有缺、多、不同的文件就报 `failed` 并列出来。终端输出可能
     乱序，以安装后的文件为准。
2. `python3 scripts/release.py upgrade --version 0.x.y`：`check` 判定不用升级运行时（只改 hooks、skills、文档，或 bridge 里只改
   测试、文档）时直接跳过。要升级时，**先由用户关掉所有用到信箱的会话**（Claude Code 会话，并用 ⌘Q 退出 ChatGPT）；命令从不
   停 bridge、不退出任何应用。用户同意后加 `--confirm`：还有 bridge 在跑就报 `waiting-on-user`（退出码 3），什么都不改；
   没有在跑的才调用已安装副本的 `native_collaboration_runtime.py upgrade --confirm`。升级失败时只打印 `rollback --confirm`
   和 `recover --confirm` 两条命令，由用户决定是否执行，命令不会自己回滚（README“升级运行时”）。
3. 用户重新打开 ChatGPT、新开 Claude Code 会话，然后 `python3 scripts/release.py smoke --version 0.x.y`：只读跑已安装副本的
   `doctor` 和 `status`。doctor 有 fail 报 `failed`；运行时该升级没升、Claude 插件检查不是 ok、ChatGPT 还没在升级后重开，报
   `waiting-on-user` 并写出用户要做什么；环境类的 warn 按 doctor 给的下一步处理。
4. `python3 scripts/release.py evidence --version 0.x.y [--output <仓库外的文件>]`：把本机记录汇总成一段 Markdown（合并提交、
   标签、Release、影响、两个宿主的副本、运行时升级、冒烟结果、还等用户做的事），缺的步骤会写出来；`--output` 不能在仓库里。
5. 请协调会话在新会话里做真实宿主验收，按 [验收清单](docs/acceptance/checklist.md) 里涉及这一版的条目。
6. 验收中发现的问题进下一版，不改已发布的标签。

### 命令不可用时

`scripts/release.py` 跑不了时（例如本机缺 `gh`），手动做同样的事，前提检查照上面第 1 步逐项核对：

```bash
git tag -a v0.x.y <合并提交> -m "agent-relay 0.x.y"
git push origin v0.x.y
gh release create v0.x.y --verify-tag --title "agent-relay 0.x.y (interface 2.0)" --notes-file <这一版的 CHANGELOG 段落>
```

宿主更新和运行时升级见 README“更新插件”“升级运行时”。

## 撤回一次合并

一个已合并的 PR 要撤回时照着做。`main` 只能经 PR 合入，撤回也走 PR，谁都不能直推。

1. 找到合并提交：`gh pr view <编号> --json mergeCommit`。
2. 从 `origin/main` 切 `autopr/revert-<编号>`，执行 `git revert -m 1 <合并提交>`（本仓库用 merge commit 合并）。
3. 开 PR，标题形如 `chore(revert): <原 PR 标题>`（`revert:` 不是允许的类型，见上文「发版 PR」），写明撤回原因；等 `CI required` 与 `autopilot-admission` 通过，按 F3 合并：用户在对话里说“合并”后由会话合并（见 `CLAUDE.md` 的 autopr 一节）。
4. 被撤回的改动已进了某个发布标签时：不改已发布的标签，按上文发一个补丁版本。bridge 的运行时文件有改动时，用户在本机
   `upgrade --confirm` 到新版本，或关掉所有会话后用 `native_collaboration_runtime.py rollback --confirm` 回到上一个运行时
   （README“升级运行时”）；信箱 schema 变过时要连插件一起回滚。

谁做：agent 准备撤回 PR，用户合并；发版和真实宿主上的回滚由用户做。多久：没发版的撤回约 15 分钟（CI 一轮 3～4 分钟，
加上审和合并）；已发版的再加一次补丁发版和本机升级，约 1 小时。

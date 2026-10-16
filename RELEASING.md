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

一个 PR，标题形如 `release: agent-relay 0.x.y（接口 2.0，信箱 schema 5，委派库 schema 3）`，只改这些：

- `plugins/agent-relay/.claude-plugin/plugin.json` 与 `plugins/agent-relay/.codex-plugin/plugin.json` 的 `version`；
- `CHANGELOG.md`：把 `[Unreleased]` 的内容移到新版本标题下，写日期。开头一段先说**要不要升级运行时**：
  - bridge 目录（`plugins/agent-relay/bridge/`）有任何改动，写“bridge 有改动，要 `upgrade --confirm` 升级运行时”；
  - 只改了 hooks、skills、文档，写“bridge 没变，不用升级运行时，更新插件并新开会话即可”；
  - 再写一节“从上一版升级”，列出两个宿主各自的命令；
- `README.md`：开头“状态”一行的版本号，“安装”里 Codex 的 `--ref v0.x.y`；
- `.agent/state.json` 与模块 `todo.md` 里跟发版有关的勾选。

bridge 目录的文件都登记在 `bridge/UPSTREAM.sha256` 里，运行时是否最新就看这份清单的哈希。所以 bridge 里**哪怕只改一份
文档**，发版后 `doctor` 也会要求升级运行时。只改 bridge 文档的话，等下一次本来就要改 bridge 代码时一起改。改了 bridge 的
那个提交要同时跑 `python3 scripts/bridge-manifest.py` 并在 `bridge/UPSTREAM.md` 记一行。

## 发版

PR 合并后，在合并提交上：

```bash
git tag -a v0.x.y <合并提交> -m "agent-relay 0.x.y"
git push origin v0.x.y
gh release create v0.x.y --title "agent-relay 0.x.y (interface 2.0)" --notes-file <这一版的 CHANGELOG 段落>
```

## 发版后

1. 用户在真实宿主上更新：先把本机克隆拉到新标签，两个宿主都更新插件；bridge 有改动时关掉所有用到信箱的会话，再跑
   `upgrade --confirm`（步骤见 README“更新插件”“升级运行时”）。终端输出可能乱序，以安装后的文件和 `doctor` 为准。
2. `doctor` 各项为 ok（环境类的 warn 按它给的下一步处理）。
3. 请协调会话在新会话里做真实宿主验收，按 [验收清单](docs/acceptance/checklist.md) 里涉及这一版的条目。
4. 验收中发现的问题进下一版，不改已发布的标签。

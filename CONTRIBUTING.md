# 参与开发

给 agent-relay 的维护者和贡献者。使用说明见 [README](README.md)。

## 本地验证

`bash scripts/validate.sh`（先在 `plugins/agent-relay/bridge` 里 `npm ci`，否则 bridge 部分显示 skip）。

## CI

每个 PR 和推到 `main` 的提交都会在 GitHub Actions 的 `macos-15` 上跑同一套验证，组合为 Python 3.9（苹果命令行工具自带）
/ 3.14 × Node 22 / 24，日志里有 doctor 的 `toolchain` 一行，写明实际用的 Python 与 Node。要把它设为 `main` 的必需检查：
仓库 Settings → Branches（或 Rules → Rulesets）→ 为 `main` 勾选 “Require status checks to pass”，选上四个
`Python … / Node …` 检查。是否这样设由维护者决定。

按改动决定跑不跑（`ci-on-demand`）：一个 PR（或推到 `main` 的提交）如果只改了 `CLAUDE.md`、`AGENTS.md`、`spec/`、`tasks/`、
`.agent/` 下的文件，四个检查只打印原因就通过，不跑测试；只要有一个文件不在这几处，就照常跑完整矩阵。名单定义在
[`scripts/ci_scope.py`](scripts/ci_scope.py)，`hooks/test_ci_exempt_guard.py` 保证测试跑到的代码都不读这些路径。每周一 03:00 UTC
在 `main` 上定时全量跑一次，及早发现运行环境里 Python 或 Node 升级带来的问题；随时想全量跑，在 Actions 页面对 CI 点
“Run workflow”。

## 发版与验收

- [发版流程](RELEASING.md)：维护者发一个新版本的步骤与检查。
- [验收清单](docs/acceptance/checklist.md)：真实宿主验收步骤；各次验收记录在 [`docs/acceptance/`](docs/acceptance/)。

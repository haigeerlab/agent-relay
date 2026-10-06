# Todo: packaging

- [x] Task 1: interface.json, relay_status.py, marketplace description, packaging tests — 5 tests (manifest agreement, marker shape, status absent/ready/invalid run exactly as the probe runs it, nothing created); `claude plugin validate` on marketplace and plugin: passed, no warnings; live `relay_status.py` → ready false with the setup hint. 225 tests green
- [x] Task 2: README and .gitignore, D8 phrase test — README sections: 能做什么, 需要什么, 安装 (both hosts + first-use steps), 怎么用 (5 spoken examples), 授权与安全 (wake null, auto-approve never binds, per-item confirmation, no automatic permission edits, project-level allow, mail is data, finding 7 Codex approval cost), 不做什么, 与 Spec Guard 的关系, 卸载, 文档, 致谢 (upstream bridge MIT). D8 phrase test green; `.gitignore` covers `.claude/settings.local.json`. 226 tests. Open: agent-relay has no LICENSE file yet (Spec Guard is MIT) — for the user at the gate
- [x] Checkpoint (gate): approve the host install commands — approved by the user at Plan review 2026-10-07
- [ ] Task 3: install on both hosts, Spec Guard probe, Codex cleanup
- [ ] Checkpoint (gate): module review; never pushed

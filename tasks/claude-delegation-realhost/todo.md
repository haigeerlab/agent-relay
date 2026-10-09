# Todo: claude-delegation-realhost

- [x] Task 1: trace the H2 record to its `_deliver` branch — read only (real delegation store, both transcripts under `~/.claude/projects/-Users-vilin-Documents-design-relay-integration/`, the coordinator's controller outputs from the Codex rollout):
  - Both runs (`cx2cc-readme` d849dfa6 failed, `cx2cc-readme2` a08f49a0 succeeded) started with `deferred_tools_delta {pendingMcpServers: ["agent-relay"], toolSearchAbsent: true}`. The success made a `Read` first; while it ran, a delta added the ten `mcp__agent-relay__*` tools and it registered. The failure ended its first turn after 8 s **without any tool call**, saying the tools were missing — the delta only arrives on a later step, so it never came.
  - `status` then saw the host `failed` (not `done`), so `continue` took the D49 re-send by stop-and-resume. `claude --resume` wrote a new transcript (6472d974, a copy of the first turn plus the new one): the resumed turn again ended without a tool call, same answer. So the resumed process had the same problem; nothing points at the regenerated MCP config.
  - The record went `unknown` (`host-result-unknown`) in that resume `_deliver`. Candidates to pin with a test in Task 3: the post-resume check `confirmed.session_ref != claim.host_session_ref` if the resumed session reports a new id, or an uncertain `_run`. The public result of that continue put the turn ref (`claude-reregister-…`) in `hostStatus` — a field mix-up (coordinator item b), fixed in Task 3.
  - Consequence for D182 (found while building): `ToolSearch` alone may not keep the turn alive; the prompt must also say: if the mailbox tools are not listed yet, do not end the turn — start the task with the allowed read tools and register as soon as they appear. Real check (b) and a new (c) (a record left at `mailbox-registration-missing`, then `continue`: the re-send turn gets the tools) decide it.
- [ ] Task 2: `done` is a stopped Claude session (D181)
- [ ] Task 3: the delegated session can load its mailbox tools (D182)
  - Coordinator, 2026-10-10: the re-send (D49) turn uses the same wording as the first — one allowed `Read` of an in-scope file first, then register. Real checks (b) three cold-start creates and (c) the re-send turn record, per attempt, whether it registered and how many seconds it took. The PR description lists this prompt change separately (added after the spec was approved).
- [ ] Task 4: truthful prune help (D183)
- [ ] Checkpoint (report): local validation and real checks
- [ ] Task 5: PR and CI
- [ ] Checkpoint (gate): module review

# agent-relay real-host acceptance checklist

The single authority for real-host acceptance: the translation run (brief phase 2), every hardening module
(phase 3), and both integration rounds (phase 4). Each run copies [record-template.md](record-template.md) to
`docs/acceptance/<date>-<run>.md` and fills one row per item.

**How to judge.** *Current* is the expected result under the current column of
[collaboration-interface.md](../collaboration-interface.md) (round 1, translation version). *Target* is the
expected result under its hardening-target column (round 2). Items marked 【加固】 exist only after the named
hardening module and are skipped in round 1. "Same as current" means the hardening does not change the item.

**Rules for every run.**
- Test identities are named `ar-acc-<run>-<role>-<host>`; delegated sessions get controller-made names. Message
  bodies of any other identity are never read.
- Evidence is message ids, state fields, command exit codes, and screenshots of host UI; never message bodies of
  real work.
- Host or project permission changes are made by the user, listed in the record, and reverted in section E.
- Run `scripts/acceptance/preflight.sh` first and paste its output into the record.

## A. Setup and preflight

| Id | Host pair | Steps | Current | Target |
|---|---|---|---|---|
| A1 | — | Run `preflight.sh --design <design project>` from the checkout the hosts load; record Claude Code and Codex versions, agent-relay source and commit on each host | Versions and source recorded; agent-relay installed from the local marketplace path | Same, plus `native_collaboration_runtime.py doctor` has no `fail` (warnings read with their next step) — `ops-commands`; every copy a host loads is `current` (a `STALE` copy is refreshed with the printed command before the run; Claude install records of a directory marketplace are listed as not loaded: round 2 R2-5, R2-11) — `acceptance-kit-round2` 【加固】 |
| A2 | Codex | Read Codex `approvals_reviewer` and the App approval selector | Recorded by hand; `guardian_subagent` counts as auto-approval (finding 1), so set the selector to 请求批准 for the run and restore it in E; under 请求批准 every mailbox call of a woken Codex turn waits for the operator to approve (finding 7) | Bind refused under `guardian_subagent` or `approval_policy = "never"` (unreadable config fails closed), and pings to an already bound Codex session held with a notice to the sender — `identity-check` 【加固】; the approval cost is documented in the README — `packaging` |
| A3 | — | List the sessions the user must open (project × host) for this run, wait until the user confirms they are open | List written in the record before any message is sent | Same as current |
| A4 | Claude | Start background Claude test sessions with the command `preflight.sh` prints: the prompt first (`claude "<prompt>" --bg …`, round 2 R2-3), `--permission-mode dontAsk`, the `allow (base)` list — or `allow (routing)` for sessions that take part in D8/D9 (round 2 R2-8) — one quoted argument per rule, never `--tools ""` | Sessions start and can call `ListAgents`, `SendMessage` and the ten mailbox tools without a prompt (finding 6) | Same; a session that would block on a prompt is reported instead of hanging — `ops-commands` 【加固】 |
| A5 | Claude, Codex | Register one wake-bound identity per test session (Claude `wake: "auto"`, Codex `{app, sessionId}`) | `bridge_agents` lists each identity with its wake target (baseline item 1) | Same, plus `bridge_sessions.whoami` shows host, session name, project — `ops-commands` 【加固】 |

## B. Messaging

| Id | Host pair | Steps | Current | Target |
|---|---|---|---|---|
| B1 | Claude → Claude | A sends to B through `SendMessage`; B replies with a token | Host-native; B's reply reaches A; nothing copied into the mailbox (baseline item 2) | Same as current |
| B2 | Claude → Claude | Reverse direction, second round | Pass both ways (baseline item 3) | Same as current |
| B3 | Codex → Codex | D starts two turns on C through `list_threads`, `send_message_to_thread`, `wait_threads` | Both turns complete and both replies are read (baseline item 4); C's standing prompt must not restrict it to its inbox | Same as current |
| B4 | Claude → Codex | A sends to D through the mailbox; D is woken and replies; A is woken | No send warnings; D replies; A woken and acks (baseline item 5) | `bridge_send` / outbox show `deliveryState` moving `queued → sending → accepted`, not just enqueued — `delivery-state-machine` 【加固】 |
| B5 | Codex → Claude | D sends to idle B twice; B replies each time | The same idle Claude session is woken twice, one attempt each (baseline item 6) | Same, and the wake job reaches `acknowledged` after ack (finding 5); the message reads `accepted` — `delivery-state-machine` 【加固】 |
| B6 | any → unbound | Send to an identity registered with `wake: null` | It is not woken; the message waits in its inbox (baseline item 10, not separately exercised before) | Same as current |
| B7 | Claude, Codex | Try to bind wake in a session running with auto-approval | Binding is refused | Codex: refused by the bridge under `guardian_subagent` or `never`, with the 请求批准 next step; Claude: the bridge cannot see the permission mode, so the skill rule stays (Claude also holds cross-session messages in bypass) — `identity-check` 【加固】 |
| B8 | any | Reply to a message as an identity that is not its recipient | Accepted (sender is free text today, gap g) | Refused ("Only <recipient> … may reply"); sending as a name another session registered is refused too — `identity-check` 【加固】 |

## C. Delegation

Run once with a Claude origin and a Codex target, once with a Codex origin and a Claude target.

| Id | Host pair | Steps | Current | Target |
|---|---|---|---|---|
| C1 | both ways | Check prerequisites with `permissions`; create a session with a safe intent | Missing project allow rules give `held` with the prerequisite named (baseline item 8); after the user adds them, create gives `created`/`completed` | Same as current |
| C2 | both ways | Exact result return to the origin | The result arrives in the origin's mailbox, `resultDelivery=enqueued`, and wakes the origin (baseline items 7, 9) | Same as current |
| C3 | both ways | Same-session second round with `continue` | Claude → Codex passes; Codex → Claude may report `target-busy` while idle (finding 4); on Claude Code 2.1.291 a Claude target in a git worktree is created `unknown` and round two refuses (round 1 finding 7) | Second round passes both ways, with the Claude target once in a plain repository and once in a git worktree — `delegation-fixes`; every Claude-target result returns through the mailbox (round 2 R2-6: three runs each, plain repository and worktree, quick task) — `round2-fixes` |
| C4 | both ways | Read-only intent asked to write | Refused, tree clean (baseline item 7; not run Codex → Claude before) | Same as current |
| C5 | both ways | Stop with `cancel` | `cancelled` | Same as current |
| C6 | both ways | Create two sessions with the same name; query and cancel each by short id | `session-name-ambiguous` with short ids, each queryable with `--disambiguator` | Same as current |
| C7 | both ways | Create while a prerequisite is missing, then create again with the same name | A held create leaves a named envelope that makes the name ambiguous and cancels as `unknown` (finding 3) | The second create is found by name without a disambiguator; the held one cancels as `cancelled` (by short id) — `delegation-fixes` |
| C8 | any | Pass an ISO date to `--expires-at` | Exits 2; only integer epoch seconds work (finding 2) | ISO 8601 with an offset accepted (documented in the session-delegation skill); a time without an offset exits 2 naming the format — `ops-commands` 【加固】 |

## D. Integration (brief phase 4)

| Id | Scope | Steps | Current | Target |
|---|---|---|---|---|
| D1 | 4.1 design project, agent-relay only | Install agent-relay alone; open Claude Code and Codex sessions | Plugin loads on both hosts; no Spec Guard hook, skill, or convention block is present | Same, plus `doctor` passes 【加固】 |
| D2 | 4.1 | Check identity in each session | Host, session name, and project are correct | Same, through `bridge_sessions.whoami` 【加固】 |
| D3 | 4.1 | Claude Code ↔ Codex in the same project, both directions | Messages and replies arrive (B4, B5) | Same as B4/B5 targets |
| D4 | 4.2 spec-guard-plugin, split Spec Guard + agent-relay (project scope) | Run Spec Guard's workflows (phase injection, verify-artifacts, add-module, Proposal, ledger) | Same results as Spec Guard's baseline suites | Same as current |
| D5 | 4.2 | Spec Guard collaboration calls | Only through `agent_relay_probe.py` and agent-relay skill names; Spec Guard's boundary check passes | Same as current |
| D6 | 4.2 | `/spec-guard:collaboration` with agent-relay installed, then temporarily uninstalled | Hands off to agent-relay; without it, prints the not-installed message and the workflow continues | Same as current |
| D7 | 4.2 | Legacy Spec Guard collaboration state present | Migration guidance; backup made first; no data lost | Same as current, also with macOS `/usr/bin/python3` 3.9 (round 2 R2-9) — `round2-fixes` |
| D8 | 4.3 cross-project, four host pairs | Say "去 <宿主> 里找设计项目的会话，跟它联调" (Claude test sessions started with `allow (routing)`, which lets the selector run) | The target session is found; same-name sessions are disambiguated | Same as current |
| D9 | 4.3 | Two-way message, then a design artifact handed over by path (Claude receivers started with `allow (routing)` from `preflight.sh --design <design project>`, which adds the Read rule) | Reply returns to the sender; the artifact is passed by reference, not content, and the receiver confirms it read it | Same as current |
| D10 | 4.3 | Idle wake and repeated wake; delegation create, second round, stop | As B5 and C1–C5 | As B5 and C3 targets |
| D11 | 4.3 | Authorization negatives | Unbound not woken; auto-approved cannot bind; read-only refused | Same, plus guardian detection 【加固】 |
| D12 | 4.3 | Close the target session during delivery | — | Message marked `unknown`, never replayed — `delivery-state-machine` 【加固】 |
| D13 | 4.3 | Let a queued message pass its expiry | — | Marked `expired`, not returned by default, never delivered later (D2) — `delivery-state-machine` 【加固】 |
| D14 | 4.3 | Send twice with the same retry key | — | One message, the retry reports `duplicate: true` and pings nobody; a different body with the same key is refused with a message naming the stored id and saying no resend is needed; the same reply (`replyTo`) sent twice is stored once on the original's thread — `idempotency` 【加固】 |
| D15 | any | Two senders to one recipient while another recipient is offline | — | Each recipient's pings go out one at a time oldest first, the online recipient is not delayed by the offline one, and a send over `BRIDGE_MAX_PENDING_PER_RECIPIENT` is refused with a clear message (warning at 80 %) — `durable-ordering` 【加固】 |
| D16 | any | Send a body from a file containing shell metacharacters | — | Sent with `bridge_send.bodyFile`, the body arrives byte-identical — `ops-commands` 【加固】 |
| D17 | any | Uninstall agent-relay from both hosts | — | Host settings backed up before change (`backups/<UTC>/host-config/`, owner-only); Codex table removed even with 始终允许 approval subtables (round 1 report finding 6); Claude entry removed, deny rules removed only from a terminal with every Claude Code session closed (kept, with the command printed, otherwise: round 2 R2-10); runtime build removed with `uninstall --confirm`; `mailbox/` history kept; `doctor` shows not attached and uninstalled — `safe-uninstall` 【加固】 |

## E. Cleanup

| Id | Steps | Expected |
|---|---|---|
| E1 | Stop background test sessions; cancel delegated sessions | None left running; any `unknown` cancel recorded |
| E2 | `scripts/acceptance/cleanup.sh <run>` (preview), then with `--confirm`; retire this run's delegated identities by exact name with `native_collaboration_retire.py --name <name> --confirm-retire` | Only `ar-acc-<run>-*` and the delegated identities listed in the record retired, history kept |
| E3 | Revert host and project permission changes listed in the record (Codex approval selector, temporary allow rules) | Each reverted change listed with who reverted it |
| E4 | Remove test artifacts from the design project's agreed temporary directory | Removal reported; no other design-project file changed |
| E5 | Confirm the guide plugin versions | Claude and Codex `spec-guard` unchanged from the start of the run |

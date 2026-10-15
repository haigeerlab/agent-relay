# Spec: codex-request-via-mailbox

## Objective

First module of 0.6.9 (hooks and skills; no bridge change). From a problem report relayed on 2026-10-16 by a Codex monitoring
session (mailbox name `spec-guard-monitor`), with the user's consent to hand it over, and the
user's decision the same day ("确认，七条假设通过，按 A 做"): when one Codex task gives work to another Codex task, the
answer is often lost, because the native Codex route returns it only to a sender that is still waiting for it.

Readers: the user; the round-2 coordinator (reviews, re-checks after release); the reporting session.

## What exists today (main 33936e0, v0.6.8)

- `skills/session-routing/SKILL.md` ("Codex → Codex 原生路径", lines 128–162): same-host Codex pairs use the App's
  thread tools. The target answers inside the turn; the source must fetch the result with `wait_threads` or
  `read_thread`. The skill forbids asking the target to send back across tasks and forbids copying the answer into the
  mailbox.
- `hooks/session_routing.py` `select_route`: for a same-host pair with native capability `available` and nothing
  attempted, the decision is always `dispatch` on `host-native-<host>` (`primary-native`). The mailbox is used for the
  same host only when native capability is `unavailable` (`native-capability-unavailable`, `fallbackFrom`).
- The mailbox already returns an answer to the sender: a reply with `replyTo` lands in the sender's inbox and pings it.
- Reported evidence (2026-10-15 to 10-16): the coordinator of a multi-session project (Codex) sent 193 native requests to four Codex
  development tasks; none of the answers came back through the mailbox. Three incidents: answers written only in the
  target task while the coordinator thought nothing had arrived (10-15 13:31); the coordinator ended its turn two
  seconds before the API task finished, and the whole line stalled until the user stepped in (10-16 01:05–01:09); three
  more times on 10-13 the coordinator needed a reminder to fetch results. Over the same period, 300+ mailbox messages
  between the coordinator and two Claude review sessions lost no answer.
- The bridge cannot see Codex native messages or the end of the target's turn (it does not read Codex private state),
  so it cannot forward a native answer afterwards (option B in the report, rejected).

## Assumptions (accepted by the user 2026-10-16)

1. **Only Codex → Codex changes.** When both tasks have joined the mailbox and the source is giving work (not asking
   something it waits for right now), the request and the answer go through the mailbox, the answer with `replyTo`.
   A question the source waits for in the same turn still goes native. "Joined" here means joined **with wake**: both
   names are bound for background pings (round-2 review of #104). A name that is registered but not bound counts as not
   joined: a mailbox message to it waits unread until it expires (seen with `codex-delegate-1y2s6ih8`, #633 and #635),
   and an unbound source would never be woken by the answer.
2. **The source decides which it is, from what the user said.** When unsure, the mailbox: a slower answer costs less
   than a lost one.
3. **Either side not joined:** still native, and the user is told that the answer to a work request may not be picked
   up, suggesting both sides join.
4. **Claude → Claude unchanged:** a native Claude message starts a turn in the target, and no lost answers were
   reported there.
5. (module `upgrade-codex-restart-check`.)
6. **Release:** skills and hooks only, 0.6.9, no `upgrade --confirm`; update the plugin and open new sessions.
   Interface stays 2.0 (an optional selector fact and one more route reason, as D192 added `nextStep`); mailbox schema 5
   and delegation store schema 3 unchanged.
7. **Process as usual;** the round-2 coordinator reviews the PRs.

Trade-off accepted (round-2 review of #104): a mailbox request to a Codex task that is busy waits until it is idle
(the busy retry window), while a native message may enter its current turn at once. This is expected, not a defect.

## Decisions

- **D195 a Codex task that gives work to another Codex task uses the mailbox when both have joined; native stays for
  questions answered in the same turn; unsure means mailbox; not joined means native with a warning.** Assumptions 1–4.

## Design

- `select_route` takes three more, optional facts: `exchange`: `ask` (the source waits for the answer in this turn),
  `assign` (the source gives work and may end its turn), or `unknown`; absent means `unknown`. `originWake` and
  `targetWake` (booleans): the name is bound for background pings; absent means `false`. Every other fact and rule is
  unchanged.
- Same host Codex, native not attempted yet, `exchange` not `ask`:
  - bridge ready, both joined and both wake-bound → `dispatch` on `agent-relay-bridge`, `routeReason: "codex-work-via-mailbox"`
    (no `fallbackFrom`: this is the chosen route, not a fallback);
  - otherwise → the native decision as today, plus `nextStep`: a sentence telling the user that an answer to a work
    request may not come back to this task, and the existing join sentence ("加入本机联调并允许唤醒，名字叫 <名字>",
    D192) for whichever side is missing.
- `exchange` is ignored for Claude → Claude and cross-host pairs. Once a native dispatch was attempted (`accepted`,
  `unknown`, `rejected`) the route stays native exactly as today: never two sends.
- Skills: `session-routing` says when to pass `assign`, `ask` or nothing, and that on `codex-work-via-mailbox` the
  source sends with `bridge_send` and the target answers with `replyTo` (the existing `collab` flow); the sentence that
  forbids copying into the mailbox stays true (the request is never sent twice). `collab` gets one line pointing back.
- `docs/collaboration-interface.md`: the selector row lists `exchange`; the Codex ↔ Codex row says work requests use
  the mailbox when both joined.

## Requirements

1. Red first, `hooks/test_session_routing.py`: the four `exchange` cases for Codex/Codex (assign, unknown, absent →
   mailbox; ask → native) with both joined, both wake-bound and the bridge ready; not joined, joined but not
   wake-bound (either side), or bridge not ready → native with the `nextStep`; `accepted`/`unknown` native dispatch stays `observe`/`reconcile`; Claude/Claude and cross-host results
   unchanged whatever `exchange` says; an invalid `exchange` value is refused.
2. Red first, skill tests (`test_skill_entrypoints.py` or the routing entry tests): the skill names the three values and
   the new route reason, and quotes the `nextStep` sentence word for word.
3. CHANGELOG `[Unreleased]` (plugin update only, no runtime upgrade).
4. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; CI green.

## Boundaries

- Never: send a request twice; read Codex private state; copy a native answer into the mailbox; change Claude → Claude.
- Ask first: any change to the selector's existing facts or outcomes.

## Acceptance (coordinator, after 0.6.9)

- Two joined Codex tasks: a work request goes through the mailbox and the answer wakes the source after it ended its
  turn; a direct question still goes native; with one side not joined, the warning is shown.

## Open questions

- Whether the user's rule "the coordinator and the four lines always use the mailbox" can be dropped: the user decides
  after acceptance.

# Spec: join-hint-on-missing-target

## Objective

Only module of 0.6.6 (plugin hooks and skills; no bridge change). From the user on 2026-10-12, relayed by the round-2
coordinator and confirmed here ("确认，六条假设通过，名字由会话来起"): when a session is asked to contact another
session by name and that session has not joined the local mailbox, the flow ends without saying what to do. The user
wants the one sentence to paste into the target session.

Readers: the user; the round-2 coordinator (reviews, re-checks after release).

## What exists today (main 92ed796, v0.6.5)

- What happened (the coordinator, this Mac, 0.6.5): asked to reach a Codex session titled "LIVE-SAAS｜前端基础架构".
  `bridge_agents` had no such name; `session_delegation_control.py resolve --name` returned no match;
  `session_routing.py select` with `targetResolution: "missing"` returned
  `{"action":"stop","routeReason":"target-missing"}` and nothing else. The coordinator found the sentence only by
  reading the skill. After the user said it in the target session (name `live-saas-fe`), message #257 woke Codex and
  the reply #258 came back in 53 seconds.
- `hooks/session_routing.py` `select_route` stops for a target that cannot be reached with three reasons:
  `target-missing` (the name resolves to nothing), `target-not-joined` (cross-host, resolved but not joined) and
  `native-unavailable-target-not-joined` (same host, native path unavailable, not joined). `_decision` returns
  `schemaVersion`, `action`, `transport`, `routeReason` and optionally `fallbackFrom`.
- `nextStep` already exists as an optional field of the public outcome (`validate_public_outcome`, text of at most
  240 characters). `select` never sets it.
- `skills/session-routing/SKILL.md` says for `stop`: "报告 `routeReason` 和一条最小下一步", and for zero matches "说明
  目标不可见及一条加入/创建建议" — the sentence itself is nowhere in a result. `skills/collab/SKILL.md` binds a wake only
  when the user says "加入并允许唤醒" in that session; both hosts use this skill.
- A mailbox name (`bridge/src/addressing.ts` `agentNameProblem`): not empty, no leading or trailing spaces, not `*`
  or `bridge`, not shaped like a session id (UUID), at most 128 characters.

## Assumptions (accepted by the user 2026-10-12)

1. **The selector gives the next step.** For the three reasons above, `select` adds `nextStep`: fixed text holding
   the sentence to say in the target session. The skill tells the session to pass it on as it is. Tests guarantee
   the field is there for these reasons.
2. **Both cases:** the name resolves to nothing, and the name resolves but the session has not joined.
3. **One sentence for both hosts:** `加入本机联调并允许唤醒，名字叫 <名字>` — the wording `collab` acts on in Claude Code
   and in Codex alike.
4. **The session picks the name, not the selector.** The text carries the placeholder `<名字>` and the rule in a few
   words; the skill tells the session to replace it with a short, readable mailbox name of its own choosing (ASCII
   letters, digits and hyphens, for example `live-saas-fe`) before showing the sentence. What the user typed (often
   a session title with Chinese and symbols) is never passed to the selector or put on a command line because of
   this module: the selector's input is unchanged and has no name field.
5. **Not built:** listing the sessions of Codex or Claude that have not joined. That would make the mail layer read
   the hosts' session lists, against "the user creates the session and joins it with one sentence".
6. **Release:** hooks and skills only. 0.6.6; takes effect after updating the plugin and opening a new session. No
   `upgrade --confirm`. Interface stays 2.0, mailbox schema 5, delegation store schema 3; route `schemaVersion`
   unchanged (an optional field is added to the `select` result; `ambiguous` and every other reason are unchanged).

## Decisions

- **D192 a stop for a target that has not joined carries the sentence that joins it.** Assumptions 1–5.

## Requirements

1. Red first, `hooks/test_session_routing.py`: for `target-missing`, `target-not-joined` and
   `native-unavailable-target-not-joined` the result has `nextStep`; it contains the exact sentence
   `加入本机联调并允许唤醒，名字叫 <名字>`; it is at most 240 characters and passes `_text` as the public outcome's
   `nextStep` does; it is the same constant for both target hosts. No other reason (`target-ambiguous`,
   `authorization-*`, `bridge-*`, `origin-not-joined`, the dispatch/observe/reconcile results) gains the field. The
   selector still rejects unknown input fields (no name can be passed in).
2. `skills/session-routing/SKILL.md`: on `stop` with `nextStep`, say it to the user as it is, with `<名字>` replaced
   by a name the session picks under the rule in assumption 4, and say that the user pastes it into the target
   session; never put the user's wording for the target into a command because of this step. `skills/collab/SKILL.md`
   line on zero matches gives the same sentence. Entry tests (`test_session_routing_entry.py`,
   `test_collab_entry.py`) assert the sentence is in both skills and that the selector's constant and the skills'
   sentence are the same text.
3. CHANGELOG `[Unreleased]`: what changed, "update the plugin and open a new session", no runtime upgrade.
4. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; CI green.

## Boundaries

- Always: the sentence is a constant in one place; tests compare the skills against it.
- Ask first: any wording change to the sentence itself after this spec.
- Never: read a host's session list; generate a name from the user's text in the selector; add a name field to the
  selector's input; touch the bridge.

## Acceptance (coordinator, after 0.6.6)

- In a new session with the 0.6.6 plugin: ask to contact a session that has not joined. The answer contains the
  sentence with a concrete, valid name in place of `<名字>`. Pasting it into the target session joins it and a
  message then gets through. Claude Code and Codex as the asking host, each once.

## Open questions

None. Accepted by the user on 2026-10-12; spec review by the round-2 coordinator pending.

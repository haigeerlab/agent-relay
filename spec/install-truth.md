# Spec: install-truth

## Objective

Second module of 0.6.2, from the same real-host acceptance of 0.6.1 (2026-10-10): what the user is told about which
plugin copy is running, and what agents are told about tool arguments, must be true.

- **M1.** Claude desktop (Code tab) sessions still ran the 0.5.2 plugin from Claude's plugin cache after the 0.6.1
  upgrade (old skills: host-native, no prune), while `claude --bg` sessions loaded 0.6.1 from the clone
  (`readFromFolder`). The 0.6.1 CHANGELOG said a clone install needs nothing more on the Claude side — wrong.
  `claude plugin list` shows 0.1.0 / 0.5.2 versions, which misleads.
- **L2.** session-routing does not list the allowed values of `authorizationState` and the other selector fields; a
  session sent `"direct-user-request"` and was refused as invalid.
- **L3.** A session got `bridge_register`'s argument names wrong on its first call.
- **L5.** When an old name is held by a stopped session, the skill should suggest a new name as the default next step
  (takeover still needs the user).

Readers: the user; the round-2 coordinator.

## Assumptions (accepted by the user 2026-10-10)

1. **M1 docs.** README "升级" and the CHANGELOG upgrade steps say, for every install kind, that the Claude side needs
   `claude plugin marketplace update agent-relay-marketplace` and `claude plugin update agent-relay@agent-relay-marketplace`
   and a restart of open Claude sessions (desktop Code tab included); the `[0.6.1]` section gets a correction note.
   Written only after a check on this Mac, run with the user's consent (it changes their Claude plugin install): after
   the two commands, does a 0.6.x directory appear under Claude's plugin cache, and does a reopened desktop Code-tab
   session load it? If not, the docs say what does work, as measured.
2. **M1 doctor.** `doctor` gains a read-only check `claude-plugin`. Measured by the coordinator (2026-10-10): one
   user-scope entry carried both `readFromFolder` = the clone (0.6.1) and `installPath` = the cache's 0.5.2 directory;
   desktop Code-tab sessions loaded `installPath`, `claude --bg` sessions `readFromFolder`; the listing's own `version`
   field (0.1.0 / 0.5.2) is not trustworthy. So for every enabled agent-relay entry the check reads the version from
   `<installPath>/.claude-plugin/plugin.json` (and, when present, from the `readFromFolder` copy too), never the
   listing's `version`; any copy that differs from the plugin doctor runs from is `warn`, naming which copy and giving
   the two update commands and the restart as next step. Unavailable `claude` → `skip`. Nothing is written.
2a. **Measured while building (2026-10-10; the user chose this rule the same day).** With the user's consent the
   update was run on this Mac and new sessions were started with the desktop app's own binary (2.1.293,
   `CLAUDE_CODE_ENTRYPOINT=claude-desktop`, `--setting-sources user,project,local`, stream-json like the Code tab) and
   with the CLI (2.1.295), in relay-integration (local-scope entry → cache `0.1.0`) and in a folder with no entry: every
   one loaded `readFromFolder` (the clone, 0.6.1), per the session's `init` plugin list and the skill's base directory.
   The 0.5.2 seen in acceptance came from a desktop session started on 2026-10-07 and still open on 2026-10-09: a session
   keeps the copy it started with. So the check compares only the copy a new session loads — `readFromFolder` when the
   entry has one, else `installPath` — and warns only when that copy differs; stale `installPath` copies that are not
   loaded are noted in the detail; the detail always says sessions started before an update keep their copy until
   restarted. `claude plugin update` without `--scope` updates only the current folder's local entry; the user entry
   needs `--scope user`. Local entries left on old cache copies (four of them for deleted folders) are left alone and
   only reported (the user, 2026-10-10).
3. **L2.** session-routing lists each selector field's allowed values, taken from `session_routing.py`, and a skill
   guard test fails when the code's set and the skill's list differ.
4. **L3.** collab gives one literal `bridge_register` call per host (`{agent, wake}`; Codex with `host`).
5. **L5.** collab: when a name is held by a stopped session, suggest a new name first; offer `takeover` only if the
   user wants that exact name.
6. CHANGELOG `[Unreleased]`; the 0.6.2 release notes repeat assumption 1's steps.

## Decisions

- **D184 the Claude side is updated and checked.** Assumptions 1 and 2.
- **D185 skills give exact arguments.** Assumptions 3–5.

## Requirements

1. Red first: doctor's `claude-plugin` check on fixture listings — every copy matching is ok; the measured shape
   (`readFromFolder` 0.6.x, `installPath` 0.5.2, listing `version` 0.1.0) warns about the `installPath` copy with both
   commands; a listing `version` that disagrees with the files is ignored; no `claude` binary skips; malformed JSON skips
   with a reason.
2. Red first (skill guards): selector field values match the code; collab has the two `bridge_register` examples and the
   rename-first advice; README and CHANGELOG name both Claude commands and the restart.
3. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Ask first: running `claude plugin marketplace update` / `claude plugin update` on this Mac for the assumption-1 check.
- Never: edit Claude's plugin cache by hand; doctor only reads.

## Acceptance (coordinator, after 0.6.2)

- After the documented steps, a desktop Code-tab session loads the new skills; doctor's `claude-plugin` is ok.
- A2: whether macOS actually showed the approval notification (bridge side already passed).

## Open questions

None. Accepted by the user on 2026-10-10 (reviewed by the round-2 coordinator, 86dbbf7).

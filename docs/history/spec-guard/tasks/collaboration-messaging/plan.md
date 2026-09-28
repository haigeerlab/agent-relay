# Plan: collaboration-messaging

Proposal: `spec/proposals/collaboration-messaging.md`

## Overview

Deliver the accepted `collaboration-messaging` module as a private same-Mac mailbox for Claude Code
and Codex. The implementation uses a pinned open-source transport and adds only the runtime safety,
host adapters, recovery controls, and one-step Agent experience required by the module Spec.

This promotion commit establishes the Capability Map row, module Spec, and this Plan only. Runtime,
adapter, skill, test, and acceptance artifacts remain a separately reviewed delivery change.

## Architecture decisions

- Reuse `cross-agent-teams-mcp@0.8.6`; do not implement a second message server or fork its
  protocol.
- Keep one hidden local transport namespace instead of introducing project groups, ownership, task
  assignment, or access-control abstractions.
- Keep token material in private user files and child environments. Repository and host config
  contain only non-secret references.
- Preserve native Codex Desktop and ChatGPT in Chrome by treating it as a persistent mailbox, not a
  managed app-server with guaranteed wake-up.
- Let the Agent resolve human aliases from visible self-description. Transport uniqueness is fixed;
  human-name interpretation remains flexible and ambiguity-safe.
- Keep daily collaboration and explicit operator actions as separate skills.

## Implementation slices

### Slice 1: Private fixed runtime

Implement strict configuration parsing, explicit initialization, pinned XATS startup, health
diagnostics, and optional per-user launchd service management.

**Acceptance:** loopback only; private directory and token permissions; no token in argv, plist,
host config, logs, or diagnostics; unsafe and unknown existing state fails closed.

**Verify:** runtime fixtures, launchd contract tests, health and recovery tests.

### Slice 2: Narrow Claude and Codex adapters

Generate no-secret host configuration. Use Codex `http_headers_helper` and a fixed Claude stdio
bridge whose child environment receives the token.

**Acceptance:** both hosts can register, list, send, read, acknowledge, and unregister; adapters do
not expose Ticket, Git, Issue, or requirement-write tools; native Codex retains ChatGPT in Chrome.

**Verify:** adapter fixtures plus real ordinary Claude Code and native Codex Desktop mailbox checks.

### Slice 3: Self-description and one-step daily entry

Add the `collab` skill and compatible Claude command surface. Lazily register the current session,
generate a unique transport identity, show a minimal directory, and resolve user-supplied names
only when one candidate matches.

**Acceptance:** no team, PID, agent type, project path, UUID, or raw tool name is requested from the
user; zero and multiple matches never send silently; project metadata remains descriptive only.

**Verify:** entry contract tests and real same-project/different-project Claude↔Codex exchanges.

### Slice 4: Recovery and honest delivery states

Separate mailbox persistence, read acknowledgement, and best-effort wake-up. Provide explicit
status, service recovery, and exact stale-identity cleanup paths.

**Acceptance:** an unavailable endpoint yields one accurate next step; cleanup requires an exact
UUID; no command guesses a process, restarts a healthy service, deletes messages, or claims a read
that did not occur.

**Verify:** offline, stale PID, daemon restart, unknown recipient, unread message, and cleanup
fixtures; real host restart checks.

### Slice 5: Delivery verification

Run focused suites, repository validation, Codex smoke self-test, and the recorded real-host
acceptance journey. Review the final diff for token, user-path, app-server, project-group, and hidden
write regressions.

**Acceptance:** implementation matches the module Spec; Capability Map and Proposal evidence remain
unchanged in the delivery change; no unrelated cleanup is included.

**Verify:**

~~~text
python3 -B plugins/spec-guard/hooks/test_collaboration_runtime.py
python3 -B plugins/spec-guard/hooks/test_collab_entry.py
/bin/bash scripts/validate.sh
/bin/bash evals/codex-plugin-smoke.sh --selftest
git diff --check
~~~

## Dependency graph

~~~text
private runtime
      ↓
host adapters
      ↓
self-description + one-step entry
      ↓
recovery + honest delivery states
      ↓
full delivery verification
~~~

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Token disclosure | Private files, child-only environments, no-secret config, output and argv tests. |
| Over-modelled collaboration | One hidden namespace; metadata is descriptive; no routing framework. |
| Mailbox mistaken for real-time chat | Report write, wake, and read as distinct states. |
| Host behavior changes | Keep native Desktop mode; require separate approval for channel or app-server modes. |
| Unsafe recovery | Fail closed and require an exact UUID for the only destructive registry action. |
| Scope leaks into tracker or Git | Keep messaging tools transport-only and review the final diff for write paths. |

## Checkpoints

- Promotion contains exactly the Capability Map, `spec/collaboration-messaging.md`, and this Plan.
- Delivery is a separate reviewable change and does not rewrite Proposal acceptance evidence.
- Real Claude Code and native Codex Desktop acceptance must remain reproducible without disabling
  ChatGPT in Chrome.

## Current status

The Proposal is promoted. Post-merge proof identified
`d05b8cff6d8edcd9ba1bd3388a452ee18b5507bf` as the first valid mainline inclusion. The runtime and
host adapters are already on `main`; the one-step entry, focused contracts, and sanitized real-host
acceptance record are isolated in the separate delivery change described by this Plan.

XATS sunset: XATS stays the default until native is promoted through a Proposal. The evidence threshold
(two consecutive releases accepted on at least two hosts, wake still working after one pinned upstream
upgrade, no open native P1/P2) and the one-minor retirement are recorded in
`docs/decisions/2026-09-28-xats-sunset.md`. Not yet triggered.

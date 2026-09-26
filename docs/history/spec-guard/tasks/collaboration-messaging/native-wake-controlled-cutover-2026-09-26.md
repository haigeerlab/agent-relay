# Controlled native cutover and rollback — 2026-09-26

Status: **rolled back to XATS; cross-host acceptance incomplete**.

The operator confirmed that the eight old XATS sessions had ended and authorized a controlled
switch. Both installed `collab` skills and selector hooks matched the reviewed source. XATS was
stopped without removing its LaunchAgent file. A consistent, owner-only, read-only SQLite archive
passed integrity, inventory and checksum checks: eight registered identities and three unread
deliveries remained unchanged. The native selector was then activated; XATS stayed offline.

A fresh Codex Desktop task used the ordinary `collab` entry to join native and bind its own wake
target. Its initial inbox was empty. ChatGPT in Chrome opened and read an isolated public test
page. A fresh Claude Code CLI session could not authenticate before any collaboration tool call.
No Claude ↔ Codex test message was sent, and Claude Code in Chrome was not functionally retested.
This trial does **not** satisfy the
one-step cross-host or dual-Chrome acceptance criteria.

The operator chose the recommended rollback. Three native acceptance identities had zero unread
deliveries and no active test turn. The pinned upstream retired exactly those identities with
`closeBacklog=false` and `notifySenders=false`; no messages were closed or notices sent. Native
preflight then reported zero registered identities and zero unacknowledged deliveries. XATS was
restarted and passed its health check. The first selector rollback was safely refused because its
permission check also required the shared `.spec-guard` parent to be `0700`, while this host uses
`0755` there and `0700` on both mailbox subdirectories. A regression test reproduced the refusal;
the check was narrowed to require an owner-owned, non-symlink shared parent and owner-only mailbox
subdirectories. Focused and full repository tests passed before the rollback was retried.

Final read-only checks: selector `xats`; XATS service running; old mailbox still eight registered
and three unread; private archive checksum unchanged; native mailbox history retained with zero
registered identities and zero unacknowledged deliveries. Chrome configuration and both mailboxes'
message bodies and read cursors were not changed; the rollback guard source was fixed as described.
Claude Code's installed Spec Guard plugin is now 0.19.1, which
retains XATS as the default when the native marker is absent. A new cross-host acceptance requires
working Claude Code access; the authentication failure requires separate diagnosis.

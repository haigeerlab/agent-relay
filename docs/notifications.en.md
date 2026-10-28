# Notices and delivery details

[简体中文](notifications.md) | English

"Authorization and safety" in the README gives only the essentials; this is the full description of notices and
delivery.

## Notices

### When they appear

- **A session waits for your approval**: when a Claude session sits on an approval prompt while a message to it is
  unhandled, this Mac shows a notice that the session is waiting for your approval, once per wait; the notice has no
  message body and cannot approve anything — you go back to that session. A Codex task on an approval card shows
  `waiting-approval` in the directory, but this notice is not shown for it.
- **Codex cannot receive**: when Codex is not open, a wake is held, or the identity is not bound for wake, the bridge
  shows a notice on this Mac at once; when Codex is only busy, after 10 minutes undelivered; at most once per message.
  The title names the sending session, the subtitle the message id, recipient and reason (with what to do when you need
  to act), and the body is a **single-line preview of at most the first 60 characters**.
- **A Claude session is not running**: the Claude desktop app stops the process of an idle session, and the bridge can
  only deliver to a running one. When a message to such a session has not gone in for five minutes, this Mac shows a
  notice naming the session (its mailbox name), how many messages are waiting and when the first was sent; once per
  offline spell, and opening the session delivers them. No message body and no click action. The sender sees
  `pendingReason: offline` in `bridge_outbox`.

When the recipient is neither bound for wake nor known to be on a host, no notice is shown, because there is no one
known to tell; the send result carries a warning instead.

### Previews and switches

The preview appears on the lock screen and shared screens (macOS's "Show previews" setting can limit that). In the
mailbox directory (`~/.agent-relay/runtime/mailbox/`):

- a `notify-preview.off` file hides the body and falls back to ids only;
- a `notify.off` file turns notices off entirely (all three above).

### Channel

With Homebrew's terminal-notifier installed (only `/opt/homebrew/bin` and `/usr/local/bin`, not looked up in PATH) it
is used, otherwise `osascript`. `osascript` notices are filed under Script Editor, which never asks for notification
permission, so on most Macs they are **silently dropped** with no switch in System Settings; to see banners,
`brew install terminal-notifier` (your choice) and allow it on its first notice. The bridge cannot see whether macOS
showed a notice, so wake details and sender warnings say only "attempted". doctor's `notifications` check judges
whether the actual channel looks allowed, and `doctor --test-notification` shows a test notice through the same channel
for you to confirm.

### Notices say where the session is, and a click takes you there

The subtitle of a "waiting for your approval" notice gives the session name, project directory name and place (Claude
desktop app, the terminal's tty, a background session and the `claude attach <id>` that opens it); a Codex notice says
"Codex app" when the app confirms it holds that thread. With terminal-notifier, clicking the notice brings the
application forward, and Terminal and iTerm also switch to that tab; background sessions, sessions inside tmux/ssh and
notices whose place is unknown have no click action. **A click only switches windows; it approves nothing and types
nothing into the session.** The first click on a terminal session's notice makes macOS ask once, on behalf of
terminal-notifier, for "Automation" permission (to control Terminal or iTerm); without it the terminal app still comes
forward but the tab is not selected, and you can change it later in System Settings → Privacy & Security → Automation.
With previews off (`notify-preview.off`) the text gives only the kind of place, and clicks still work.

### The place you can always see

Notices can be dropped by the system; the **waiting list** cannot: ask any session "which messages are waiting for
Codex", or run doctor and read `codex-waiting` (counts, senders and ids only, no bodies).

## Delivery

- **No "exactly once" promise**: every direct message has a delivery state (`queued`, `sending`, `accepted`, `failed`,
  `unknown`, `expired`), visible in the outbox. When a wake's outcome is unclear it is marked `unknown` and **never
  resent automatically**; a message still queued after its timeout (24 hours by default, adjustable with
  `BRIDGE_QUEUE_TIMEOUT_MS` or `expiresInSeconds` on send) is marked `expired`: no more wakes, hidden from the inbox by
  default, never executed later, and the sender is notified. When a Claude recipient does not hold a ping, Claude Code
  usually sends no receipt, so the message stays `unknown` in the outbox until the recipient reads it and it becomes
  `accepted` (seen on the real host in the 0.9.4 acceptance); this is normal, do not resend.
- **Queued per recipient, with a cap**: one recipient has one wake in flight at a time, in send order from oldest to
  newest; one stuck recipient does not delay others; messages the recipient already read are not woken separately.
  Each recipient holds at most 100 undelivered messages (`BRIDGE_MAX_PENDING_PER_RECIPIENT`, 10 to 10000); at 80 % the
  send result warns, and when full the send is refused with the reason; reading, ack, expiry or failure frees a slot.
- **A retry key means one message**: resending the same content with the same `idempotencyKey` returns the original
  (`duplicate: true`) and wakes no one; the same key with a different recipient, body, thread or reply target is
  refused, naming the stored message id and saying no resend is needed. A reply can carry `replyTo` (the original's
  id), lands on the original's thread, and the outbox shows which replies each message received; the same reply to the
  same message is stored once, unless the previous one finally failed or expired. Give important messages an
  `idempotencyKey` when you send them and retry an error with the same key; at most you get the original back.
- **An error means not saved**: when a step after the message was saved fails (a busy database, for example),
  `bridge_send` does not report an error: it returns the stored id with a warning "Saved as #id; … Do not send it
  again." and the wake is retried in the background, so an error from `bridge_send` means the message was not saved.

The full state machine and fields are in the [interface document](collaboration-interface.md), §5 and §6.

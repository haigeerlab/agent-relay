# Legacy XATS session audit — 2026-09-25

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Status: **read-only evidence; cutover remains blocked**. At 12:00 UTC the installed XATS runtime
reported a running daemon. The source read-only preflight still reported 8 registered identities,
3 deliverable unread messages and unverified active sessions. No selector marker was written.

## Operator retention decision — 2026-09-26

The operator chose the recommended treatment for the three known unread deliveries: preserve
them unchanged as read-only history when a separately approved cutover is eventually safe.
This is a retention decision, not evidence that the old sessions have ended or authorization to
acknowledge messages, archive the live database, stop XATS, or select the native backend. A fresh
read-only preflight still reports 8 registered identities and 3 unread deliveries; active-session
status remains unverified.

## What the current records prove

- The three unread deliveries are still events 9–11 from the earlier acceptance period: two
  target a Claude identity and one targets a Codex identity. Only sender/recipient metadata and
  event IDs were inspected; no subject or body was read, no inbox cursor advanced, and no
  identity was removed.
- Three registered Claude identities contain stored process IDs. A host-side `ps` check found
  none of those three PIDs running. This rules out those **recorded processes** being live at the
  check time; it does not prove an identity cannot reconnect under another process.
- The five registered native-Desktop Codex identities have no recorded task ID, process binding,
  or tmux pane from which to establish present task liveness. Their old `last_seen_at` timestamps
  and test-style display names are not sufficient proof that the underlying tasks are closed.
- All eight identities have `delivery_kind=none`, so no registered push-delivery binding can be
  inferred from the database. That does not prevent a still-open session from manually reading
  its mailbox.

## Cutover consequence

No automatic stale-identity cleanup or unread acknowledgement is justified. Before a live switch,
review the exact recipient identities with the operator, confirm which old tasks can still use
XATS, quiesce the service only with separate approval, and repeat the unread inventory. Preserve
events 9–11 in the verified private archive if the operator explicitly classifies them as
historical. The audit neither performs nor authorizes that classification.

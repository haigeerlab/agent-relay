"""Tell "our own code is wrong" apart from "a read failed", in one place.

Several modules degrade a failed probe into a conservative result -- `unknown`,
`partial`, `publication-uncertain`, `host-result-unknown`.  Every one of those tells the
reader to retry, and a retry cannot fix a typo, so a defect must never be reported as
one of them.  v0.41.0 separated "the probe could not read" from "it read and the fact
does not hold"; this is the third member of that family.

**Prefer naming the exception type.**  A module that can see its own transport's error
class should catch that instead -- `hosted_ticket_*` catches `HostedTicketError`,
`local_ticket_publish` catches `InventoryError`.  This helper exists only for the two
places where that is impossible:

- `proposal_closeout` is deliberately transport-free (see `_rejection` there: duck-typed
  on `status_code` "so any adapter can report one without this module importing a
  transport"), so it cannot name an adapter's error class.
- `session_delegation_claude`'s native wake is an injected `Callable` with no in-repo
  implementation, so its exception type is not knowable here.

`ValueError` is deliberately absent: journals and transports across this plugin use it
for unreadable JSON and for their own error bases (`HostedTicketError`,
`InventoryError`, `ClaudeAdapterError` are all `ValueError` subclasses), so including it
would catch exactly the failures that must still degrade.
"""
from __future__ import annotations

DEFECTS = (AttributeError, TypeError, NameError, KeyError, IndexError,
           AssertionError, ImportError)


def is_defect(error: BaseException) -> bool:
    """True when the exception says our own code is wrong, not that a read failed."""
    return isinstance(error, DEFECTS)

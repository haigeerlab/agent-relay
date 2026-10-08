"""delegation-claim: one call at a time may reach a host for a delegation (D122-D126)."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import stat
import tempfile
import unittest

from session_delegation import DelegationError, DelegationStore, OperationBusy, OperationClaim


NOW = 1_800_000_000
DELEGATION = "11111111-2222-4333-8444-555555555555"


class ClaimFileTests(unittest.TestCase):
    """D122: a private lock file per delegation, held exclusively, carrying the operation in flight."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ar-claim-")
        self.addCleanup(temporary.cleanup)
        self.store = DelegationStore(Path(temporary.name) / "state", now=lambda: NOW)
        self.path = self.store.root / "claims" / (DELEGATION + ".lock")

    def test_the_claim_file_is_private_and_starts_clean(self):
        with OperationClaim(self.store, DELEGATION) as claim:
            self.assertEqual(claim.previous(), "")
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_a_second_holder_is_refused_while_the_first_holds_it(self):
        with OperationClaim(self.store, DELEGATION):
            with self.assertRaises(OperationBusy):
                with OperationClaim(self.store, DELEGATION):
                    self.fail("a second holder must not get the claim")
        with OperationClaim(self.store, DELEGATION):
            pass  # released with the first holder

    def test_another_process_holding_the_lock_makes_it_busy(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(OperationBusy):
                with OperationClaim(self.store, DELEGATION):
                    pass
        finally:
            os.close(descriptor)

    def test_begin_is_durable_and_end_clears_it(self):
        with OperationClaim(self.store, DELEGATION) as claim:
            claim.begin("create")
        with OperationClaim(self.store, DELEGATION) as claim:
            self.assertEqual(claim.previous(), "create", "a holder that died leaves its operation")
            claim.end()
        with OperationClaim(self.store, DELEGATION) as claim:
            self.assertEqual(claim.previous(), "")
        self.assertEqual(self.path.read_bytes(), b"")

    def test_an_unsafe_claim_file_is_refused(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.store.root / "elsewhere"
        target.write_text("", encoding="utf-8")
        self.path.symlink_to(target)
        with self.assertRaisesRegex(DelegationError, "claim-file-unsafe"):
            with OperationClaim(self.store, DELEGATION):
                pass
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaisesRegex(DelegationError, "claim-file-unsafe"):
            with OperationClaim(self.store, DELEGATION):
                pass

    def test_a_malformed_delegation_id_is_refused(self):
        with self.assertRaisesRegex(DelegationError, "claim-file-unsafe"):
            with OperationClaim(self.store, "../escape"):
                pass


if __name__ == "__main__":
    unittest.main()

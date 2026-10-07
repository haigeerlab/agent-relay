"""--expires-at takes ISO 8601 with an offset (documented) or epoch seconds (ops-commands D44, checklist C8)."""
from __future__ import annotations

import contextlib
import io
import unittest

from session_delegation_control import _parser, expires_at


class ExpiresAtTests(unittest.TestCase):
    def test_iso_with_an_offset_and_epoch_seconds_are_accepted(self):
        self.assertEqual(expires_at("2026-10-08T18:00:00+08:00"), 1791453600)
        self.assertEqual(expires_at("2026-10-08T10:00:00Z"), 1791453600)
        self.assertEqual(expires_at("2026-10-08T10:00:00.900+00:00"), 1791453600)
        self.assertEqual(expires_at("1791453600"), 1791453600)

    def test_other_values_exit_2_naming_the_format(self):
        for value in ("2026-10-08T18:00:00", "2026-10-08", "tomorrow", "-5", "1.5e9", ""):
            with self.subTest(value=value):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as raised:
                    _parser().parse_args(["create", "--expires-at", value])
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("ISO 8601 with an offset", err.getvalue())
                self.assertIn("2026-10-08T18:00:00+08:00", err.getvalue())


if __name__ == "__main__":
    unittest.main()

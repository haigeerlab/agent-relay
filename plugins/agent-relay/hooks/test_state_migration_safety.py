#!/usr/bin/env python3
"""state-migration-safety: one migration at a time, never under a running bridge, all or nothing (D116-D121)."""
import fcntl
import os
import unittest

import state_migration
from test_state_migration import Fixture, no_servers, tree_digest


def running(_path):
    return 2


class SafetyFixture(Fixture):
    def target_digest(self):
        return tree_digest(self.home / ".agent-relay")


class ExclusiveTests(SafetyFixture):
    """D116, D117: a second migration and agent-relay's own bridges are refused before any write."""

    def test_a_second_migration_is_refused_while_the_lock_is_held(self):
        self.make_ready_case()
        before = self.target_digest()
        held = os.open(self.home / ".agent-relay", os.O_RDONLY)
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _report, result = state_migration.migrate(self.home, (), no_servers, target_count=no_servers)
        finally:
            os.close(held)
        self.assertEqual(result["state"], "blocked")
        self.assertIn("another state migration is running", result["diagnostic"])
        self.assertEqual(self.target_digest(), before)
        self.assertFalse((self.home / ".agent-relay" / "backups").exists(), "no backup was started")

    def test_the_lock_is_released_after_a_migration(self):
        self.make_ready_case()
        _report, result = state_migration.migrate(self.home, (), no_servers, target_count=no_servers)
        self.assertEqual(result["state"], "migrated")
        again = os.open(self.home / ".agent-relay", os.O_RDONLY)
        try:
            fcntl.flock(again, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(again)

    def test_running_agent_relay_bridges_block_detect_and_migrate(self):
        self.make_ready_case()
        report = state_migration.inspect(self.home, (), no_servers, target_count=running)
        self.assertEqual(report.target_servers, 2)
        self.assertTrue(any("agent-relay bridge server" in blocker for blocker in report.blockers), report.blockers)
        before = self.target_digest()
        _report, result = state_migration.migrate(self.home, (), no_servers, target_count=running)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(self.target_digest(), before)


if __name__ == "__main__":
    unittest.main()

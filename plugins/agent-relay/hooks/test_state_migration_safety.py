#!/usr/bin/env python3
"""state-migration-safety: one migration at a time, never under a running bridge, all or nothing (D116-D121)."""
import fcntl
import os
from pathlib import Path
import unittest
from unittest import mock

import state_migration
from test_state_migration import Fixture, no_servers, tree_digest

REAL_WRITE = state_migration._write_journal
STEPS = ("mailbox:retiring", "mailbox:placing", "data:retiring", "data:placing", "delegation:retiring",
         "delegation:placing", "verifying")


def fail_at(step):
    """Write the journal, then fail as the step is about to move anything."""
    def write(parent, journal):
        REAL_WRITE(parent, journal)
        if journal["step"] == step:
            raise RuntimeError(f"injected at {step}")
    return write


def layout(root):
    """Every path under `root` with its type and, for files, a digest: directories count too."""
    return {**{str(p.relative_to(root)): "dir" for p in root.rglob("*") if p.is_dir()}, **tree_digest(root)}


def running(_path):
    return 2


class SafetyFixture(Fixture):
    def target_digest(self):
        return tree_digest(self.home / ".agent-relay")

    def make_lived_in_case(self, delegation_dir=False):
        """A ready case whose target already holds files the swap must carry over or put back."""
        self.make_ready_case()
        (self.runtime / "mailbox" / "notify.off").write_text("", encoding="utf-8")
        daily = self.runtime / "mailbox" / "backups" / "bridge-daily-2026-10-01.sqlite"
        daily.write_bytes(b"target daily")
        daily.chmod(0o600)  # the runtime requires private backups
        (self.runtime / "data" / "keep.txt").write_text("target data\n", encoding="utf-8")
        if delegation_dir:
            self.private(self.home / ".agent-relay" / "delegation")
            (self.home / ".agent-relay" / "delegation" / "note.txt").write_text("target\n", encoding="utf-8")

    def watched(self):
        """The target paths a migration may touch: runtime mailbox and data, and the delegation directory."""
        parent = self.home / ".agent-relay"
        return {name: layout(path) if path.exists() else None
                for name, path in (("mailbox", self.runtime / "mailbox"), ("data", self.runtime / "data"),
                                   ("delegation", parent / "delegation"))}

    def leftovers(self):
        parent = self.home / ".agent-relay"
        return sorted(p.name for p in parent.iterdir() if p.name.startswith(".state-migration-")
                      or p.name.startswith("state-migration.json"))


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



class AllOrNothingTests(SafetyFixture):
    """D118, D119: prepared beside, swapped whole directories, put back on any failure."""

    def migrate(self):
        return state_migration.migrate(self.home, (), no_servers, target_count=no_servers)

    def test_a_failure_at_each_step_puts_the_target_back_exactly(self):
        for delegation_dir in (False, True):
            for step in STEPS:
                with self.subTest(step=step, delegation_dir=delegation_dir):
                    self.setUp()
                    self.make_lived_in_case(delegation_dir)
                    before, old = self.watched(), tree_digest(self.home / ".spec-guard")
                    with mock.patch.object(state_migration, "_write_journal", side_effect=fail_at(step)):
                        _report, result = self.migrate()
                    self.assertEqual(result["state"], "rolled-back", result)
                    self.assertIn(f"injected at {step}", result["diagnostic"])
                    self.assertEqual(self.watched(), before, "the target is exactly as before")
                    self.assertEqual(tree_digest(self.home / ".spec-guard"), old)
                    self.assertFalse((self.home / ".agent-relay" / "state-migration.json").exists())
                    kept = Path(result["kept"])
                    self.assertTrue(kept.name.startswith(".state-migration-failed-"), kept)
                    self.assertTrue(kept.is_dir(), "the failed stage is kept for inspection")
                    self.assertEqual(self.leftovers(), [kept.name])
                    self.assertTrue(Path(result["backup"]).is_dir(), "the backup stays")

    def test_a_count_mismatch_after_the_swap_puts_the_target_back(self):
        self.make_lived_in_case()
        before = self.watched()
        real = state_migration.table_counts

        def skewed(path):
            counts = real(path)
            if path == self.runtime / "mailbox" / "bridge.sqlite":
                counts["messages"] -= 1
            return counts

        with mock.patch.object(state_migration, "table_counts", side_effect=skewed):
            _report, result = self.migrate()
        self.assertEqual(result["state"], "rolled-back")
        self.assertEqual(result["mismatches"][0]["database"], "mailbox")
        self.assertEqual(self.watched(), before)

    def test_a_failure_before_the_journal_removes_only_this_stage(self):
        self.make_lived_in_case()
        before = self.watched()
        with mock.patch.object(state_migration, "_sqlite_copy", side_effect=OSError("disk full")):
            _report, result = self.migrate()
        self.assertEqual(result["state"], "rolled-back")
        self.assertEqual(self.watched(), before)
        self.assertEqual(self.leftovers(), [], "the stage was ours and is gone; there was no journal")

    def test_a_successful_migration_carries_the_target_files_and_keeps_the_previous_ones(self):
        self.make_lived_in_case(delegation_dir=True)
        _report, result = self.migrate()
        self.assertEqual(result["state"], "migrated", result)
        mailbox = self.runtime / "mailbox"
        self.assertEqual(state_migration.table_counts(mailbox / "bridge.sqlite")["messages"], 3)
        self.assertTrue((mailbox / "notify.off").is_file(), "a mailbox flag file is carried over")
        self.assertEqual((mailbox / "backups" / "bridge-daily-2026-10-01.sqlite").read_bytes(), b"target daily")
        self.assertEqual((mailbox / "backups" / "bridge-daily-2026-10-06.sqlite").read_bytes(), b"daily")
        self.assertEqual((self.runtime / "data" / "keep.txt").read_text(encoding="utf-8"), "target data\n")
        self.assertTrue((self.runtime / "data" / "claude-codex-bridge" / "runs").is_dir(), "old data copied in")
        delegation = self.home / ".agent-relay" / "delegation"
        self.assertEqual((delegation / "note.txt").read_text(encoding="utf-8"), "target\n")
        self.assertTrue((delegation / "delegation.sqlite").is_file())
        for path in (mailbox, self.runtime / "data", delegation):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700, path)
        self.assertFalse((self.home / ".agent-relay" / "state-migration.json").exists())
        previous = Path(result["previous"])
        self.assertTrue((previous / "previous-mailbox" / "notify.off").is_file(), "the replaced target is kept")


if __name__ == "__main__":
    unittest.main()

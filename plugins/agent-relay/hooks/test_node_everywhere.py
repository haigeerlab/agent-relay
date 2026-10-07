"""install, upgrade and retire use the node the host entries pin, and npm runs on it (acceptance-kit-round2 D57,
round 2 R2-12: with nvm v12 first in PATH, `install --npm <v24 npm>` failed because npm's `#!/usr/bin/env node`
found v12, and retire's default node was PATH's)."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_collaboration_retire
import native_collaboration_runtime as runtime


def script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    return path


class Machine(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-node-all-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.log = self.base / "npm.log"
        self.old = script(self.base / "nvm12" / "node", "echo v12.22.12")
        self.new = script(self.base / "nvm24" / "node", "echo v24.18.0")
        # npm starts through `#!/usr/bin/env node`: record which node that finds, and build when asked.
        script(self.base / "nvm24" / "npm",
               f'echo "$(command -v node) $(node --version) $*" >> "{self.log}"\n'
               'if [ "$1 $2" = "run build" ]; then mkdir -p dist && echo server > dist/server.js; fi')
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = {"PATH": f"{self.old.parent}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(self.home),
                    "CLAUDE_CONFIG_DIR": str(self.home), "CODEX_HOME": str(self.home / ".codex"),
                    "AGENT_RELAY_HOME": str(self.base / "relay")}

    def pin_claude(self, node: Path):
        (self.home / ".claude.json").write_text(json.dumps({"mcpServers": {"agent-relay": {"command": str(node)}}}))

    def main(self, module, argv):
        out = io.StringIO()
        with patch.dict(os.environ, self.env, clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out):
            try:
                code = module.main(argv)
            except SystemExit as error:
                code = error.code
        return code, out.getvalue()


class InstallNodeTests(Machine):
    def test_explicit_node_runs_npm_on_that_node_even_with_v12_first_in_path(self):
        code, output = self.main(runtime, ["install", "--node", str(self.new)])
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["state"], "ready")
        runs = self.log.read_text().splitlines()
        self.assertEqual(len(runs), 2, runs)
        for line in runs:
            self.assertTrue(line.startswith(f"{self.new} v24.18.0 "), line)

    def test_the_pinned_node_and_its_npm_are_used_without_options(self):
        self.pin_claude(self.new)
        code, output = self.main(runtime, ["install"])
        self.assertEqual(code, 0, output)
        self.assertTrue(all(line.startswith(f"{self.new} ") for line in self.log.read_text().splitlines()))

    def test_only_an_old_node_refuses_before_anything_is_built(self):
        code, output = self.main(runtime, ["install"])
        self.assertNotEqual(code, 0)
        self.assertIn("node-too-old", output)
        self.assertIn("node:sqlite", output)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.base / "relay" / "runtime").exists())


class RetireNodeTests(Machine):
    def test_retire_defaults_to_the_pinned_node(self):
        self.pin_claude(self.new)
        with patch("native_collaboration_retire.retire_identity", return_value={"state": "retired"}) as retire:
            code, output = self.main(native_collaboration_retire, ["--name", "x", "--confirm-retire"])
        self.assertEqual(code, 0, output)
        self.assertEqual(Path(retire.call_args.args[1]), self.new)

    def test_retire_with_only_an_old_node_refuses(self):
        with patch("native_collaboration_retire.retire_identity") as retire:
            code, output = self.main(native_collaboration_retire, ["--name", "x", "--confirm-retire"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)["state"], "refused")
        self.assertIn("node-too-old", output)
        retire.assert_not_called()


if __name__ == "__main__":
    unittest.main()

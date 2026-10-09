#!/usr/bin/env python3
"""Guard the CI exempt list (ci-on-demand D137).

CI skips the tests when a change touches only exempt paths (scripts/ci_scope.py). That is safe only while nothing
`scripts/validate.sh` runs reads those paths, so this test scans it for path literals naming them: string constants in
Python (docstrings excluded), non-comment lines in shell and TypeScript. It errs toward failing: on a hit, either the
path leaves the exempt list or the reference goes. It cannot see a path built at run time or a walk over the whole
repository; none exists today.
"""
import ast
import importlib.util
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HOOKS = REPO / "plugins" / "agent-relay" / "hooks"
BRIDGE = REPO / "plugins" / "agent-relay" / "bridge"

# The files that define or test the exempt list itself.
OWN = {"scripts/ci_scope.py", "plugins/agent-relay/hooks/test_ci_scope.py",
       "plugins/agent-relay/hooks/test_ci_exempt_guard.py"}

# Known references that do not read an exempt path: (file, text on the line, why).
ALLOWED = (
    ("plugins/agent-relay/hooks/test_native_only_collaboration.py", 'HISTORY / "spec" /',
     "docs/history/spec-guard/spec/, archived specs under docs/, not the root spec/"),
)


def load_ci_scope():
    module_spec = importlib.util.spec_from_file_location("ci_scope", REPO / "scripts" / "ci_scope.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def patterns():
    """(anywhere, whole_part): regexes searched in a literal or line, and regexes matched against one path part."""
    ci = load_ci_scope()
    anywhere = [re.compile(re.escape(name)) for name in ci.EXEMPT_FILES]
    whole_part = []
    for directory in ci.EXEMPT_DIRS:
        name = re.escape(directory.rstrip("/"))
        anywhere.append(re.compile(r"(?<![\w.-])" + name + r"/"))  # spec/x, not my-spec/x or .agent-relay/x
        whole_part.append(re.compile(name + r"$"))                  # REPO / "spec"
    return anywhere, whole_part


def names_exempt(literal, pats):
    anywhere, whole_part = pats
    return (any(pat.search(literal) for pat in anywhere)
            or any(pat.match(part) for part in literal.split("/") for pat in whole_part))


def python_strings(source):
    """(line, value) of every string constant except docstrings."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]


def code_lines(source):
    """(line, text) of lines that are not comments, for shell and TypeScript."""
    out = []
    for number, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "//", "/*", "*")):
            out.append((number, line))
    return out


def scanned_files():
    files = sorted(HOOKS.glob("*.py"))
    files += sorted(p for p in (REPO / "scripts").rglob("*") if p.is_file())
    for directory in ("src", "test"):
        files += sorted(p for p in (BRIDGE / directory).rglob("*") if p.is_file())
    files += sorted(p for p in BRIDGE.iterdir() if p.is_file())
    return [p for p in files if p.relative_to(REPO).as_posix() not in OWN]


def offenders(files, pats):
    found = []
    for path in files:
        rel = path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else path.name
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        if path.suffix == ".py":
            candidates = [n for n, value in python_strings(source) if names_exempt(value, pats)]
        else:
            candidates = [n for n, text in code_lines(source)
                          if any(pat.search(text) for pat in pats[0])
                          or any(names_exempt(word, pats) for word in re.findall(r"[\"']([^\"']*)[\"']", text))]
        for number in candidates:
            line = lines[number - 1]
            if any(rel == file and marker in line for file, marker, _ in ALLOWED):
                continue
            found.append(f"{rel}:{number}: {line.strip()[:120]}")
    return sorted(set(found))


class ExemptGuardTest(unittest.TestCase):
    def setUp(self):
        self.pats = patterns()

    def test_nothing_validate_runs_names_an_exempt_path(self):
        files = scanned_files()
        self.assertGreater(len(files), 50, "the scan found too few files to mean anything")
        self.assertEqual(offenders(files, self.pats), [],
                         "these refer to a path CI may skip; drop the path from scripts/ci_scope.py or the reference")

    def test_a_planted_reference_is_caught(self):
        import tempfile
        planted = {
            "a.py": 'REPO = None\nTEXT = (REPO / "spec" / "x.md")\n',
            "b.py": 'open("tasks/ci-on-demand/todo.md")\n',
            "c.py": 'read(".agent/state.json")\n',
            "d.py": 'read("CLAUDE.md")\n',
            "e.sh": 'cat AGENTS.md\n',
            "f.ts": 'readFileSync("spec/CAPABILITY-MAP.md")\n',
        }
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, text in planted.items():
                path = Path(tmp) / name
                path.write_text(text)
                paths.append(path)
            caught = offenders(paths, self.pats)
        self.assertEqual(len(caught), len(planted), caught)

    def test_look_alikes_comments_and_docstrings_are_not_caught(self):
        import tempfile
        clean = {
            "a.py": '"""See spec/state-migration.md."""\nimport importlib.util\n'
                    'spec = importlib.util.spec_from_file_location("x", "y")\n'
                    'HOME = "~/.agent-relay/runtime"\nNAME = "tasks_done"\nP = "docs/specs/x.md"\n',
            "b.sh": '# reads spec/x.md in the comment only\necho "$HOME/.agent-relay"\n',
            "c.ts": '// spec/x.md\nconst taskList = "my-tasks/x";\n',
        }
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, text in clean.items():
                path = Path(tmp) / name
                path.write_text(text)
                paths.append(path)
            self.assertEqual(offenders(paths, self.pats), [])

    def test_every_allowed_reference_still_exists(self):
        for file, marker, why in ALLOWED:
            self.assertIn(marker, (REPO / file).read_text(encoding="utf-8"), f"stale allowance ({why}): {file}")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Step-by-step maintainer release commands (D278 output, D286 local records)."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
SCHEMA = "agent-relay.release/v1"
EXIT_CODES = {"ok": 0, "preview": 0, "refused": 2, "waiting-on-user": 3, "failed": 1}

_runtime_spec = importlib.util.spec_from_file_location(
    "release_native_runtime", REPO / "plugins" / "agent-relay" / "hooks" / "native_collaboration_runtime.py")
_runtime = importlib.util.module_from_spec(_runtime_spec)
_runtime_spec.loader.exec_module(_runtime)
state_home = _runtime.state_home
RUNTIME_FILES = _runtime.RUNTIME_FILES

_preflight_spec = importlib.util.spec_from_file_location(
    "release_preflight", REPO / "scripts" / "acceptance" / "preflight.py")
_preflight = importlib.util.module_from_spec(_preflight_spec)
_preflight_spec.loader.exec_module(_preflight)


class ReleaseError(Exception):
    """A refusal or failure with a stable machine-readable reason."""

    def __init__(self, message, status, reason):
        super().__init__(message)
        self.status = status
        self.reason = reason


class HelpRequested(Exception):
    """Return from argparse help through the same JSON output path."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ReleaseError("参数错误：" + message, "refused", "usage")

    def exit(self, status=0, message=None):
        if status == 0:
            raise HelpRequested()
        self.error(message or "无法解析参数")


def run(args, timeout=30, *, text=True):
    """The only process entry point; callers pass an argument list."""
    return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=text,
                          timeout=timeout, check=True)


def validate_version(version):
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ReleaseError("版本号必须为三个由点分隔的非负整数，例如 1.2.3。", "refused", "invalid-version")
    return version


def read_record(version):
    """Read without creating state; a new version starts with no completed steps."""
    validate_version(version)
    path = state_home() / "release" / (version + ".json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": SCHEMA, "version": version, "steps": {}}


def write_record(record, step, facts):
    """Replace just one step, publishing the complete record with an atomic rename."""
    version = validate_version(record["version"])
    updated = {**record, "steps": {**record.get("steps", {}), step: facts}}
    directory = state_home() / "release"
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=version + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(updated, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, directory / (version + ".json"))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return updated


def github_repository(args):
    github = args.github
    if github is None:
        url = run(["git", "-C", str(args.repo), "remote", "get-url", args.remote]).stdout.strip()
        path = urlsplit(url).path if "://" in url else url.partition(":")[2]
        path = path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        if not re.fullmatch(r"[^/\s:]+/[^/\s:]+", path):
            raise ReleaseError("无法从远端地址解析 GitHub 仓库，请指定 --github owner/repo。", "refused", "usage")
        github = path
    return github


def check(args):
    def git(*command):
        return run(["git", "-C", str(args.repo), *command]).stdout.strip()

    github = github_repository(args)

    pr = json.loads(run(["gh", "api", f"repos/{github}/pulls/{args.pr}"]).stdout)
    if not pr.get("merged"):
        raise ReleaseError("发版 PR 尚未合并。", "refused", "not-merged")
    sha = pr["merge_commit_sha"]
    git("fetch", args.remote)
    if git("rev-parse", args.remote + "/main") != sha:
        raise ReleaseError("远端 main 已不在发版 PR 的合并提交。", "refused", "main-moved")
    runs = json.loads(run(["gh", "run", "list", "--repo", github, "--commit", sha,
                           "--json", "conclusion,status,workflowName"]).stdout)
    if not runs or any(item.get("status") != "completed" or item.get("conclusion") != "success" for item in runs):
        raise ReleaseError("合并提交的 CI 为空、尚未结束或未全部成功。", "refused", "ci-not-green")

    def show(path, ref=sha):
        return git("show", ref + ":" + path)

    plugin = "plugins/agent-relay/"
    try:
        versions = [validate_version(json.loads(show(plugin + host + "/plugin.json"))["version"])
                    for host in (".claude-plugin", ".codex-plugin")]
    except (subprocess.CalledProcessError, ValueError, KeyError, TypeError, ReleaseError):
        raise ReleaseError("两份插件清单必须包含有效的三段版本号。", "refused", "version-mismatch")
    if versions[0] != versions[1]:
        raise ReleaseError("Claude 与 Codex 插件清单的版本号不一致。", "refused", "version-mismatch")
    args.version = version = versions[0]
    for name, label in (("README.md", "状态："), ("README.en.md", "Status:")):
        try:
            text = show(name)
        except subprocess.CalledProcessError:
            text = ""
        status = re.search(r"^>\s*" + label + r"\s*" + re.escape(version) + r"(?=\s|（|\(|$)", text, re.MULTILINE)
        ref = re.search(r"--ref\s+v" + re.escape(version) + r"(?=\s|[`\"']|$)", text)
        if not status or not ref:
            raise ReleaseError(name + " 的状态行或安装 --ref 与插件版本不一致。", "refused", "readme-mismatch")
    try:
        changelog = show("CHANGELOG.md")
    except subprocess.CalledProcessError:
        changelog = ""
    if not re.search(r"^## \[" + re.escape(version) + r"\](?:\s.*)?$", changelog, re.MULTILINE):
        raise ReleaseError("CHANGELOG.md 缺少本版本的章节。", "refused", "changelog-missing")
    try:
        bridge_version = validate_version(json.loads(show(plugin + "bridge/package.json"))["version"])
    except (subprocess.CalledProcessError, ValueError, KeyError, TypeError, ReleaseError):
        raise ReleaseError("bridge 的版本号无效。", "refused", "bridge-version")
    if tuple(map(int, bridge_version.split("."))) > tuple(map(int, version.split("."))):
        raise ReleaseError("bridge 的版本号高于插件版本。", "refused", "bridge-version")

    tags = git("tag", "--merged", sha, "--sort=-v:refname").splitlines()
    remote_tag = git("ls-remote", args.remote, "refs/tags/v" + version)
    # Unmerged local tags also block publication.
    local_tag = git("tag", "--list", "v" + version)
    if local_tag or remote_tag:
        raise ReleaseError("本版本的 tag 已存在于本地或远端。", "refused", "tag-exists")
    previous = next((tag for tag in tags if tag.startswith("v")), None)
    interface_to = json.loads(show(plugin + "interface.json"))["interface"]
    interface_from = json.loads(show(plugin + "interface.json", previous))["interface"] if previous else None
    bridge = plugin + "bridge/"
    if previous:
        paths = git("diff", "--name-only", previous, sha, "--", bridge).splitlines()
    else:
        paths = git("ls-tree", "-r", "--name-only", sha, "--", bridge).splitlines()
    runtime_files = sorted(path[len(bridge):] for path in paths
                           if any(path[len(bridge):].startswith(entry) if entry.endswith("/")
                                  else path[len(bridge):] == entry for entry in RUNTIME_FILES))
    facts = {"status": "ok", "mergeCommit": sha, "previousTag": previous,
             "interface": {"from": interface_from, "to": interface_to},
             "runtimeUpgrade": previous is None or bool(runtime_files), "runtimeFiles": runtime_files}
    write_record(read_record(version), "check", facts)
    return facts


def prepare(args):
    record = read_record(args.version)
    checked = record.get("steps", {}).get("check", {})
    if checked.get("status") != "ok":
        raise ReleaseError("本版本尚无成功的 check 记录，请先运行 check。", "refused", "needs-check")
    sha = checked["mergeCommit"]
    archived = run(["git", "-C", str(args.repo), "archive", "--format=tar", sha,
                    ".claude-plugin", "plugins/agent-relay"], text=False).stdout
    directory = Path(tempfile.mkdtemp(prefix="agent-relay-release-"))
    with tarfile.open(fileobj=io.BytesIO(archived), mode="r:") as archive:
        members = archive.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ReleaseError("归档含绝对路径或上级目录，已拒绝解包。", "refused", "unsafe-archive")
        archive.extractall(directory, members=members)

    plugin = directory / "plugins" / "agent-relay"
    manifest = {}
    for path in sorted(plugin.rglob("*")):
        relative = path.relative_to(plugin)
        if any(part in _preflight.IGNORED for part in relative.parts) or not path.is_file():
            continue
        manifest[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path = directory / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    changelog = run(["git", "-C", str(args.repo), "show", sha + ":CHANGELOG.md"]).stdout
    section = re.search(r"^## \[" + re.escape(args.version) + r"\](?:[ \t][^\n]*)?(?:\n|\Z)(.*?)(?=^## \[|\Z)",
                        changelog, re.MULTILINE | re.DOTALL)
    if section is None:
        raise ReleaseError("CHANGELOG.md 缺少本版本的章节。", "refused", "changelog-missing")
    (directory / "release-notes.md").write_text(section.group(1), encoding="utf-8")
    facts = {"status": "ok", "dir": str(directory),
             "manifestSha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "files": len(manifest)}
    write_record(record, "prepare", facts)
    return facts


def publish(args):
    record = read_record(args.version)
    steps = record.get("steps", {})
    for step in ("check", "prepare"):
        if steps.get(step, {}).get("status") != "ok":
            raise ReleaseError("本版本尚无成功的 " + step + " 记录，请先运行 " + step + "。",
                               "refused", "needs-" + step)
    checked = steps["check"]
    sha = checked["mergeCommit"]
    git = ["git", "-C", str(args.repo)]
    main_ref = run([*git, "ls-remote", args.remote, "refs/heads/main"]).stdout.split()
    if not main_ref or main_ref[0] != sha:
        raise ReleaseError("远端 main 已不在发版 PR 的合并提交。", "refused", "main-moved")

    tag = "v" + args.version
    tag_ref = "refs/tags/" + tag
    remote_refs = run([*git, "ls-remote", args.remote, tag_ref, tag_ref + "^{}"]).stdout
    refs = {ref: commit for commit, ref in (line.split() for line in remote_refs.splitlines())}
    remote_commit = refs.get(tag_ref + "^{}", refs.get(tag_ref))
    if remote_commit is not None and remote_commit != sha:
        raise ReleaseError("远端 tag 指向其他提交，已拒绝发布。", "refused", "tag-mismatch")

    github = github_repository(args)
    if remote_commit is not None:
        try:
            release_url = run(["gh", "release", "view", tag, "--json", "url", "--jq", ".url",
                               "--repo", github]).stdout.strip()
        except subprocess.CalledProcessError:
            pass
        else:
            return {"status": "ok", "alreadyPublished": True, "tag": tag,
                    "releaseUrl": release_url, "peeledCommit": remote_commit}

    commands = [
        [*git, "tag", "-a", tag, sha, "-m", "agent-relay " + args.version],
        [*git, "push", args.remote, tag],
        ["gh", "release", "create", tag, "--verify-tag", "--title",
         "agent-relay " + args.version + " (interface " + str(checked["interface"]["to"]) + ")",
         "--notes-file", str(Path(steps["prepare"]["dir"]) / "release-notes.md"), "--repo", github],
    ]
    if not args.confirm:
        return {"status": "preview", "commands": commands}

    for command in commands[:2]:
        run(command)
    release_url = run(commands[2]).stdout.strip()
    peeled = run([*git, "ls-remote", args.remote, tag_ref + "^{}"]).stdout.split()
    if not peeled or peeled[0] != sha:
        raise ReleaseError("发布后远端 tag 未解析到合并提交。", "failed", "tag-mismatch")
    facts = {"status": "ok", "tag": tag, "releaseUrl": release_url, "peeledCommit": peeled[0]}
    write_record(record, "publish", facts)
    return facts


def claude_source():
    """Read the marketplace's declared source, never its cached install location."""
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    marketplaces = json.loads((home / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8"))
    source = marketplaces.get("agent-relay-marketplace", {}).get("source", {})
    kind = source.get("source")
    if kind == "directory" and source.get("path"):
        return {"kind": "directory", "path": source["path"]}
    if kind in ("git", "github") and (source.get("url") or source.get("repo")):
        return {"kind": "git", **{key: source[key] for key in ("url", "repo", "ref") if key in source}}
    raise ReleaseError("无法识别 Claude 的 agent-relay-marketplace 来源。", "refused", "claude-source-unknown")


def _codex_marketplace(text):
    """Locate the target table and its scalar source without reserializing TOML."""
    def ambiguous():
        return ReleaseError("Codex 市场段缺失、来源不明或 ref 行不唯一。", "refused", "codex-ref-ambiguous")

    headers = list(re.finditer(r"^[ \t]*(\[[^\r\n]+?\])[ \t]*(?:#[^\r\n]*)?(?:\r?\n|$)", text, re.MULTILINE))
    targets = [index for index, header in enumerate(headers)
               if header.group(1) == "[marketplaces.agent-relay-marketplace]"]
    if len(targets) != 1:
        raise ambiguous()
    index = targets[0]
    start = headers[index].end()
    end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
    section = text[start:end]
    fields = {}
    for field in re.finditer(r'''^[ \t]*(source|path|url|ref)[ \t]*=[ \t]*("(?:[^"\\\r\n]|\\.)*"|'[^'\r\n]*')[ \t]*(?:#[^\r\n]*)?\r?$''',
                             section, re.MULTILINE):
        raw = field.group(2)
        fields[field.group(1)] = json.loads(raw) if raw.startswith('"') else raw[1:-1]
    location = fields.get("path") or fields.get("url") or fields.get("source")
    if not location:
        raise ambiguous()
    if "path" in fields or not re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*://|[^/\s]+@[^:\s]+:", location):
        source = {"kind": "directory", "path": location}
    else:
        source = {"kind": "git", "url": location}
        if "ref" in fields:
            source["ref"] = fields["ref"]
    refs = list(re.finditer(r"^([ \t]*)ref[ \t]*=[^\r\n]*(\r\n|\n|$)", section, re.MULTILINE))
    if source["kind"] == "git" and len(refs) != 1:
        raise ambiguous()
    return start, source, refs


def codex_ref_change(text, version):
    """Return a one-line edit, or None for a local source; never write config."""
    validate_version(version)
    start, source, refs = _codex_marketplace(text)
    if source["kind"] == "directory":
        return None
    ref = refs[0]
    replacement = ref.group(1) + 'ref = "v' + version + '"' + ref.group(2)
    return text[:start + ref.start()] + replacement + text[start + ref.end():]


def install(args):
    record = read_record(args.version)
    if record.get("steps", {}).get("publish", {}).get("status") != "ok":
        raise ReleaseError("本版本尚无成功的 publish 记录，请先运行 publish。", "refused", "needs-publish")
    if args.confirm:
        raise ReleaseError("not implemented yet", "refused", "not-implemented")

    claude = claude_source()
    config = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
    text = config.read_bytes().decode("utf-8")
    changed = codex_ref_change(text, args.version)
    _, codex, _ = _codex_marketplace(text)
    commands = []
    if claude["kind"] == "directory":
        commands.append(["git", "-C", claude["path"], "pull", "--ff-only"])
    commands.extend([
        ["claude", "plugin", "marketplace", "update", "agent-relay-marketplace"],
        ["claude", "plugin", "update", "--scope", "user", "agent-relay@agent-relay-marketplace"],
        ["codex", "plugin", "add", "agent-relay@agent-relay-marketplace"],
    ])
    return {"status": "preview", "sources": {"claude": claude, "codex": codex}, "commands": commands,
            "codexConfig": {"path": str(config),
                            "backup": str(state_home() / "release" / (args.version + "-config.toml.bak")),
                            "refChange": changed is not None and changed != text, "ref": "v" + args.version}}


def upgrade(args):
    raise ReleaseError("not implemented yet", "refused", "not-implemented")


def smoke(args):
    raise ReleaseError("not implemented yet", "refused", "not-implemented")


def evidence(args):
    raise ReleaseError("not implemented yet", "refused", "not-implemented")


def parser():
    common = ArgumentParser(add_help=False)
    common.add_argument("--repo", type=Path, default=REPO, help="仓库目录，默认当前检出目录")
    common.add_argument("--remote", default="origin", help="Git 远端名称")
    common.add_argument("--github", help="GitHub 仓库 owner/repo，默认从远端地址解析")
    root = ArgumentParser(description="按步骤检查和执行 agent-relay 发版。")
    commands = root.add_subparsers(dest="step", required=True)
    for name, handler in (("check", check), ("prepare", prepare), ("publish", publish), ("install", install),
                          ("upgrade", upgrade), ("smoke", smoke), ("evidence", evidence)):
        command = commands.add_parser(name, parents=[common], description="agent-relay 发版步骤：" + name)
        command.set_defaults(handler=handler)
        if name == "check":
            command.add_argument("--pr", required=True, type=int, help="已合并的发版 PR 编号")
        else:
            command.add_argument("--version", required=True, help="发版版本号，例如 1.2.3")
        if name in ("publish", "install", "upgrade"):
            command.add_argument("--confirm", action="store_true", help="确认执行写入步骤")
        if name == "evidence":
            command.add_argument("--output", type=Path, help="将汇总写入仓库外的文件")
    return root


def main(argv=None):
    args = argparse.Namespace(step=None, version=None)
    result = {}
    print("正在检查发版命令。")
    try:
        args = parser().parse_args(argv, namespace=args)
        if args.version is not None:
            validate_version(args.version)
        result = args.handler(args)
        result.setdefault("status", "ok")
        exit_code = EXIT_CODES[result["status"]]
        json.dumps(result, ensure_ascii=False)
    except HelpRequested:
        result = {"status": "ok"}
        exit_code = 0
    except ReleaseError as error:
        result = {"status": error.status, "reason": error.reason, "error": str(error)}
        exit_code = EXIT_CODES[error.status]
    except Exception as error:
        result = {"status": "failed", "error": str(error)}
        exit_code = 1
    messages = {"ok": "步骤已完成。", "preview": "预览已生成。", "refused": "已拒绝执行。",
                "waiting-on-user": "等待用户操作。", "failed": "步骤执行失败。"}
    print(messages[result["status"]])
    if result.get("reason") == "not-implemented":
        print("该步骤尚未实现。")
    elif result.get("error"):
        print("原因：" + result["error"])
    report = {**result, "schema": SCHEMA, "step": args.step, "version": args.version}
    print(json.dumps(report, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

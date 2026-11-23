#!/usr/bin/env python3
"""Step-by-step maintainer release commands (D278 output, D286 local records)."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
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


def manifest_of(root):
    """Relative path -> sha256 for every file under root, minus preflight.IGNORED names."""
    root = Path(root)
    manifest = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in _preflight.IGNORED for part in relative.parts) or not path.is_file():
            continue
        manifest[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


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

    manifest = manifest_of(directory / "plugins" / "agent-relay")
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


PLUGIN_ID = "agent-relay@agent-relay-marketplace"


def claude_copy(source):
    """The copy Claude runs, found as preflight.py finds it: the directory source, else the user-scope install."""
    records, marketplaces = _preflight._claude_records()
    items = (records or {}).get("plugins", {}).get(PLUGIN_ID, [])
    item = next((entry for entry in (items if isinstance(items, list) else [])
                 if isinstance(entry, dict) and entry.get("scope") == "user"), {})
    if source["kind"] == "directory":
        path = _preflight._directory_plugin(marketplaces.get("agent-relay-marketplace"))
    else:
        path = item.get("installPath")
    return {"path": str(path) if path else None, "version": item.get("version")}


def codex_copy():
    """The copy Codex runs: plugins/cache/<market>/agent-relay/<version> for the installed version."""
    listing = json.loads(run(["codex", "plugin", "list", "--json"]).stdout)
    for plugin in listing.get("installed", []) if isinstance(listing, dict) else []:
        if not isinstance(plugin, dict) or plugin.get("name") != "agent-relay":
            continue
        market = str(plugin.get("pluginId") or "").partition("@")[2]
        version = plugin.get("version")
        if re.fullmatch(r"[A-Za-z0-9_.-]+", market) and isinstance(version, str) \
                and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
            return {"path": str(home / "plugins" / "cache" / market / "agent-relay" / version), "version": version}
    return {"path": None, "version": None}


def copy_differences(copy, manifest):
    """Empty when the copy matches MANIFEST.json file by file."""
    if not copy["path"] or not Path(copy["path"]).is_dir():
        return {"copy": "not-found"}
    found = manifest_of(copy["path"])
    differences = {"missing": sorted(set(manifest) - set(found)), "extra": sorted(set(found) - set(manifest)),
                   "changed": sorted(name for name in set(manifest) & set(found) if manifest[name] != found[name])}
    return {kind: names for kind, names in differences.items() if names}


def _prepare_clone(path, tag_commit, pull):
    """Refuse an unready clone before touching it; fast-forward it to the tag's commit when it is behind."""
    git = ["git", "-C", path]

    def not_clean(message):
        return ReleaseError("Claude 的本地 clone " + message + "，未做任何改动。", "refused", "clone-not-clean")

    try:
        dirty = run([*git, "status", "--porcelain"]).stdout.strip()
        branch = run([*git, "symbolic-ref", "--short", "-q", "HEAD"]).stdout.strip()
        head = run([*git, "rev-parse", "HEAD"]).stdout.strip()
    except subprocess.CalledProcessError:
        raise not_clean("无法读取状态")
    if dirty:
        raise not_clean("有未提交的改动")
    if branch != "main":
        raise not_clean("不在 main 分支")
    if head == tag_commit:
        return False
    try:
        run([*git, "fetch"], timeout=300)
        run([*git, "merge-base", "--is-ancestor", "HEAD", tag_commit])
    except subprocess.CalledProcessError:
        raise not_clean("无法快进到 tag 所在提交")
    run(pull, timeout=300)
    if run([*git, "rev-parse", "HEAD"]).stdout.strip() != tag_commit:
        raise ReleaseError("Claude 的本地 clone 快进后不在 tag 所在提交。", "refused", "clone-not-at-tag")
    return True


def install(args):
    record = read_record(args.version)
    steps = record.get("steps", {})
    if steps.get("publish", {}).get("status") != "ok":
        raise ReleaseError("本版本尚无成功的 publish 记录，请先运行 publish。", "refused", "needs-publish")

    claude = claude_source()
    config = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
    text = config.read_bytes().decode("utf-8")
    changed = codex_ref_change(text, args.version)
    _, codex, _ = _codex_marketplace(text)
    backup = state_home() / "release" / (args.version + "-config.toml.bak")
    pull = ["git", "-C", claude["path"], "pull", "--ff-only"] if claude["kind"] == "directory" else None
    host_commands = [
        ["claude", "plugin", "marketplace", "update", "agent-relay-marketplace"],
        ["claude", "plugin", "update", "--scope", "user", PLUGIN_ID],
        ["codex", "plugin", "add", PLUGIN_ID],
    ]
    if not args.confirm:
        return {"status": "preview", "sources": {"claude": claude, "codex": codex},
                "commands": ([pull] if pull else []) + host_commands,
                "codexConfig": {"path": str(config), "backup": str(backup),
                                "refChange": changed is not None and changed != text, "ref": "v" + args.version}}

    prepared = steps.get("prepare", {})
    try:
        manifest = json.loads((Path(prepared["dir"]) / "MANIFEST.json").read_text(encoding="utf-8"))
    except (KeyError, TypeError, OSError, ValueError):
        manifest = None
    if prepared.get("status") != "ok" or not isinstance(manifest, dict):
        raise ReleaseError("找不到本版本 prepare 生成的 MANIFEST.json，请先重新运行 prepare。",
                           "refused", "needs-prepare")
    tag_commit = steps["publish"]["peeledCommit"]

    ran, skipped = [], []
    if pull:
        (ran if _prepare_clone(claude["path"], tag_commit, pull) else skipped).append(pull)
    for command in host_commands[:2]:
        run(command, timeout=300)
        ran.append(command)
    ref_changed = changed is not None and changed != text
    if changed is not None and not ref_changed:
        skipped.append(["write", str(config)])
    else:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(config, backup)
        if ref_changed:
            config.write_bytes(changed.encode("utf-8"))
    run(host_commands[2], timeout=300)
    ran.append(host_commands[2])

    hosts = {"claude": claude_copy(claude), "codex": codex_copy()}
    differences = {host: found for host, copy in hosts.items() if (found := copy_differences(copy, manifest))}
    facts = {"status": "ok", "hosts": hosts, "ran": ran, "skipped": skipped,
             "codexConfig": {"path": str(config), "backup": str(backup) if backup.exists() else None,
                             "refChanged": ref_changed},
             "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if differences:
        lines = [{"claude": "Claude", "codex": "Codex"}[host] + " " + kind + " " +
                 (", ".join(names) if isinstance(names, list) else names)
                 for host, found in differences.items() for kind, names in found.items()]
        facts.update({"status": "failed", "reason": "copy-mismatch", "differences": differences,
                      "error": "宿主副本与 MANIFEST.json 不一致：" + "；".join(lines)})
    write_record(record, "install", facts)
    return facts


def upgrade(args):
    """D283: never stops a bridge, never rolls back; the user closes the sessions using the mailbox."""
    record = read_record(args.version)
    steps = record.get("steps", {})
    checked = steps.get("check", {})
    if checked.get("status") != "ok":
        raise ReleaseError("本版本尚无成功的 check 记录，请先运行 check。", "refused", "needs-check")
    if checked.get("runtimeUpgrade") is False:
        facts = {"status": "ok", "skipped": True, "message": "本版本没有改动运行时文件，无需升级运行时。"}
        write_record(record, "upgrade", facts)
        return facts
    installed = steps.get("install", {})
    copy = ((installed.get("hosts") or {}).get("claude") or {}).get("path")
    if installed.get("status") != "ok" or not copy:
        raise ReleaseError("本版本尚无成功的 install 记录，请先运行 install。", "refused", "needs-install")

    script = str(Path(copy) / "hooks" / "native_collaboration_runtime.py")
    command = ["python3", "-B", script, "upgrade", "--confirm"]
    running = _runtime._servers_running(_runtime.default_root())
    if not args.confirm:
        return {"status": "preview", "running": running, "command": command}
    if running:
        facts = {"status": "waiting-on-user", "running": running, "command": command,
                 "message": "仍有 " + str(running) + " 个 bridge 在运行，未做任何改动。请用户关闭所有使用信箱的会话"
                            "（Claude Code 会话，并用 ⌘Q 退出 ChatGPT），之后再运行 upgrade --confirm。"}
        write_record(record, "upgrade", facts)
        return facts

    try:
        output = run(command, timeout=900).stdout
    except subprocess.CalledProcessError as error:
        output = error.stdout or ""
    lines = [line for line in output.splitlines() if line.strip()]
    try:
        result = json.loads(lines[-1])
    except (IndexError, ValueError):
        result = {}
    state = result.get("state") if isinstance(result, dict) else None
    if state in ("upgraded", "current"):
        facts = {"status": "ok", "state": state, "previous": result.get("previous"), "backup": result.get("backup")}
        write_record(record, "upgrade", facts)
        return facts
    recovery = [["python3", "-B", script, step, "--confirm"] for step in ("rollback", "recover")]
    facts = {"status": "failed", "reason": "runtime-upgrade-failed", "state": state, "recovery": recovery,
             "diagnostic": result.get("diagnostic") if isinstance(result, dict) else None,
             "error": "运行时升级未成功，未自动回滚或恢复。需要时请用户确认后自行运行：" +
                      "；".join(" ".join(item) for item in recovery)}
    write_record(record, "upgrade", facts)
    return facts


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
    if result.get("message"):
        print(result["message"])
    if result.get("reason") == "not-implemented":
        print("该步骤尚未实现。")
    elif result.get("error"):
        print("原因：" + result["error"])
    report = {**result, "schema": SCHEMA, "step": args.step, "version": args.version}
    print(json.dumps(report, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

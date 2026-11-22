#!/usr/bin/env python3
"""Step-by-step maintainer release commands (D278 output, D286 local records)."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
SCHEMA = "agent-relay.release/v1"
EXIT_CODES = {"ok": 0, "preview": 0, "refused": 2, "waiting-on-user": 3, "failed": 1}

_runtime_spec = importlib.util.spec_from_file_location(
    "release_native_runtime", REPO / "plugins" / "agent-relay" / "hooks" / "native_collaboration_runtime.py")
_runtime = importlib.util.module_from_spec(_runtime_spec)
_runtime_spec.loader.exec_module(_runtime)
state_home = _runtime.state_home


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


def run(args, timeout=30):
    """The only process entry point; callers pass an argument list."""
    return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
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


def check(args):
    raise ReleaseError("not implemented yet", "refused", "not-implemented")


def prepare(args):
    raise ReleaseError("not implemented yet", "refused", "not-implemented")


def publish(args):
    raise ReleaseError("not implemented yet", "refused", "not-implemented")


def install(args):
    raise ReleaseError("not implemented yet", "refused", "not-implemented")


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

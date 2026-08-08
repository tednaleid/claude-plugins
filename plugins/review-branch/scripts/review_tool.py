#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["markdown-it-py"]
# ///

# ABOUTME: review-branch tool: renders review.toml to a collaborative HTML tracker,
# ABOUTME: runs the review daemon, merges browser state, emits posting manifests

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

__version__ = "0.2.0"
APP_NAME = "review-branch"
DEFAULT_PORT = 43117

SUBCOMMANDS = ("init", "render", "open", "status", "manifest", "install", "daemon", "stop")


def data_root() -> Path:
    override = os.environ.get("REVIEW_BRANCH_HOME")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME", "~/.local/share")
    return Path(xdg).expanduser() / APP_NAME


def state_root() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME", "~/.local/state")
    return Path(xdg).expanduser() / APP_NAME


def git(cwd, *args, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_ok(cwd, *args) -> str | None:
    try:
        return git(cwd, *args)
    except RuntimeError:
        return None


def main_worktree(repo_dir: Path) -> Path:
    common = git(repo_dir, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common).parent


def repo_id(repo_dir: Path) -> str:
    root = main_worktree(repo_dir)
    seed = git_ok(repo_dir, "remote", "get-url", "origin") or str(root)
    digest = hashlib.sha256(seed.encode()).hexdigest()[:4]
    return f"{root.name}-{digest}"


def ensure_data_repo() -> Path:
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").is_dir():
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        git(root, "config", "user.name", APP_NAME)
        git(root, "config", "user.email", f"{APP_NAME}@localhost")
    return root


def data_commit(message: str) -> None:
    root = ensure_data_repo()
    git(root, "add", "-A")
    if git(root, "status", "--porcelain"):
        git(root, "commit", "-q", "-m", message)


def cmd_init(slug: str, repo_dir: Path) -> Path:
    ensure_data_repo()
    base = data_root() / repo_id(repo_dir) / slug
    existing = []
    for p in base.glob("round-*"):
        tail = p.name.removeprefix("round-")
        if p.is_dir() and tail.isdigit():
            existing.append(int(tail))
    round_dir = base / f"round-{max(existing, default=0) + 1}"
    round_dir.mkdir(parents=True)
    return round_dir.resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review-branch", description="review-branch tool")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    p_init = sub.add_parser("init", help="create the next round directory for a review")
    p_init.add_argument("--slug", required=True)
    for name in ("render", "open", "status", "manifest"):
        p = sub.add_parser(name)
        p.add_argument("review_dir")
    sub.add_parser("install", help="copy scripts to the bin dir")
    sub.add_parser("daemon", help="run the server in the foreground")
    sub.add_parser("stop", help="stop the daemon via pidfile")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2
    if args.command == "init":
        print(cmd_init(args.slug, Path.cwd()))
        return 0
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

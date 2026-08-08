#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["markdown-it-py"]
# ///

# ABOUTME: review-branch tool: renders review.toml to a collaborative HTML tracker,
# ABOUTME: runs the review daemon, merges browser state, emits posting manifests

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from markdown_it import MarkdownIt

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


def load_review(round_dir: Path) -> dict:
    path = round_dir / "review.toml"
    try:
        return tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise SystemExit(f"{path}: {e}")


def load_state(round_dir: Path) -> dict:
    path = round_dir / "state.json"
    if not path.exists():
        return {"findings": {}}
    return json.loads(path.read_text())


def merged_findings(review: dict, state: dict) -> list[dict]:
    out = []
    entries = state.get("findings", {})
    for f in review.get("findings", []):
        s = entries.get(f["id"], {})
        crev = f.get("comment_rev", 1)
        edited = s.get("edited_comment")
        edited_current = edited is not None and s.get("edited_comment_rev") == crev
        note = s.get("note")
        merged = dict(f)
        merged.update(
            disposition=s.get("disposition"),
            note=note,
            note_stale=note is not None and s.get("note_rev", 0) < crev,
            edited_comment=edited,
            edited_stale=edited is not None and not edited_current,
            postable_body=edited if edited_current else f.get("comment"),
            posted=bool(f.get("posted_url")),
        )
        out.append(merged)
    return out


def parse_anchor(finding: dict) -> tuple[str, int | None]:
    anchor = finding.get("anchor")
    if anchor and ":" in anchor:
        path, _, line = anchor.rpartition(":")
        if line.isdigit():
            return path, int(line)
    nums = re.findall(r"\d+", str(finding.get("lines", "")))
    return finding["file"], int(nums[-1]) if nums else None


def cmd_status(round_dir: Path) -> dict:
    review = load_review(round_dir)
    return {
        "review": review.get("review", {}),
        "findings": merged_findings(review, load_state(round_dir)),
    }


def cmd_manifest(round_dir: Path, exclude: set[str]) -> list[dict]:
    entries = []
    for f in merged_findings(load_review(round_dir), load_state(round_dir)):
        if f["disposition"] != "post" or f["posted"] or f["id"] in exclude:
            continue
        if f.get("commentable", True) is False:
            continue
        path, line = parse_anchor(f)
        body = f["postable_body"]
        if line is None or not body:
            raise SystemExit(
                f"{f['id']}: cannot build manifest entry (line={line}, body empty={not body})"
            )
        entries.append({"file": path, "line": line, "body": body})
    return entries


_MD = MarkdownIt("commonmark").enable("table")


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def md_html(text: str) -> str:
    return _MD.render(text or "")


def diff_link(meta: dict, path: str, line: int | None) -> str | None:
    url = meta.get("url")
    if not url:
        return None
    if meta.get("vcs") == "glab":
        return f"{url}/diffs#diff-content-{hashlib.sha1(path.encode()).hexdigest()}"
    if meta.get("vcs") == "gh":
        frag = f"diff-{hashlib.sha256(path.encode()).hexdigest()}"
        if line:
            frag += f"R{line}"
        return f"{url}/files#{frag}"
    return None


def version_token(round_dir: Path) -> str:
    digest = hashlib.sha1()
    names = ["review.toml", "state.json"]
    review_path = round_dir / "review.toml"
    if review_path.exists():
        names += [a.get("path", "") for a in load_review(round_dir).get("assets", [])]
    for name in names:
        p = round_dir / name
        if name and p.exists():
            st = p.stat()
            digest.update(f"{name}:{st.st_mtime_ns}:{st.st_size};".encode())
    return digest.hexdigest()[:16]


def route_for(round_dir: Path) -> str:
    root = data_root().resolve()
    try:
        rel = round_dir.resolve().relative_to(root)
    except ValueError:
        raise SystemExit(f"{round_dir} is not under the data root {root}")
    if len(rel.parts) != 3:
        raise SystemExit(f"{round_dir}: expected <repo-id>/<slug>/round-N under the data root")
    return "/".join(rel.parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review-branch", description="review-branch tool")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    p_init = sub.add_parser("init", help="create the next round directory for a review")
    p_init.add_argument("--slug", required=True)
    for name in ("render", "open", "status", "manifest"):
        p = sub.add_parser(name)
        p.add_argument("review_dir")
    p_manifest = sub._name_parser_map["manifest"]
    p_manifest.add_argument("--exclude", default="")
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
    if args.command == "status":
        print(json.dumps(cmd_status(Path(args.review_dir)), indent=2))
        return 0
    if args.command == "manifest":
        exclude = {x for x in args.exclude.split(",") if x}
        print(json.dumps(cmd_manifest(Path(args.review_dir), exclude), indent=2))
        return 0
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

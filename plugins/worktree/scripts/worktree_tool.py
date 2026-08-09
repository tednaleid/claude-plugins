#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///

# ABOUTME: creates a git worktree under .claude/worktrees and bootstraps it
# ABOUTME: copies gitignored env files, runs direnv/lockfile setup, applies .worktree.toml hooks

import argparse
import fnmatch
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ENV_GLOBS = (".env", ".env.*", ".envrc")


def run(cwd, *args, check=True, capture=True):
    try:
        out = subprocess.run(list(args), cwd=str(cwd), text=True,
                             capture_output=capture, check=False)
    except FileNotFoundError:
        if check:
            raise SystemExit(f"{args[0]} not found")
        return subprocess.CompletedProcess(list(args), 127, "", f"{args[0]}: not found")
    if check and out.returncode != 0:
        err = out.stderr.strip() if capture else ""
        raise SystemExit(f"{' '.join(args)} failed: {err}")
    return out


def slug_dir(branch):
    return branch.replace("/", "-")


def env_files_to_copy(gitignored_paths):
    keep = []
    for path in gitignored_paths:
        if "/" in path:
            continue
        if any(fnmatch.fnmatch(path, glob) for glob in ENV_GLOBS):
            keep.append(path)
    return keep


def load_hooks(repo_root):
    empty = {"copy": [], "symlink": [], "command": []}
    path = Path(repo_root) / ".worktree.toml"
    if not path.exists():
        return empty
    data = tomllib.loads(path.read_text())
    return {
        "copy": data.get("copy", []),
        "symlink": data.get("symlink", []),
        "command": data.get("command", []),
    }


def detect_vcs(repo_root):
    remote = run(repo_root, "git", "remote", "get-url", "origin", check=False).stdout
    if "gitlab" in remote:
        return "glab"
    if "github" in remote:
        return "gh"
    return "local"


def resolve_branch(arg, vcs, repo_root):
    """Resolve an MR/PR number, an MR/PR URL, or a branch name to a branch."""
    text = (arg or "").strip()
    if not text:
        return run(repo_root, "git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if "/merge_requests/" in text:
        text = text.rstrip("/").split("/merge_requests/")[-1].split("/")[0]
        vcs = "glab"
    elif "/pull/" in text:
        text = text.rstrip("/").split("/pull/")[-1].split("/")[0]
        vcs = "gh"
    if text.isdigit():
        if vcs == "glab":
            out = run(repo_root, "glab", "mr", "view", text, "--output", "json")
            return json.loads(out.stdout)["source_branch"]
        if vcs == "gh":
            out = run(repo_root, "gh", "pr", "view", text,
                      "--json", "headRefName", "--jq", ".headRefName")
            return out.stdout.strip()
        raise SystemExit(f"{text} looks like an MR/PR number but no gitlab/github remote")
    return text


def gitignored_files(repo_root):
    out = run(repo_root, "git", "ls-files", "--others", "--ignored",
              "--exclude-standard")
    return [line for line in out.stdout.splitlines() if line]


def create_worktree(repo_root, branch, dest):
    run(repo_root, "git", "fetch", "origin", check=False)
    dest.parent.mkdir(parents=True, exist_ok=True)
    origin_ref = f"origin/{branch}"
    exists = run(repo_root, "git", "rev-parse", "--verify", origin_ref,
                 check=False).returncode == 0
    if exists:
        run(repo_root, "git", "worktree", "add", str(dest), origin_ref)
    else:
        local = run(repo_root, "git", "rev-parse", "--verify", branch,
                    check=False).returncode == 0
        if local:
            run(repo_root, "git", "worktree", "add", str(dest), branch)
        else:
            run(repo_root, "git", "worktree", "add", "-b", branch, str(dest), "HEAD")


def copy_env_files(repo_root, dest):
    copied = []
    for name in env_files_to_copy(gitignored_files(repo_root)):
        src = Path(repo_root) / name
        if src.is_file():
            (dest / name).write_bytes(src.read_bytes())
            copied.append(name)
    return copied


def parent_direnv_allowed(repo_root):
    """True only when direnv confirms the parent .envrc is allowed.

    This gates whether we run `direnv allow` on the new worktree's .envrc, so
    it fails closed: any parse failure, missing .envrc, or unrecognized
    status returns False rather than risk auto-allowing an untrusted file.

    direnv's JSON status reports state.foundRC.allowed as an enum (0 allowed,
    1 not allowed, 2 denied); older direnv's text output instead printed
    "Found RC allowed true"/"false". Prefer JSON; fall back to text matching
    both the old boolean form and the new enum's allowed value.
    """
    out = run(repo_root, "direnv", "status", "--json", check=False)
    if out.returncode == 0:
        try:
            found_rc = json.loads(out.stdout)["state"]["foundRC"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return False
        if not isinstance(found_rc, dict):
            return False
        return found_rc.get("allowed") == 0
    text = run(repo_root, "direnv", "status", check=False).stdout
    return "Found RC allowed true" in text or "Found RC allowed 0" in text


def bootstrap(repo_root, dest):
    """direnv when an .envrc is present and the parent was allowed, else lockfile setup."""
    if (dest / ".envrc").exists() and parent_direnv_allowed(repo_root):
        run(dest, "direnv", "allow", str(dest), check=False)
        return "direnv allow"
    if (dest / "pyproject.toml").exists():
        run(dest, "uv", "sync", "--all-groups", check=False)
        return "uv sync"
    if (dest / "bun.lock").exists() or (dest / "bunfig.toml").exists():
        run(dest, "bun", "install", check=False)
        return "bun install"
    if (dest / "pnpm-lock.yaml").exists():
        run(dest, "pnpm", "install", check=False)
        return "pnpm install"
    if (dest / "package-lock.json").exists():
        run(dest, "npm", "install", check=False)
        return "npm install"
    return "no bootstrap"


def apply_hooks(repo_root, dest, hooks):
    applied = []
    for entry in hooks["copy"]:
        src = Path(repo_root) / entry["from"]
        if src.exists():
            (dest / entry["to"]).write_bytes(src.read_bytes())
            applied.append(f"copy {entry['from']}")
    for entry in hooks["symlink"]:
        target = dest / entry["to"]
        if not target.exists():
            target.symlink_to(Path(repo_root) / entry["from"])
            applied.append(f"symlink {entry['from']}")
    for entry in hooks["command"]:
        run(dest, "sh", "-c", entry["run"], check=False, capture=False)
        applied.append(f"run {entry['run']}")
    return applied


def main():
    parser = argparse.ArgumentParser(
        description="Create and bootstrap a git worktree under .claude/worktrees/."
    )
    parser.add_argument("target", nargs="?",
                        help="MR/PR number, MR/PR URL, or branch name (default: current branch)")
    args = parser.parse_args()

    repo_root = run(Path.cwd(), "git", "rev-parse", "--show-toplevel").stdout.strip()
    vcs = detect_vcs(repo_root)
    branch = resolve_branch(args.target, vcs, repo_root)
    dest = Path(repo_root) / ".claude" / "worktrees" / slug_dir(branch)
    if dest.exists():
        raise SystemExit(f"worktree already exists: {dest}")

    create_worktree(repo_root, branch, dest)
    copied = copy_env_files(repo_root, dest)
    step = bootstrap(repo_root, dest)
    applied = apply_hooks(repo_root, dest, load_hooks(repo_root))

    print(str(dest))
    summary = [f"branch {branch}", f"bootstrap: {step}"]
    if copied:
        summary.append("copied: " + ", ".join(copied))
    if applied:
        summary.append("hooks: " + ", ".join(applied))
    print("  " + " | ".join(summary), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

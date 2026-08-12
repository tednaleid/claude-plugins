#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///

# ABOUTME: `wt` CLI to manage git worktrees under .claude/worktrees (create/list/remove/install)
# ABOUTME: create bootstraps env files, direnv/lockfile setup, and .worktree.toml hooks

import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ENV_GLOBS = (".env", ".env.*", ".envrc")

VERSION = "0.3.2"  # SYNC_PLUGIN_VERSION kept in step with plugin.json by scripts/sync-marketplace.ts


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


def phase(level, msg):
    """Progress line to stderr; silent at quiet level 0."""
    if level >= 1:
        print(f"  {msg}", file=sys.stderr)


def stream_level(args):
    """Verbosity for create: 0 quiet, 1 phase lines, 2 also stream subprocess output.

    -q/-v override; otherwise stream when stderr is a terminal (a human is
    watching) and stay at phase-lines-only when it is piped (an agent runs it).
    """
    if "-q" in args or "--quiet" in args:
        return 0
    if "-v" in args or "--verbose" in args:
        return 2
    return 2 if sys.stderr.isatty() else 1


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


def bootstrap(repo_root, dest, level):
    """direnv when an .envrc is present and the parent was allowed, else lockfile setup."""
    if (dest / ".envrc").exists() and parent_direnv_allowed(repo_root):
        label, cmd = "direnv allow", ("direnv", "allow", str(dest))
    elif (dest / "pyproject.toml").exists():
        label, cmd = "uv sync", ("uv", "sync", "--all-groups")
    elif (dest / "bun.lock").exists() or (dest / "bunfig.toml").exists():
        label, cmd = "bun install", ("bun", "install")
    elif (dest / "pnpm-lock.yaml").exists():
        label, cmd = "pnpm install", ("pnpm", "install")
    elif (dest / "package-lock.json").exists():
        label, cmd = "npm install", ("npm", "install")
    else:
        return "no bootstrap"
    phase(level, f"bootstrap: {label}")
    out = run(dest, *cmd, check=False, capture=level < 2)
    if out.returncode != 0:
        detail = (out.stderr or out.stdout or "").rstrip()
        if detail:
            print(detail, file=sys.stderr)
        print(f"  bootstrap failed: {label} (exit {out.returncode})", file=sys.stderr)
        return f"{label} (failed)"
    return label


def apply_hooks(repo_root, dest, hooks, level):
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
        phase(level, f"run {entry['run']}")
        out = run(dest, "sh", "-c", entry["run"], check=False, capture=level < 2)
        if out.returncode != 0:
            detail = (out.stderr or out.stdout or "").rstrip()
            if detail:
                print(detail, file=sys.stderr)
            print(f"  hook failed: {entry['run']} (exit {out.returncode})", file=sys.stderr)
        applied.append(f"run {entry['run']}")
    return applied


def repo_root_cwd():
    return run(Path.cwd(), "git", "rev-parse", "--show-toplevel").stdout.strip()


def cmd_create(args, repo_root):
    unknown = [a for a in args
               if a.startswith("-") and a not in ("-q", "--quiet", "-v", "--verbose")]
    if unknown:
        raise SystemExit(f"create: unknown option {unknown[0]} (try `wt create --help`)")
    level = stream_level(args)
    positional = [a for a in args if not a.startswith("-")]
    target = positional[0] if positional else None
    vcs = detect_vcs(repo_root)
    branch = resolve_branch(target, vcs, repo_root)
    dest = Path(repo_root) / ".claude" / "worktrees" / slug_dir(branch)
    if dest.exists():
        raise SystemExit(f"worktree already exists: {dest}")

    phase(level, f"worktree add {branch}")
    create_worktree(repo_root, branch, dest)
    copied = copy_env_files(repo_root, dest)
    if copied:
        phase(level, "copy env: " + ", ".join(copied))
    step = bootstrap(repo_root, dest, level)
    applied = apply_hooks(repo_root, dest, load_hooks(repo_root), level)

    print(str(dest))
    summary = [f"branch {branch}", f"bootstrap: {step}"]
    if copied:
        summary.append("copied: " + ", ".join(copied))
    if applied:
        summary.append("hooks: " + ", ".join(applied))
    print("  " + " | ".join(summary), file=sys.stderr)
    return 0


def parse_worktrees(porcelain):
    """Parse `git worktree list --porcelain` into [{path, head, branch}]."""
    entries = []
    current = {}
    for line in porcelain.splitlines():
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current = {"path": line[len("worktree "):], "head": "", "branch": "(detached)"}
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):][:8]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):].removeprefix("refs/heads/")
    if current:
        entries.append(current)
    return entries


def match_worktrees(entries, terms):
    """Keep entries where every term is a substring of the path or branch."""
    return [e for e in entries
            if all(t in f"{e['path']} {e['branch']}" for t in terms)]


def list_worktrees(repo_root):
    out = run(repo_root, "git", "worktree", "list", "--porcelain")
    return parse_worktrees(out.stdout)


def cmd_list(args, repo_root):
    entries = match_worktrees(list_worktrees(repo_root), args)
    if not entries:
        print("no worktrees match" if args else "no worktrees", file=sys.stderr)
        return 0
    width = max(len(e["branch"]) for e in entries)
    for e in entries:
        print(f"{e['branch']:<{width}}  {e['head']}  {e['path']}")
    return 0


def cmd_remove(args, repo_root):
    force = "--force" in args or "-f" in args
    terms = [a for a in args if not a.startswith("-")]
    main_path = str(Path(repo_root))
    candidates = [e for e in list_worktrees(repo_root) if e["path"] != main_path]
    matches = match_worktrees(candidates, terms)
    if not matches:
        raise SystemExit(f"no worktree matches {' '.join(terms) or '(empty)'}")
    if len(matches) > 1:
        listed = "\n".join(f"  {e['branch']}  {e['path']}" for e in matches)
        raise SystemExit(f"ambiguous; {len(matches)} worktrees match:\n{listed}")
    path = matches[0]["path"]
    cmd = ["git", "worktree", "remove"]
    if force:
        cmd.append("--force")
    cmd.append(path)
    run(repo_root, *cmd)
    print(f"removed {path}")
    return 0


def bin_dir():
    return Path(os.environ.get("WORKTREE_BIN", "~/.local/bin")).expanduser()


def cmd_install():
    dest_dir = bin_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "wt"
    shutil.copy2(Path(__file__).resolve(), dest)
    dest.chmod(0o755)
    print(f"installed {dest}")
    return 0


def cmd_version():
    print(f"wt {VERSION}")
    return 0


VERBS = ("create", "list", "remove", "install", "version")


def resolve(argv):
    """Map argv to (verb, remaining_args): prefix-matched verbs, `list` default.

    A bare invocation, a leading option, or an unmatched first token all fall
    through to `list` (with the tokens as filter terms). `--` forces the rest
    to be list filter terms even when they look like a verb.
    """
    if not argv:
        return "list", argv
    if argv[0] == "--":
        return "list", argv[1:]
    if argv[0].startswith("-"):
        return "list", argv
    hits = [v for v in VERBS if v.startswith(argv[0])]
    if len(hits) == 1:
        return hits[0], argv[1:]
    if not hits:
        return "list", argv
    raise SystemExit(f"ambiguous verb {argv[0]!r}: {', '.join(hits)}")


USAGE = """\
wt - manage git worktrees under .claude/worktrees/

  wt [list] [filter...]      list worktrees (default), optionally filtered
  wt create [target]         create+bootstrap a worktree (MR/PR number, URL,
                             branch name, or current branch)
  wt remove [--force] <t>    remove the one worktree matching <t>
  wt install                 copy this script to ~/.local/bin/wt
  wt version                 print the wt version (also `wt --version`)

Verbs prefix-match (wt cr foo == wt create foo). Use `--` to force the rest to
be a list filter (wt -- create lists worktrees matching "create").

Run `wt <verb> --help` (or `wt help <verb>`) for details on a verb.
"""


HELP = {
    "create": """\
wt create [-q|-v] [target]   create and bootstrap a worktree

  target          MR/PR number, MR/PR URL, branch name, or omit for current branch
  -q, --quiet     only the final summary line
  -v, --verbose   stream bootstrap output even when stderr is not a terminal

Makes .claude/worktrees/<slug> from origin/<branch> (else a local branch or
HEAD), copies gitignored .env*/.envrc from the main worktree, bootstraps
(direnv when the parent .envrc was allowed, else uv/bun/pnpm/npm by lockfile),
and applies any .worktree.toml hooks. Prints the path on stdout and progress on
stderr; bootstrap output streams live at a terminal and stays quiet when piped.
""",
    "list": """\
wt [list] [filter...]        list worktrees (the default command)

  filter          substrings matched against each worktree's branch and path

Bare `wt` runs this. With no filter it lists every worktree.
""",
    "remove": """\
wt remove [--force] <filter...>   remove the one worktree matching <filter>

  filter          substrings matched against branch and path
  -f, --force     pass --force to git worktree remove (discard a dirty tree)

Refuses when more than one worktree matches, and never removes the main
worktree. Branch deletion stays manual.
""",
    "install": """\
wt install                   copy this script to ~/.local/bin/wt

Set WORKTREE_BIN to install elsewhere; make sure that directory is on PATH.
""",
    "version": """\
wt version                   print the wt version (matches the plugin release)

Also available as `wt --version`.
""",
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        topic = argv[1:]
        if topic:
            hits = [v for v in VERBS if v.startswith(topic[0])]
            print(HELP[hits[0]] if len(hits) == 1 else USAGE)
        else:
            print(USAGE)
        return 0
    if argv and argv[0] in ("-V", "--version"):
        return cmd_version()
    verb, rest = resolve(argv)
    if any(a in ("-h", "--help") for a in rest):
        print(HELP.get(verb, USAGE))
        return 0
    if verb == "version":
        return cmd_version()
    if verb == "install":
        return cmd_install()
    repo_root = repo_root_cwd()
    if verb == "create":
        return cmd_create(rest, repo_root)
    if verb == "list":
        return cmd_list(rest, repo_root)
    if verb == "remove":
        return cmd_remove(rest, repo_root)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

# worktree

Create and manage git worktrees for reviewing an MR/PR or working on a branch in isolation.
The `/worktree` skill drives it for agents (create a worktree, then enter it); the `wt` CLI is
the same script for driving it by hand.

## Create targets

- An **MR number** (GitLab remote, e.g. `124`) -- resolves the source branch via `glab mr view`.
- A **PR number** (GitHub remote) -- resolves via `gh pr view`.
- An **MR or PR URL** -- extracts the number, resolves as above.
- A **branch name** -- uses it directly.
- **Nothing** -- uses the current branch.

Create then:

1. Makes `.claude/worktrees/<slug>` from `origin/<branch>` (or a local branch / HEAD as fallback).
2. Copies gitignored env files (`.env`, `.env.*`, `.envrc`) from the main worktree.
3. Bootstraps via `direnv allow` when the parent `.envrc` was allowed; otherwise `uv sync` /
   `bun install` / `pnpm install` / `npm install` by lock file.
4. Applies any `.worktree.toml` hooks, prints the path on stdout and a summary on stderr.

Before a JS install, `create` seeds the new worktree's `node_modules` with a copy-on-write
clone of the main worktree's (APFS `clonefile`, or `cp --reflink` on btrfs/XFS), which shares
storage extents rather than duplicating them. The install then runs normally and reconciles the
seed against the lock file, so it stays the thing that makes the tree correct. On a 400MB
`node_modules` this turns a cold install into a near-noop. It is skipped when the worktree
already has a `node_modules`, and any failure falls through to a normal install.

`create` is idempotent. Against a worktree that already exists it reuses it and exits 0, so
stdout is always the path to the worktree for that target. The checkout is left untouched, but
steps 2-4 all run again, which finishes a setup that was interrupted partway. These worktrees
are disposable, so copies overwrite: an `.env` edited inside the worktree loses to the main
worktree's copy, and `[[command]]` hooks run every time. To land in an existing worktree
without re-running setup, `cd` to it instead.

A worktree directory deleted outright is recreated (`create` prunes the stale registration that
otherwise makes `git worktree add` refuse the path). A directory that exists but holds no
checkout, such as one left behind by `rm -rf`, is an error rather than a silent reuse.

## Install the plugin (for the `/worktree` skill)

```bash
claude plugin install worktree@tednaleid
```

Invoke with `/worktree <mr-or-pr-or-branch>`, or just describe what you want ("worktree MR 124
for review", "set up a worktree for feature/auth-fix").

## Install the `wt` CLI (to drive it by hand)

Running the `/worktree` skill installs and refreshes `wt` in `~/.local/bin` automatically, so
in most cases you get it for free. To install it without invoking the skill, from a checkout
of this repo:

```bash
plugins/worktree/scripts/worktree_tool.py install   # copies the script to ~/.local/bin/wt
```

Set `WORKTREE_BIN` to install somewhere other than `~/.local/bin`, and make sure that directory
is on your PATH. The installed `wt` is a snapshot copy that runs through a `uv` shebang, so its
dependency-free script resolves with no extra setup.

```
wt [list] [filter...]      list worktrees (default), optionally filtered
wt create [-q|-v] [target] create + bootstrap a worktree (see targets above)
wt remove [--force] <t>    remove the one worktree matching <t>
wt install                 copy this script to ~/.local/bin/wt
wt version                 print the wt version (also `wt --version`)
```

`list`/`remove` match by substring against branch and path; `remove` refuses when more than one
worktree matches and never touches the main worktree. Branch deletion stays manual.

Verbs prefix-match, so `wt cr foo` is `wt create foo` and `wt re foo` is `wt remove foo`. Use
`--` to force the rest to be a list filter even when it looks like a verb: `wt -- create`. Every
verb has help: `wt create --help` or `wt help create`.

`create` prints its progress on stderr and the worktree path on stdout. Bootstrap
(`uv sync`/`npm install`/...) can take a while; its live output streams when stderr is a
terminal and is suppressed when the output is piped (so an agent driving the script does not
collect the install log). `-v`/`--verbose` forces streaming; `-q`/`--quiet` drops to just the
final summary line. A failed bootstrap or hook is reported rather than silently swallowed.
Streamed output goes to stderr even though the child writes it to stdout, so stdout is the
worktree path and nothing else and `wt_path=$(wt create ...)` is safe from a terminal.

## Changing directory

`wt` cannot `cd` your shell (no child process can), so jumping into a worktree stays a shell
function. A minimal fuzzy jumper:

```zsh
wcd () {
  local worktree
  worktree=$(git worktree list | fzf --query="$1" --select-1 --exit-0 | awk '{print $1}')
  [[ -n "$worktree" ]] && cd "$worktree"
}
```

It reads `git worktree list`, so it works for any worktree regardless of how it was made.

To create-or-jump in one step, lean on `create` being idempotent and printing the path on
stdout. Run it from the main worktree, since `wt` resolves `.claude/worktrees/` against the
current checkout's root and would otherwise nest one worktree inside another:

```zsh
wtcd () {
  local main path
  main=$(git worktree list --porcelain | head -1 | cut -d' ' -f2-)
  path=$(cd "$main" && wt create "$@") || return
  cd "$path"
}
```

Only stdout is captured, so stderr stays on the terminal and bootstrap output streams live.

## Per-repo hooks

A `.worktree.toml` at the repo root adds setup beyond the defaults:

```toml
[[copy]]
from = ".env.staging"   # relative to the main worktree
to = ".env"             # relative to the new worktree

[[symlink]]
from = ".bin"
to = ".bin"

[[command]]
run = "just bootstrap"
```

`copy`/`symlink` sources are relative to the main worktree; `command` runs inside the new
worktree.

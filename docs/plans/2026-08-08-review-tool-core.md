# Review Tool Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `review_tool.py` (renderer, daemon, state merge, manifest, install) and rewrite the review-branch skill to write structured `review.toml` findings that render to a collaborative HTML tracker served by a local daemon.

**Architecture:** A single self-contained uv-shebang Python script provides all deterministic behavior: XDG-rooted storage with an auto-committing git repo, TOML-to-HTML rendering with an embedded template, a localhost daemon whose routes are the filesystem, and a state-merge layer that reconciles Claude's `review.toml` with the browser's `state.json`. The skill prose only drives this CLI. Spec: `docs/spec/2026-08-08-review-branch-collab-design.md`.

**Tech Stack:** Python >= 3.12 (uv shebang single-file script), stdlib `tomllib`/`http.server`/`hashlib`/`subprocess`, `markdown-it-py` for markdown, pytest via `uv run` for tests.

## Global Constraints

- Scripts are single-file uv-shebang (`#!/usr/bin/env -S uv run --script`) with inline metadata blocks; `requires-python = ">=3.12"`.
- Dependency: `markdown-it-py` only. The spec lists `tomli-w` but the tool never writes TOML (Claude writes review.toml; the tool writes JSON and HTML), so it is omitted. This deviation is deliberate; flag it in the final report.
- Every code file starts with two `ABOUTME: ` comment lines.
- No emojis, no em-dashes, no hyperbole in any prose, docs, or template copy. Tables in HTML may use `&mdash;` for "none" (existing convention).
- Data root: `${REVIEW_BRANCH_HOME:-${XDG_DATA_HOME:-~/.local/share}/review-branch}`. State root (pidfile, log): `${XDG_STATE_HOME:-~/.local/state}/review-branch`. Bin dir for install: `${REVIEW_BRANCH_BIN:-~/.local/bin}`.
- Daemon: binds 127.0.0.1 only; default port 43117; override `REVIEW_BRANCH_PORT`.
- Data-root git commit messages: `<repo-id> <slug> round-N: <action>` (e.g. `omni-a3f2 mr-124 round-1: state update`, `... : f3 comment rev 2`).
- Severities: `high`, `med`, `low`, `info`. Dispositions: `"post"`, `"skip"`, `null` (undecided).
- Commit messages in this repo: short imperative, no conventional-commit prefixes (match `git log` style, e.g. "Add review-branch plugin"). End every commit with the Claude co-author trailer.
- Run tests with `just test` (added in Task 1). All tests must pass before every commit.
- The script must remain importable as a module (`import review_tool`) with all side effects behind `if __name__ == "__main__":`.

## File Structure

```
justfile                                          # Modify: add `test` recipe (Task 1)
plugins/review-branch/scripts/review_tool.py      # Create: the whole tool (Tasks 1-11)
tests/review_branch/conftest.py                   # Create: sys.path + fixtures (Tasks 1-2)
tests/review_branch/test_cli.py                   # Create (Task 1)
tests/review_branch/test_paths.py                 # Create (Task 2)
tests/review_branch/test_data_repo.py             # Create (Task 3)
tests/review_branch/test_init.py                  # Create (Task 4)
tests/review_branch/test_merge.py                 # Create (Task 5)
tests/review_branch/test_status_manifest.py       # Create (Task 6)
tests/review_branch/test_render_helpers.py        # Create (Task 7)
tests/review_branch/test_render.py                # Create (Task 8)
tests/review_branch/test_daemon.py                # Create (Task 9)
tests/review_branch/test_lifecycle.py             # Create (Task 10)
tests/review_branch/test_install.py               # Create (Task 11)
plugins/review-branch/skills/review-branch/references/data-format.md   # Create (Task 12)
plugins/review-branch/skills/review-branch/references/http-api.md      # Create (Task 12)
plugins/review-branch/skills/review-branch/references/diagrams.md      # Create (Task 12)
plugins/review-branch/skills/review-branch/SKILL.md                    # Rewrite (Task 13)
plugins/review-branch/skills/review-branch/references/html-template.md # Delete (Task 13)
plugins/review-branch/skills/review-branch/assets/template.html        # Delete (Task 13)
plugins/review-branch/.claude-plugin/plugin.json                       # Modify (Task 13)
plugins/review-branch/README.md                                        # Rewrite (Task 13)
```

`review_tool.py` internal layout (one file, ordered sections): header + constants, path helpers, git helpers, repo identity, data-repo helpers, load/merge, render helpers, template, render, daemon, lifecycle (open/stop/daemon), install, argparse `main`.

---

### Task 1: Test harness and CLI skeleton

**Files:**
- Create: `plugins/review-branch/scripts/review_tool.py`
- Create: `tests/review_branch/conftest.py`
- Create: `tests/review_branch/test_cli.py`
- Modify: `justfile` (append recipe at end of file)

**Interfaces:**
- Produces: `review_tool.main(argv: list[str] | None = None) -> int`; `review_tool.__version__: str` (starts at `"0.2.0"`); argparse subcommands registered but stubbed (each returns exit code 2 with "not implemented" on stderr until its task lands).

- [ ] **Step 1: Write the failing test**

`tests/review_branch/conftest.py`:

```python
# ABOUTME: pytest path setup and shared fixtures for review-branch script tests
# ABOUTME: makes plugins/review-branch/scripts importable and provides temp env/repos

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "review-branch" / "scripts"),
)
```

`tests/review_branch/test_cli.py`:

```python
# ABOUTME: tests for the review_tool CLI entry point
# ABOUTME: covers --version output and unknown-command handling

import pytest

import review_tool


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exc:
        review_tool.main(["--version"])
    assert exc.value.code == 0
    assert review_tool.__version__ in capsys.readouterr().out


def test_no_args_prints_usage_and_fails(capsys):
    assert review_tool.main([]) == 2
    assert "usage" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Add the `test` recipe and run the test to verify it fails**

Append to `justfile`:

```
# Run python script tests
test:
    uv run --python 3.12 --with pytest --with markdown-it-py pytest tests -q
```

Run: `just test`
Expected: FAIL with `ModuleNotFoundError: No module named 'review_tool'`

- [ ] **Step 3: Write the skeleton**

`plugins/review-branch/scripts/review_tool.py`:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["markdown-it-py"]
# ///

# ABOUTME: review-branch tool: renders review.toml to a collaborative HTML tracker,
# ABOUTME: runs the review daemon, merges browser state, emits posting manifests

import argparse
import sys

__version__ = "0.2.0"
APP_NAME = "review-branch"
DEFAULT_PORT = 43117

SUBCOMMANDS = ("init", "render", "open", "status", "manifest", "install", "daemon", "stop")


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
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

Then `chmod +x plugins/review-branch/scripts/review_tool.py`.

The skeleton registers exactly the eight subcommands in `SUBCOMMANDS`; `manifest` gains `--exclude` in Task 6 and `init` gains real behavior in Task 4.

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add justfile plugins/review-branch/scripts/review_tool.py tests/review_branch/
git commit -m "Add review_tool CLI skeleton and test harness"
```

---

### Task 2: Path helpers and repo identity

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py`
- Modify: `tests/review_branch/conftest.py`
- Create: `tests/review_branch/test_paths.py`

**Interfaces:**
- Produces: `data_root() -> Path`, `state_root() -> Path`, `git(cwd, *args, check=True) -> str`, `git_ok(cwd, *args) -> str | None`, `main_worktree(repo_dir: Path) -> Path`, `repo_id(repo_dir: Path) -> str` (format `<name>-<4 hex of sha256(origin url or main worktree abspath)>`).
- Consumes: nothing beyond Task 1.

- [ ] **Step 1: Add shared fixtures**

Append to `tests/review_branch/conftest.py`:

```python
import subprocess

import pytest


def run_git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def make_repo(path, origin=None):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    (path / "README.md").write_text("x\n")
    run_git(path, "add", "-A")
    run_git(path, "commit", "-q", "-m", "init")
    if origin:
        run_git(path, "remote", "add", "origin", origin)
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_BRANCH_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("REVIEW_BRANCH_BIN", str(tmp_path / "bin"))
    monkeypatch.delenv("REVIEW_BRANCH_PORT", raising=False)
    return tmp_path
```

- [ ] **Step 2: Write the failing tests**

`tests/review_branch/test_paths.py`:

```python
# ABOUTME: tests for data/state root resolution and repo identity hashing
# ABOUTME: covers env overrides, XDG fallbacks, remote vs path seeds, worktree resolution

from pathlib import Path

import review_tool
from conftest import make_repo, run_git


def test_data_root_honors_review_branch_home(env):
    assert review_tool.data_root() == env / "data"


def test_data_root_falls_back_to_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("REVIEW_BRANCH_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert review_tool.data_root() == tmp_path / "xdg" / "review-branch"


def test_state_root_uses_xdg_state_home(env):
    assert review_tool.state_root() == env / "state" / "review-branch"


def test_repo_id_uses_origin_url_and_repo_name(env):
    repo = make_repo(env / "myproj", origin="git@gitlab.example.com:g/myproj.git")
    rid = review_tool.repo_id(repo)
    assert rid.startswith("myproj-")
    assert len(rid) == len("myproj-") + 4


def test_repo_id_stable_across_worktrees(env):
    repo = make_repo(env / "myproj", origin="git@gitlab.example.com:g/myproj.git")
    run_git(repo, "worktree", "add", str(env / "wt"), "-b", "feature")
    assert review_tool.repo_id(env / "wt") == review_tool.repo_id(repo)


def test_repo_id_without_remote_uses_path(env):
    a = make_repo(env / "same")
    b = make_repo(env / "other")
    assert review_tool.repo_id(a) != review_tool.repo_id(b)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `just test`
Expected: FAIL with `AttributeError: module 'review_tool' has no attribute 'data_root'`

- [ ] **Step 4: Implement**

Add to `review_tool.py` (after the constants, before `main`):

```python
import hashlib
import os
import subprocess
from pathlib import Path


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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `just test`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py tests/review_branch/
git commit -m "Add path resolution and repo identity to review_tool"
```

---

### Task 3: Data-root git repo helpers

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py`
- Create: `tests/review_branch/test_data_repo.py`

**Interfaces:**
- Consumes: `data_root()` (Task 2).
- Produces: `ensure_data_repo() -> Path` (creates the data root and a git repo inside it, idempotent, sets local `user.name`/`user.email` so commits work everywhere), `data_commit(message: str) -> None` (stages everything, commits only if something changed, never raises on "nothing to commit").

- [ ] **Step 1: Write the failing tests**

`tests/review_branch/test_data_repo.py`:

```python
# ABOUTME: tests for the auto-committing git repo at the data root
# ABOUTME: covers creation, idempotency, commit messages, and empty-commit no-ops

import review_tool


def test_ensure_data_repo_creates_git_repo(env):
    root = review_tool.ensure_data_repo()
    assert (root / ".git").is_dir()


def test_ensure_data_repo_is_idempotent(env):
    review_tool.ensure_data_repo()
    review_tool.ensure_data_repo()  # must not raise or re-init


def test_data_commit_records_message(env):
    root = review_tool.ensure_data_repo()
    (root / "f.txt").write_text("hello\n")
    review_tool.data_commit("proj-abcd mr-1 round-1: state update")
    log = review_tool.git(root, "log", "--oneline")
    assert "proj-abcd mr-1 round-1: state update" in log


def test_data_commit_with_no_changes_is_noop(env):
    review_tool.ensure_data_repo()
    review_tool.data_commit("nothing changed")  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test`
Expected: FAIL with `AttributeError: ... 'ensure_data_repo'`

- [ ] **Step 3: Implement**

Add to `review_tool.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py tests/review_branch/test_data_repo.py
git commit -m "Add auto-committing data-root git repo helpers"
```

---

### Task 4: init subcommand

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py`
- Create: `tests/review_branch/test_init.py`

**Interfaces:**
- Consumes: `repo_id`, `data_root`, `ensure_data_repo` (Tasks 2-3).
- Produces: `cmd_init(slug: str, repo_dir: Path) -> Path` (creates `<data-root>/<repo-id>/<slug>/round-N` where N is one past the highest existing round, or 1); CLI `init --slug <slug>` prints the absolute round dir path to stdout and is wired into `main`.

- [ ] **Step 1: Write the failing tests**

`tests/review_branch/test_init.py`:

```python
# ABOUTME: tests for the init subcommand round-directory creation
# ABOUTME: covers first round, round increment, and CLI stdout contract

import review_tool
from conftest import make_repo


def test_init_creates_round_one(env):
    repo = make_repo(env / "proj", origin="https://gitlab.example.com/g/proj.git")
    d = review_tool.cmd_init("mr-124", repo)
    assert d.name == "round-1"
    assert d.parent.name == "mr-124"
    assert d.is_dir()
    assert d.parent.parent.parent == review_tool.data_root()


def test_init_increments_rounds(env):
    repo = make_repo(env / "proj", origin="https://gitlab.example.com/g/proj.git")
    review_tool.cmd_init("mr-124", repo)
    d2 = review_tool.cmd_init("mr-124", repo)
    assert d2.name == "round-2"


def test_init_cli_prints_path(env, capsys, monkeypatch):
    repo = make_repo(env / "proj", origin="https://gitlab.example.com/g/proj.git")
    monkeypatch.chdir(repo)
    assert review_tool.main(["init", "--slug", "mr-9"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("mr-9/round-1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test`
Expected: FAIL with `AttributeError: ... 'cmd_init'`

- [ ] **Step 3: Implement**

Add to `review_tool.py`, and wire the `init` branch in `main` (replace the generic "not implemented" fallthrough with a dispatch: `if args.command == "init": print(cmd_init(args.slug, Path.cwd())); return 0`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py tests/review_branch/test_init.py
git commit -m "Add init subcommand creating round directories"
```

---

### Task 5: Load and merge logic

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py`
- Create: `tests/review_branch/test_merge.py`

**Interfaces:**
- Consumes: nothing new (pure functions over files).
- Produces:
  - `load_review(round_dir: Path) -> dict` (parses review.toml via `tomllib`; raises `SystemExit` with the parse error and file path on bad TOML)
  - `load_state(round_dir: Path) -> dict` (returns `{"findings": {}}` when state.json is absent)
  - `merged_findings(review: dict, state: dict) -> list[dict]` where each merged finding carries every review.toml field plus: `disposition` (`"post"|"skip"|None`), `note`, `note_stale: bool`, `edited_comment`, `edited_stale: bool`, `postable_body` (edited comment when its rev matches `comment_rev`, else the draft `comment`), `posted: bool` (true when `posted_url` present).
  - Staleness rule (spec): state entries carry `note_rev` / `edited_comment_rev`; an entry is stale when its rev is lower than the finding's `comment_rev` (default 1).

- [ ] **Step 1: Write the failing tests**

`tests/review_branch/test_merge.py`:

```python
# ABOUTME: tests for review.toml/state.json loading and the merge/staleness rules
# ABOUTME: covers postable body selection, stale notes and edits, posted flags

import json

import pytest

import review_tool

REVIEW_TOML = """
[review]
title = "MR 124 review - refs"
vcs = "glab"
number = 124
url = "https://gitlab.example.com/g/p/-/merge_requests/124"
source_branch = "feat"
target_branch = "main"

[overall]
body = "Overall prose."

[[findings]]
id = "f1"
severity = "high"
title = "Bad validation"
file = "api.py"
lines = "10-20"
lenses = ["security"]
body = "Explanation."
comment = "Draft one."
comment_rev = 2
anchor = "api.py:20"

[[findings]]
id = "f2"
severity = "low"
title = "Naming nit"
file = "b.py"
lines = "5"
lenses = ["naming"]
body = "Nit."
comment = "Draft two."
posted_url = "https://gitlab.example.com/note/1"
posted_at = "2026-08-08T00:00:00Z"
"""


@pytest.fixture
def round_dir(tmp_path):
    d = tmp_path / "round-1"
    d.mkdir()
    (d / "review.toml").write_text(REVIEW_TOML)
    return d


def write_state(d, findings):
    (d / "state.json").write_text(json.dumps({"findings": findings}))


def test_missing_state_yields_defaults(round_dir):
    merged = review_tool.merged_findings(
        review_tool.load_review(round_dir), review_tool.load_state(round_dir)
    )
    f1 = merged[0]
    assert f1["disposition"] is None
    assert f1["postable_body"] == "Draft one."
    assert f1["posted"] is False
    assert merged[1]["posted"] is True


def test_current_edit_wins(round_dir):
    write_state(round_dir, {"f1": {"disposition": "post", "edited_comment": "Mine.", "edited_comment_rev": 2}})
    f1 = review_tool.merged_findings(
        review_tool.load_review(round_dir), review_tool.load_state(round_dir)
    )[0]
    assert f1["postable_body"] == "Mine."
    assert f1["edited_stale"] is False
    assert f1["disposition"] == "post"


def test_stale_edit_and_note_are_flagged_and_ignored(round_dir):
    write_state(
        round_dir,
        {"f1": {"note": "soften", "note_rev": 1, "edited_comment": "Old.", "edited_comment_rev": 1}},
    )
    f1 = review_tool.merged_findings(
        review_tool.load_review(round_dir), review_tool.load_state(round_dir)
    )[0]
    assert f1["postable_body"] == "Draft one."
    assert f1["edited_stale"] is True
    assert f1["note_stale"] is True
    assert f1["note"] == "soften"


def test_bad_toml_exits_with_path_in_message(tmp_path):
    d = tmp_path / "round-1"
    d.mkdir()
    (d / "review.toml").write_text("[review\n")
    with pytest.raises(SystemExit) as exc:
        review_tool.load_review(d)
    assert "review.toml" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test`
Expected: FAIL with `AttributeError: ... 'load_review'`

- [ ] **Step 3: Implement**

Add to `review_tool.py`:

```python
import json
import tomllib


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py tests/review_branch/test_merge.py
git commit -m "Add review/state loading and merge with staleness rules"
```

---

### Task 6: status and manifest subcommands

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py`
- Create: `tests/review_branch/test_status_manifest.py`

**Interfaces:**
- Consumes: `load_review`, `load_state`, `merged_findings` (Task 5).
- Produces:
  - `parse_anchor(finding: dict) -> tuple[str, int | None]` (splits `anchor` on the last `:`; falls back to `file` plus the last integer in `lines`; `(file, None)` when no line derivable)
  - `cmd_status(round_dir: Path) -> dict` returning `{"review": <[review] table>, "findings": <merged list>}`; CLI prints it as indented JSON
  - `cmd_manifest(round_dir: Path, exclude: set[str]) -> list[dict]` returning `[{"file": str, "line": int, "body": str}]` for findings with disposition `"post"`, `commentable` not false, not yet posted, id not excluded; CLI flag `--exclude f3,f7` (comma-separated); errors to stderr with exit 1 if a selected finding has no derivable line or empty body.

- [ ] **Step 1: Write the failing tests**

`tests/review_branch/test_status_manifest.py`:

```python
# ABOUTME: tests for the status and manifest subcommands
# ABOUTME: covers merged JSON output, post filtering, excludes, and anchor fallback

import json

import pytest

import review_tool

REVIEW_TOML = """
[review]
title = "MR 9"
vcs = "glab"
url = "https://gitlab.example.com/g/p/-/merge_requests/9"

[[findings]]
id = "f1"
severity = "high"
title = "A"
file = "a.py"
lines = "10-20"
body = "x"
comment = "Comment A."
anchor = "a.py:20"

[[findings]]
id = "f2"
severity = "med"
title = "B"
file = "b.py"
lines = "30-41"
body = "x"
comment = "Comment B."

[[findings]]
id = "f3"
severity = "info"
title = "C"
file = "c.py"
lines = "1"
body = "x"
commentable = false
"""


@pytest.fixture
def round_dir(tmp_path):
    d = tmp_path / "round-1"
    d.mkdir()
    (d / "review.toml").write_text(REVIEW_TOML)
    (d / "state.json").write_text(
        json.dumps(
            {
                "findings": {
                    "f1": {"disposition": "post"},
                    "f2": {"disposition": "post"},
                    "f3": {"disposition": "post"},
                }
            }
        )
    )
    return d


def test_status_shape(round_dir, capsys):
    assert review_tool.main(["status", str(round_dir)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["review"]["title"] == "MR 9"
    assert [f["id"] for f in data["findings"]] == ["f1", "f2", "f3"]
    assert data["findings"][0]["postable_body"] == "Comment A."


def test_manifest_filters_and_anchors(round_dir, capsys):
    assert review_tool.main(["manifest", str(round_dir)]) == 0
    entries = json.loads(capsys.readouterr().out)
    # f3 is commentable = false, so only f1 and f2; f2 anchor falls back to end of lines
    assert entries == [
        {"file": "a.py", "line": 20, "body": "Comment A."},
        {"file": "b.py", "line": 41, "body": "Comment B."},
    ]


def test_manifest_exclude(round_dir, capsys):
    assert review_tool.main(["manifest", str(round_dir), "--exclude", "f2"]) == 0
    entries = json.loads(capsys.readouterr().out)
    assert [e["file"] for e in entries] == ["a.py"]


def test_parse_anchor_fallbacks():
    assert review_tool.parse_anchor({"anchor": "x/y.py:12", "file": "z.py", "lines": "1"}) == ("x/y.py", 12)
    assert review_tool.parse_anchor({"file": "z.py", "lines": "5-9"}) == ("z.py", 9)
    assert review_tool.parse_anchor({"file": "z.py"}) == ("z.py", None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test`
Expected: FAIL (status returns 2 "not implemented")

- [ ] **Step 3: Implement**

Add to `review_tool.py`, and wire `status` and `manifest` into `main` (add `--exclude` with `default=""` to the manifest subparser; split on commas, ignore empties):

```python
import re


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
```

In `main`, the two branches:

```python
    if args.command == "status":
        print(json.dumps(cmd_status(Path(args.review_dir)), indent=2))
        return 0
    if args.command == "manifest":
        exclude = {x for x in args.exclude.split(",") if x}
        print(json.dumps(cmd_manifest(Path(args.review_dir), exclude), indent=2))
        return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py tests/review_branch/test_status_manifest.py
git commit -m "Add status and manifest subcommands"
```

---

### Task 7: Render helpers (markdown, escaping, diff links, version token)

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py`
- Create: `tests/review_branch/test_render_helpers.py`

**Interfaces:**
- Consumes: `load_review` (Task 5), `parse_anchor` (Task 6).
- Produces: `esc(s) -> str` (html.escape with quotes), `md_html(text: str) -> str` (markdown-it commonmark + tables), `diff_link(meta: dict, path: str, line: int | None) -> str | None` (glab: `<url>/diffs#diff-content-<sha1(path)>`; gh: `<url>/files#diff-<sha256(path)>R<line>`; None when no url), `version_token(round_dir: Path) -> str` (16-hex digest over name/mtime/size of review.toml, state.json, and each asset file), `route_for(round_dir: Path) -> str` (`<repo-id>/<slug>/round-N`, SystemExit if the dir is not exactly three levels under the data root).

- [ ] **Step 1: Write the failing tests**

`tests/review_branch/test_render_helpers.py`:

```python
# ABOUTME: tests for markdown, escaping, diff-link, version-token, and route helpers
# ABOUTME: covers glab/gh anchor formats, local mode, token change on write, route validation

import hashlib

import pytest

import review_tool


def test_md_html_renders_inline_code():
    assert "<code>x</code>" in review_tool.md_html("has `x` in it")


def test_esc_escapes_angle_brackets_and_quotes():
    assert review_tool.esc('<a href="x">') == "&lt;a href=&quot;x&quot;&gt;"


def test_diff_link_glab():
    meta = {"vcs": "glab", "url": "https://gitlab.example.com/g/p/-/merge_requests/9"}
    link = review_tool.diff_link(meta, "runner/api.py", 121)
    sha = hashlib.sha1(b"runner/api.py").hexdigest()
    assert link == f"{meta['url']}/diffs#diff-content-{sha}"


def test_diff_link_gh_includes_right_line():
    meta = {"vcs": "gh", "url": "https://github.com/o/r/pull/42"}
    link = review_tool.diff_link(meta, "runner/api.py", 121)
    sha = hashlib.sha256(b"runner/api.py").hexdigest()
    assert link == f"{meta['url']}/files#diff-{sha}R121"


def test_diff_link_local_is_none():
    assert review_tool.diff_link({"vcs": "local"}, "a.py", 1) is None


def test_version_token_changes_on_state_write(tmp_path):
    d = tmp_path / "round-1"
    d.mkdir()
    (d / "review.toml").write_text('[review]\ntitle = "t"\n')
    t1 = review_tool.version_token(d)
    (d / "state.json").write_text('{"findings": {}}')
    assert review_tool.version_token(d) != t1


def test_route_for_requires_data_root(env, tmp_path):
    d = review_tool.data_root() / "proj-abcd" / "mr-1" / "round-1"
    d.mkdir(parents=True)
    assert review_tool.route_for(d) == "proj-abcd/mr-1/round-1"
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(SystemExit):
        review_tool.route_for(outside)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test`
Expected: FAIL with `AttributeError: ... 'md_html'`

- [ ] **Step 3: Implement**

Add to `review_tool.py`:

```python
import html

from markdown_it import MarkdownIt

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py tests/review_branch/test_render_helpers.py
git commit -m "Add render helpers: markdown, diff links, version token, routes"
```

---

### Task 8: Embedded template and the render subcommand

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py`
- Create: `tests/review_branch/test_render.py`

**Interfaces:**
- Consumes: everything from Tasks 5-7 plus `data_commit` (Task 3).
- Produces: `render_html(round_dir: Path, served: bool) -> str`; `cmd_render(round_dir: Path) -> Path` (writes `review.html` with `served=False`, commits `<rid> <slug> round-N: render`); CLI `render <review_dir>` prints the written path. Also `finding_card`, `meta_row`, `summary_cards`, `assets_html`, `table_html` (internal composition helpers), and the `TEMPLATE` string with tokens `<!--TITLE-->`, `<!--SUBTITLE-->`, `<!--META-->`, `<!--SUMMARY-->`, `<!--CONTENT-->`, `<!--BAKED-->`.
- Behavior contracts the daemon (Task 9) and page rely on:
  - Served pages get `served: true` baked in; `cmd_render` bakes `served: false` so a `file://` open is read-only.
  - Card DOM: `.finding[data-fid][data-rev]`; comment textarea `.comment` (initial content = postable body, so `defaultValue` detects edits); note textarea `.note` (initial content = current non-stale note); radios `name="dispo-<fid>"` values `post`/`skip`/`""`; stale note rendered as `.applied` div; posted findings render frozen with a `posted` badge linking `posted_url` and show `posted_body`.
  - JS saves whole-document state to relative `api/state` (works because round routes always end in `/`), carries unknown prior state entries forward untouched, debounces 2s, retries every 5s on failure with a banner and a copy-state link, polls `api/version` every 2s and reloads only when clean, warns on unload when dirty.

- [ ] **Step 1: Write the failing tests**

`tests/review_branch/test_render.py`:

```python
# ABOUTME: tests for render_html composition and the render subcommand
# ABOUTME: covers cards, escaping, diff links, asset inlining, baked state, git commit

import json

import pytest

import review_tool

REVIEW_TOML = """
[review]
title = "MR 124 review - <refs>"
vcs = "glab"
number = 124
url = "https://gitlab.example.com/g/p/-/merge_requests/124"
source_branch = "feat"
target_branch = "main"
commits = 4
files = "20 (+1752 / -43)"

[overall]
body = "Overall with `code`."

[[assets]]
type = "svg"
path = "diagram.svg"
caption = "Flow"

[[findings]]
id = "f1"
severity = "high"
title = "Bad <validation>"
file = "api.py"
lines = "10-20"
lenses = ["security"]
body = "Explanation."
snippet = "if x < 1: pass"
fix = "Clamp it."
comment = "Draft one."
anchor = "api.py:20"

[[findings]]
id = "f2"
severity = "info"
title = "Context only"
file = "b.py"
body = "FYI."
commentable = false

[[coverage]]
surface = "API 422"
covered = ""
gap = "f1"
"""


@pytest.fixture
def round_dir(env):
    d = review_tool.data_root() / "proj-abcd" / "mr-124" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(REVIEW_TOML)
    (d / "diagram.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><title>seq</title></svg>')
    (d / "state.json").write_text(json.dumps({"findings": {"f1": {"disposition": "post"}}}))
    return d


def test_render_html_composition(round_dir):
    page = review_tool.render_html(round_dir, served=True)
    assert "MR 124 review - &lt;refs&gt;" in page          # escaped title
    assert 'data-fid="f1"' in page and 'data-rev="1"' in page
    assert "diffs#diff-content-" in page                    # diff link
    assert "<title>seq</title>" in page                     # svg inlined
    assert "if x &lt; 1: pass" in page                      # snippet escaped
    assert 'name="dispo-f1"' in page and "checked" in page  # disposition radio state
    assert '"served": true' in page
    assert "API 422" in page                                # coverage table


def test_f2_has_no_comment_area(round_dir):
    page = review_tool.render_html(round_dir, served=True)
    # slice from f2's card to the next h2 (the coverage table heading)
    f2_chunk = page.split('data-fid="f2"')[1].split("<h2>")[0]
    assert "textarea" not in f2_chunk


def test_cmd_render_writes_file_and_commits(round_dir, capsys):
    assert review_tool.main(["render", str(round_dir)]) == 0
    out_path = round_dir / "review.html"
    assert out_path.exists()
    page = out_path.read_text()
    assert '"served": false' in page
    log = review_tool.git(review_tool.data_root(), "log", "--oneline")
    assert "proj-abcd mr-124 round-1: render" in log
    assert str(out_path) in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test`
Expected: FAIL with `AttributeError: ... 'render_html'`

- [ ] **Step 3: Implement the composition helpers**

Add to `review_tool.py`:

```python
def meta_row(meta: dict) -> str:
    spans = []
    label = {"glab": "MR", "gh": "PR"}.get(meta.get("vcs"))
    if label and meta.get("url") and meta.get("number"):
        mark = "!" if label == "MR" else "#"
        spans.append(
            f'<span><strong>{label}:</strong> <a href="{esc(meta["url"])}">{mark}{meta["number"]}</a></span>'
        )
    if meta.get("source_branch"):
        arrow = f'{esc(meta["source_branch"])} -&gt; {esc(meta.get("target_branch", ""))}'
        spans.append(f"<span><strong>Branch:</strong> {arrow}</span>")
    for key, name in (("commits", "Commits"), ("files", "Files"), ("spec", "Spec")):
        if meta.get(key):
            spans.append(f"<span><strong>{name}:</strong> {esc(meta[key])}</span>")
    return "\n".join(spans)


def summary_cards(findings: list[dict]) -> str:
    counts = {"high": 0, "med": 0, "low": 0, "info": 0}
    for f in findings:
        counts[f.get("severity", "info")] += 1
    cards = []
    for sev, name in (("high", "High"), ("med", "Medium"), ("low", "Low / nits"), ("info", "Out-of-scope flags")):
        if counts[sev] or sev in ("high", "med"):
            cards.append(
                f'<div class="card"><div class="num {sev}">{counts[sev]}</div><div class="label">{name}</div></div>'
            )
    return "\n".join(cards)


def assets_html(round_dir: Path, review: dict) -> str:
    parts = []
    for a in review.get("assets", []):
        p = round_dir / a["path"]
        try:
            content = p.read_text()
        except OSError as e:
            raise SystemExit(f"asset {p}: {e}")
        if a.get("type") == "svg":
            content = re.sub(r"^\s*<\?xml[^>]*\?>", "", content)
        cap = f"<figcaption>{esc(a['caption'])}</figcaption>" if a.get("caption") else ""
        parts.append(f'<figure class="asset">{content}{cap}</figure>')
    return "\n".join(parts)


def table_html(title: str, headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<h2>{esc(title)}</h2>\n<table>\n<tr>{head}</tr>\n{body}\n</table>"


def _dash(value) -> str:
    return esc(value) if value else "&mdash;"


def finding_card(f: dict, meta: dict) -> str:
    sev = f.get("severity", "info")
    fid = f["id"]
    _, line = parse_anchor(f)
    fileref = f'{f["file"]}:{f["lines"]}' if f.get("lines") else f["file"]
    link = diff_link(meta, f["file"], line)
    file_html = f'<a href="{esc(link)}">{esc(fileref)}</a>' if link else esc(fileref)
    head = [
        f'<span class="num">{esc(fid)}</span>',
        f'<span class="title">{esc(f.get("title", ""))}</span>',
        f'<span class="badge {sev}">{sev}</span>',
    ]
    head += [f'<span class="tag">{esc(lens)}</span>' for lens in f.get("lenses", [])]
    if f["posted"]:
        head.append(f'<a class="badge posted" href="{esc(f.get("posted_url", ""))}">posted</a>')
    parts = [
        f'<div class="finding {sev}" data-fid="{esc(fid)}" data-rev="{f.get("comment_rev", 1)}">',
        f'<div class="head">{" ".join(head)}</div>',
        f'<div class="file">{file_html}</div>',
        md_html(f.get("body", "")),
    ]
    if f.get("snippet"):
        parts.append(f"<pre><code>{esc(f['snippet'])}</code></pre>")
    if f.get("fix"):
        parts.append(f"<p><strong>Suggested fix:</strong> {esc(f['fix'])}</p>")
    if f["posted"]:
        parts.append(f"<pre><code>{esc(f.get('posted_body', ''))}</code></pre>")
    elif f.get("commentable", True):
        area = ['<div class="comment-area">']
        if f["note_stale"]:
            area.append(f'<div class="applied">applied: {esc(f["note"])}</div>')
        area.append('<label class="small">Comment draft</label>')
        area.append(f'<textarea class="comment">{esc(f["postable_body"] or "")}</textarea>')
        area.append('<label class="small">Note to Claude</label>')
        note_now = "" if f["note_stale"] else (f.get("note") or "")
        area.append(
            f'<textarea class="note" placeholder="tell Claude how to adjust this">{esc(note_now)}</textarea>'
        )
        dispo = f["disposition"] or ""
        area.append('<div class="dispo">')
        for value, name in (("post", "Post"), ("skip", "Skip"), ("", "Undecided")):
            checked = " checked" if dispo == value else ""
            area.append(
                f'<label><input type="radio" name="dispo-{esc(fid)}" value="{value}"{checked}> {name}</label>'
            )
        area.append("</div></div>")
        parts.append("\n".join(area))
    parts.append("</div>")
    return "\n".join(parts)
```

- [ ] **Step 4: Implement `render_html`, `cmd_render`, and the template**

Add to `review_tool.py`:

```python
def render_html(round_dir: Path, served: bool) -> str:
    review = load_review(round_dir)
    state = load_state(round_dir)
    meta = review.get("review", {})
    findings = merged_findings(review, state)
    content = [assets_html(round_dir, review)]
    if review.get("overall", {}).get("body"):
        content.append("<h2>Overall</h2>\n" + md_html(review["overall"]["body"]))
    content.append("<h2>Findings</h2>")
    content += [finding_card(f, meta) for f in findings]
    content.append(
        table_html(
            "Hexagonal architecture compliance",
            ["Boundary", "Change", "Status"],
            [[esc(r.get("boundary", "")), esc(r.get("change", "")), esc(r.get("status", ""))] for r in review.get("hex", [])],
        )
    )
    content.append(
        table_html(
            "What the tests do and don't cover",
            ["Surface", "Covered", "Gap"],
            [[esc(r.get("surface", "")), _dash(r.get("covered")), _dash(r.get("gap"))] for r in review.get("coverage", [])],
        )
    )
    content.append(
        table_html(
            "Files touched",
            ["File", "+/-", "Notes"],
            [[f"<code>{esc(r.get('path', ''))}</code>", esc(r.get("delta", "")), esc(r.get("notes", ""))] for r in review.get("files_touched", [])],
        )
    )
    baked = json.dumps(
        {"served": served, "route": route_for(round_dir), "token": version_token(round_dir), "state": state}
    ).replace("</", "<\\/")
    subtitle = "Collaborative review tracker. Mark dispositions, edit drafts, leave notes for Claude."
    return (
        TEMPLATE
        .replace("<!--TITLE-->", esc(meta.get("title", "review")))
        .replace("<!--SUBTITLE-->", subtitle)
        .replace("<!--META-->", meta_row(meta))
        .replace("<!--SUMMARY-->", summary_cards(findings))
        .replace("<!--CONTENT-->", "\n".join(part for part in content if part))
        .replace("<!--BAKED-->", baked)
    )


def cmd_render(round_dir: Path) -> Path:
    out = round_dir / "review.html"
    out.write_text(render_html(round_dir, served=False))
    rid, slug, rnd = route_for(round_dir).split("/")
    data_commit(f"{rid} {slug} {rnd}: render")
    return out
```

Wire into `main`:

```python
    if args.command == "render":
        print(cmd_render(Path(args.review_dir)))
        return 0
```

The template (module-level constant; CSS palette carried over from the retired `assets/template.html`, structural additions for the comment area, banner, and progress line):

```python
TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title><!--TITLE--></title>
<style>
  :root {
    --bg: #0f1115; --panel: #161922; --panel2: #1c2030; --border: #2a3042;
    --text: #e6e8ee; --muted: #9aa3b2; --accent: #7aa2f7;
    --red: #f7768e; --amber: #e0af68; --green: #9ece6a; --blue: #7dcfff;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 32px 24px 80px; }
  h1 { margin: 0 0 4px; font-size: 22px; }
  h2 { margin: 32px 0 10px; font-size: 17px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
  .sub { color: var(--muted); font-size: 13px; margin-bottom: 24px; }
  .meta { display: flex; gap: 16px; flex-wrap: wrap; color: var(--muted); font-size: 12px; margin: 6px 0 22px; }
  .meta strong { color: var(--text); font-weight: 500; }
  a { color: var(--accent); }
  code, pre { font-family: var(--mono); font-size: 12.5px; }
  pre { background: var(--panel2); border: 1px solid var(--border); border-radius: 6px;
        padding: 12px; overflow-x: auto; margin: 8px 0; }
  code { background: var(--panel2); padding: 1px 5px; border-radius: 3px; }
  pre code { background: transparent; padding: 0; }
  figure.asset { margin: 20px 0; background: var(--panel); border: 1px solid var(--border);
                 border-radius: 6px; padding: 16px; overflow-x: auto; }
  figure.asset figcaption { color: var(--muted); font-size: 12px; margin-top: 8px; }
  .finding { background: var(--panel); border: 1px solid var(--border);
             border-left: 4px solid var(--muted); border-radius: 6px; padding: 14px 16px; margin: 14px 0; }
  .finding.high { border-left-color: var(--red); }
  .finding.med  { border-left-color: var(--amber); }
  .finding.low  { border-left-color: var(--blue); }
  .finding.info { border-left-color: var(--green); }
  .finding .head { display: flex; gap: 10px; align-items: baseline; margin-bottom: 4px; flex-wrap: wrap; }
  .finding .num { color: var(--muted); font-family: var(--mono); font-size: 12px; min-width: 28px; }
  .finding .title { font-weight: 600; font-size: 14.5px; }
  .badge { font-family: var(--mono); font-size: 10.5px; padding: 1px 7px; border-radius: 10px;
           text-transform: uppercase; letter-spacing: .04em; }
  .badge.high { background: rgba(247,118,142,.15); color: var(--red); }
  .badge.med  { background: rgba(224,175,104,.15); color: var(--amber); }
  .badge.low  { background: rgba(125,207,255,.15); color: var(--blue); }
  .badge.info { background: rgba(158,206,106,.15); color: var(--green); }
  .badge.posted { background: rgba(158,206,106,.15); color: var(--green); text-decoration: none; }
  .file { color: var(--muted); font-family: var(--mono); font-size: 12px; }
  .small { color: var(--muted); font-size: 12.5px; display: block; margin-top: 10px; }
  .tag { display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 4px;
         background: var(--panel2); border: 1px solid var(--border); color: var(--muted); }
  table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; }
  th, td { text-align: left; border-bottom: 1px solid var(--border); padding: 8px 10px;
           vertical-align: top; font-size: 13px; }
  th { color: var(--muted); font-weight: 500; }
  .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                  gap: 10px; margin: 12px 0 20px; }
  .summary-grid .card { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 12px; }
  .summary-grid .num { font-size: 22px; font-weight: 600; }
  .summary-grid .label { color: var(--muted); font-size: 12px; }
  .num.high { color: var(--red); } .num.med { color: var(--amber); }
  .num.low { color: var(--blue); } .num.info { color: var(--green); }
  .comment-area { margin-top: 12px; border-top: 1px solid var(--border); padding-top: 4px; }
  textarea { width: 100%; min-height: 72px; margin-top: 4px; background: var(--panel2);
             color: var(--text); border: 1px solid var(--border); border-radius: 6px;
             padding: 8px; font: 12.5px/1.5 var(--mono); resize: vertical; }
  textarea.note { min-height: 40px; font-family: inherit; }
  textarea:disabled, input:disabled { opacity: .5; }
  .applied { color: var(--muted); font-size: 12px; font-style: italic; margin-top: 8px; }
  .dispo { display: flex; gap: 16px; margin-top: 8px; color: var(--muted); font-size: 13px; }
  .dispo label { cursor: pointer; }
  .controls { display: flex; gap: 10px; align-items: center; margin: 8px 0 18px;
              font-size: 12px; color: var(--muted); }
  .progress { font-family: var(--mono); }
  #banner { display: none; position: sticky; top: 0; background: rgba(224,175,104,.12);
            border: 1px solid var(--amber); color: var(--amber); border-radius: 6px;
            padding: 8px 12px; margin: 0 0 16px; font-size: 12.5px; }
  #banner.show { display: block; }
  #banner a { color: var(--amber); margin-left: 10px; }
</style>
</head>
<body>
<div class="wrap">
<div id="banner"><span id="banner-msg"></span><a href="#" id="banner-copy" hidden>copy unsaved state</a></div>
<h1><!--TITLE--></h1>
<div class="sub"><!--SUBTITLE--></div>
<div class="meta"><!--META--></div>
<div class="summary-grid"><!--SUMMARY--></div>
<div class="controls"><span class="progress" id="progress"></span></div>
<!--CONTENT-->
</div>
<script>window.BAKED = <!--BAKED-->;</script>
<script>
(function () {
  var baked = window.BAKED;
  var state = (baked.state && baked.state.findings) ? baked.state : { findings: {} };
  var token = baked.token;
  var served = baked.served && location.protocol !== "file:";
  var dirty = 0;
  var saveTimer = null;
  var banner = document.getElementById("banner");
  var bannerMsg = document.getElementById("banner-msg");
  var bannerCopy = document.getElementById("banner-copy");
  var progress = document.getElementById("progress");
  var cards = Array.prototype.slice.call(document.querySelectorAll(".finding[data-fid]"));

  function showBanner(msg, withCopy) {
    bannerMsg.textContent = msg;
    bannerCopy.hidden = !withCopy;
    banner.classList.add("show");
  }
  function hideBanner() { banner.classList.remove("show"); }

  function updateProgress() {
    var counts = { post: 0, skip: 0, undecided: 0 };
    cards.forEach(function (card) {
      if (!card.querySelector(".dispo")) return;
      var checked = card.querySelector("input[type=radio]:checked");
      counts[checked && checked.value ? checked.value : "undecided"] += 1;
    });
    progress.textContent = counts.post + " post, " + counts.skip + " skip, " + counts.undecided + " undecided";
  }

  function collect() {
    cards.forEach(function (card) {
      if (!card.querySelector(".dispo")) return;
      var fid = card.dataset.fid;
      var crev = parseInt(card.dataset.rev, 10) || 1;
      var entry = state.findings[fid] || (state.findings[fid] = {});
      var checked = card.querySelector("input[type=radio]:checked");
      entry.disposition = checked && checked.value ? checked.value : null;
      var comment = card.querySelector("textarea.comment");
      if (comment.value !== comment.defaultValue) {
        entry.edited_comment = comment.value;
        entry.edited_comment_rev = crev;
      }
      var note = card.querySelector("textarea.note");
      if (note.value && note.value !== note.defaultValue) {
        entry.note = note.value;
        entry.note_rev = crev;
      } else if (!note.value && note.defaultValue) {
        delete entry.note;
        delete entry.note_rev;
      }
    });
    return state;
  }

  function save() {
    saveTimer = null;
    fetch("api/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collect())
    }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (resp) {
      dirty = 0;
      token = resp.token;
      hideBanner();
    }).catch(function () {
      showBanner("server unreachable - " + dirty + " unsaved change(s) held in this tab. restart with: review-branch open <review-dir>", true);
      saveTimer = setTimeout(save, 5000);
    });
  }

  function schedule() {
    dirty += 1;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 2000);
    updateProgress();
  }

  updateProgress();

  if (!served) {
    document.querySelectorAll("textarea, input").forEach(function (el) { el.disabled = true; });
    showBanner("read-only snapshot - run: review-branch open <review-dir> to edit", false);
    return;
  }

  cards.forEach(function (card) {
    card.querySelectorAll("input[type=radio]").forEach(function (el) { el.addEventListener("change", schedule); });
    card.querySelectorAll("textarea").forEach(function (el) { el.addEventListener("input", schedule); });
  });

  setInterval(function () {
    fetch("api/version").then(function (r) { return r.json(); }).then(function (resp) {
      if (resp.token !== token && !dirty && !saveTimer) location.reload();
    }).catch(function () {});
  }, 2000);

  window.addEventListener("beforeunload", function (e) {
    if (dirty || saveTimer) { e.preventDefault(); e.returnValue = ""; }
  });

  bannerCopy.addEventListener("click", function (e) {
    e.preventDefault();
    navigator.clipboard.writeText(JSON.stringify(collect()));
  });
})();
</script>
</body>
</html>
"""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `just test`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py tests/review_branch/test_render.py
git commit -m "Add embedded template and render subcommand"
```

---

### Task 9: Daemon

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py`
- Create: `tests/review_branch/test_daemon.py`

**Interfaces:**
- Consumes: `render_html`, `version_token`, `load_state`, `merged_findings`, `data_commit` (Tasks 3-8).
- Produces: `make_server(port: int, root: Path | None = None) -> ThreadingHTTPServer` (binds 127.0.0.1; `port=0` picks a free port for tests; handler class attribute `root` defaults to `data_root()`), `ReviewHandler`, `index_html(root: Path) -> str`, `INDEX_TEMPLATE`.
- HTTP contract (also documented in Task 12's http-api.md):
  - `GET /api/health` -> `{"app": "review-branch", "version": ..., "data_root": ...}`
  - `GET /` -> index page listing every `*/*/round-*/review.toml`, newest activity first
  - `GET /<rid>/<slug>/round-N/` -> in-memory `render_html(d, served=True)`; without trailing slash -> 301 to the slash form
  - `GET .../api/state` -> state.json content; `GET .../api/version` -> `{"token": ...}`
  - `POST .../api/state` -> validates `{"findings": {...}}`, stamps `updated_at` (UTC ISO), writes state.json, refreshes the on-disk review.html snapshot (`served=False`), commits `<rid> <slug> round-N: state update`, returns `{"ok": true, "token": <new>}`
  - `POST /api/shutdown` -> stops the server (used by the Task 10 version handshake)
  - Unknown or out-of-root routes -> 404 JSON `{"error": "unknown review route"}`; bad JSON -> 400

- [ ] **Step 1: Write the failing tests**

`tests/review_branch/test_daemon.py`:

```python
# ABOUTME: daemon smoke tests over a real ThreadingHTTPServer on an ephemeral port
# ABOUTME: covers health, index, page serving, state round-trip, version token, 404s

import http.client
import json
import threading

import pytest

import review_tool

REVIEW_TOML = """
[review]
title = "MR 7 review"
vcs = "glab"
number = 7
url = "https://gitlab.example.com/g/p/-/merge_requests/7"

[[findings]]
id = "f1"
severity = "med"
title = "T"
file = "a.py"
lines = "3"
body = "x"
comment = "Draft."
"""


@pytest.fixture
def served(env):
    d = review_tool.data_root() / "proj-abcd" / "mr-7" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(REVIEW_TOML)
    srv = review_tool.make_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv.server_address[1], d
    srv.shutdown()


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/json"} if body else {}
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    return resp.status, data


def test_health(served):
    port, _ = served
    status, data = request(port, "GET", "/api/health")
    assert status == 200
    payload = json.loads(data)
    assert payload["app"] == "review-branch"
    assert payload["version"] == review_tool.__version__


def test_index_lists_review(served):
    port, _ = served
    status, data = request(port, "GET", "/")
    assert status == 200
    assert "MR 7 review" in data
    assert "/proj-abcd/mr-7/round-1/" in data


def test_review_page_served_true(served):
    port, _ = served
    status, data = request(port, "GET", "/proj-abcd/mr-7/round-1/")
    assert status == 200
    assert '"served": true' in data


def test_no_trailing_slash_redirects(served):
    port, _ = served
    status, _ = request(port, "GET", "/proj-abcd/mr-7/round-1")
    assert status == 301


def test_unknown_route_404(served):
    port, _ = served
    status, _ = request(port, "GET", "/nope/mr-1/round-1/")
    assert status == 404


def test_state_roundtrip_writes_commits_and_tokens(served):
    port, d = served
    _, before = request(port, "GET", "/proj-abcd/mr-7/round-1/api/version")
    body = json.dumps({"findings": {"f1": {"disposition": "post"}}})
    status, data = request(port, "POST", "/proj-abcd/mr-7/round-1/api/state", body)
    assert status == 200
    resp = json.loads(data)
    assert resp["ok"] is True
    saved = json.loads((d / "state.json").read_text())
    assert saved["findings"]["f1"]["disposition"] == "post"
    assert "updated_at" in saved
    assert (d / "review.html").exists()
    log = review_tool.git(review_tool.data_root(), "log", "--oneline")
    assert "proj-abcd mr-7 round-1: state update" in log
    _, after = request(port, "GET", "/proj-abcd/mr-7/round-1/api/version")
    assert json.loads(after)["token"] != json.loads(before)["token"]


def test_bad_json_400(served):
    port, _ = served
    status, _ = request(port, "POST", "/proj-abcd/mr-7/round-1/api/state", "{nope")
    assert status == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test`
Expected: FAIL with `AttributeError: ... 'make_server'`

- [ ] **Step 3: Implement**

Add to `review_tool.py`:

```python
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>review-branch</title>
<style>
  body { margin: 0; background: #0f1115; color: #e6e8ee;
         font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 32px 24px; }
  a { color: #7aa2f7; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; border-bottom: 1px solid #2a3042; padding: 8px 10px; font-size: 13px; }
  th { color: #9aa3b2; font-weight: 500; }
</style>
</head>
<body><div class="wrap">
<h1>Reviews</h1>
<table><tr><th>Review</th><th>Repo</th><th>Findings</th><th>Progress</th></tr>
<!--ROWS-->
</table>
</div></body></html>
"""


def index_html(root: Path) -> str:
    rows = []
    tomls = sorted(
        root.glob("*/*/round-*/review.toml"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for toml_path in tomls:
        d = toml_path.parent
        try:
            review = tomllib.loads(toml_path.read_text())
        except tomllib.TOMLDecodeError:
            continue
        findings = merged_findings(review, load_state(d))
        counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "info")
            counts[sev] = counts.get(sev, 0) + 1
        sev_text = " ".join(f"{k}:{counts[k]}" for k in ("high", "med", "low", "info") if k in counts)
        decided = sum(1 for f in findings if f["disposition"])
        posted = sum(1 for f in findings if f["posted"])
        route = "/".join(d.relative_to(root).parts)
        title = review.get("review", {}).get("title", route)
        rows.append(
            f'<tr><td><a href="/{route}/">{esc(title)}</a></td><td>{esc(d.relative_to(root).parts[0])}</td>'
            f"<td>{esc(sev_text)}</td><td>{decided} decided, {posted} posted</td></tr>"
        )
    return INDEX_TEMPLATE.replace("<!--ROWS-->", "\n".join(rows) or '<tr><td colspan="4">no reviews yet</td></tr>')


class ReviewHandler(BaseHTTPRequestHandler):
    root: Path

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8"):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj), "application/json")

    def _round_dir(self, parts: list[str]) -> Path | None:
        if len(parts) != 3:
            return None
        d = (self.root / parts[0] / parts[1] / parts[2]).resolve()
        if not d.is_relative_to(self.root.resolve()):
            return None
        return d if (d / "review.toml").exists() else None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self._json(200, {"app": APP_NAME, "version": __version__, "data_root": str(self.root)})
        if path == "/":
            return self._send(200, index_html(self.root))
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[-2] == "api":
            d = self._round_dir(parts[:-2])
            if d is None:
                return self._json(404, {"error": "unknown review route"})
            if parts[-1] == "state":
                return self._json(200, load_state(d))
            if parts[-1] == "version":
                return self._json(200, {"token": version_token(d)})
            return self._json(404, {"error": "unknown api endpoint"})
        d = self._round_dir(parts)
        if d is None:
            return self._json(404, {"error": "unknown review route"})
        if not path.endswith("/"):
            self.send_response(301)
            self.send_header("Location", path + "/")
            self.end_headers()
            return
        return self._send(200, render_html(d, served=True))

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/shutdown":
            threading.Thread(target=self.server.shutdown).start()
            return self._json(200, {"ok": True})
        parts = [p for p in path.split("/") if p]
        if len(parts) != 5 or parts[3:] != ["api", "state"]:
            return self._json(404, {"error": "unknown endpoint"})
        d = self._round_dir(parts[:3])
        if d is None:
            return self._json(404, {"error": "unknown review route"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})
        if not isinstance(payload, dict) or not isinstance(payload.get("findings"), dict):
            return self._json(400, {"error": 'expected {"findings": {...}}'})
        payload["updated_at"] = datetime.now(UTC).isoformat()
        (d / "state.json").write_text(json.dumps(payload, indent=2) + "\n")
        (d / "review.html").write_text(render_html(d, served=False))
        data_commit(f"{parts[0]} {parts[1]} {parts[2]}: state update")
        return self._json(200, {"ok": True, "token": version_token(d)})


def make_server(port: int, root: Path | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (ReviewHandler,), {"root": root or data_root()})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py tests/review_branch/test_daemon.py
git commit -m "Add review daemon with filesystem routes and index page"
```

---

### Task 10: Lifecycle: open, daemon, stop

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py`
- Create: `tests/review_branch/test_lifecycle.py`

**Interfaces:**
- Consumes: `make_server` (Task 9), `route_for` (Task 7), `state_root` (Task 2).
- Produces: `current_port() -> int` (`REVIEW_BRANCH_PORT` or 43117), `health_check(port) -> dict | None` (1s timeout, None on any failure), `daemon_action(health: dict | None) -> str` returning `"start" | "squatter" | "restart" | "use"`, `spawn_daemon(port)` (detached via `start_new_session=True`, re-invokes this file with `sys.executable`, logs to `<state-root>/daemon.log`), `cmd_open(round_dir) -> str` (returns the review URL, starting/restarting the daemon as needed), `cmd_daemon() -> int` (foreground serve with pidfile), `cmd_stop() -> int` (SIGTERM via pidfile, tolerates stale/missing). All wired into `main`; `open` prints the URL.

- [ ] **Step 1: Write the failing tests**

`tests/review_branch/test_lifecycle.py`:

```python
# ABOUTME: tests for daemon lifecycle: action decisions, open against a live server, stop
# ABOUTME: uses an in-thread server for open and a throwaway child process for stop

import subprocess
import sys
import threading

import review_tool

REVIEW_TOML = '[review]\ntitle = "t"\nvcs = "local"\n'


def test_daemon_action_decisions():
    assert review_tool.daemon_action(None) == "start"
    assert review_tool.daemon_action({"app": "something-else"}) == "squatter"
    assert review_tool.daemon_action({"app": "review-branch", "version": "0.0.1"}) == "restart"
    assert review_tool.daemon_action({"app": "review-branch", "version": review_tool.__version__}) == "use"
    assert review_tool.daemon_action({"app": "review-branch", "version": "99.0.0"}) == "use"


def test_open_uses_running_daemon(env, monkeypatch, capsys):
    d = review_tool.data_root() / "proj-abcd" / "mr-3" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(REVIEW_TOML)
    srv = review_tool.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    monkeypatch.setenv("REVIEW_BRANCH_PORT", str(port))
    try:
        assert review_tool.main(["open", str(d)]) == 0
        out = capsys.readouterr().out.strip()
        assert out == f"http://127.0.0.1:{port}/proj-abcd/mr-3/round-1/"
    finally:
        srv.shutdown()


def test_stop_kills_pidfile_process(env):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    review_tool.state_root().mkdir(parents=True, exist_ok=True)
    review_tool.pidfile().write_text(str(proc.pid))
    assert review_tool.cmd_stop() == 0
    assert proc.wait(timeout=10) != 0
    assert not review_tool.pidfile().exists()


def test_stop_tolerates_stale_pidfile(env):
    review_tool.state_root().mkdir(parents=True, exist_ok=True)
    review_tool.pidfile().write_text("999999")
    assert review_tool.cmd_stop() == 0
    assert not review_tool.pidfile().exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test`
Expected: FAIL with `AttributeError: ... 'daemon_action'`

- [ ] **Step 3: Implement**

Add to `review_tool.py`:

```python
import signal
import time
import urllib.request


def current_port() -> int:
    return int(os.environ.get("REVIEW_BRANCH_PORT", DEFAULT_PORT))


def pidfile() -> Path:
    return state_root() / "daemon.pid"


def health_check(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _vtuple(version: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", version)) or (0,)


def daemon_action(health: dict | None) -> str:
    if health is None:
        return "start"
    if health.get("app") != APP_NAME:
        return "squatter"
    if _vtuple(str(health.get("version", "0"))) < _vtuple(__version__):
        return "restart"
    return "use"


def spawn_daemon(port: int) -> None:
    state_root().mkdir(parents=True, exist_ok=True)
    log = (state_root() / "daemon.log").open("a")
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "daemon"],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "REVIEW_BRANCH_PORT": str(port)},
    )


def _wait(predicate, tries: int = 50, delay: float = 0.1) -> bool:
    for _ in range(tries):
        if predicate():
            return True
        time.sleep(delay)
    return False


def cmd_open(round_dir: Path) -> str:
    if not (round_dir / "review.toml").exists():
        raise SystemExit(f"{round_dir}: no review.toml")
    route = route_for(round_dir)
    port = current_port()
    action = daemon_action(health_check(port))
    if action == "squatter":
        raise SystemExit(f"port {port} is in use by another application; set REVIEW_BRANCH_PORT")
    if action == "restart":
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", method="POST", data=b"")
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass
        _wait(lambda: health_check(port) is None)
        action = "start"
    if action == "start":
        spawn_daemon(port)
        if not _wait(lambda: health_check(port) is not None):
            raise SystemExit(f"daemon failed to start; see {state_root() / 'daemon.log'}")
    return f"http://127.0.0.1:{port}/{route}/"


def cmd_daemon() -> int:
    server = make_server(current_port())
    state_root().mkdir(parents=True, exist_ok=True)
    pidfile().write_text(str(os.getpid()))
    try:
        server.serve_forever()
    finally:
        pidfile().unlink(missing_ok=True)
    return 0


def cmd_stop() -> int:
    pf = pidfile()
    if not pf.exists():
        print("daemon not running (no pidfile)")
        return 0
    pid = int(pf.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"stopped daemon (pid {pid})")
    except ProcessLookupError:
        print(f"removed stale pidfile (pid {pid} not running)")
    pf.unlink(missing_ok=True)
    return 0
```

Wire into `main`:

```python
    if args.command == "open":
        print(cmd_open(Path(args.review_dir)))
        return 0
    if args.command == "daemon":
        return cmd_daemon()
    if args.command == "stop":
        return cmd_stop()
```

Note: `test_stop_kills_pidfile_process` asserts `proc.wait() != 0` because SIGTERM produces a negative returncode; the point is that the process died.

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py tests/review_branch/test_lifecycle.py
git commit -m "Add daemon lifecycle: open, foreground daemon, stop"
```

---

### Task 11: install subcommand

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py`
- Create: `tests/review_branch/test_install.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `INSTALL_MAP = {"review_tool.py": "review-branch", "glab_comment.py": "glab-comment", "gh_comment.py": "gh-comment"}`, `bin_dir() -> Path` (`REVIEW_BRANCH_BIN` or `~/.local/bin`), `install_scripts(src_dir: Path, dest_dir: Path) -> list[str]` (copies present sources, chmod 755, returns installed names), `cmd_install() -> int` (installs from this file's own directory, prints installed and skipped names). The comment scripts do not exist until the comment-posters plan lands; skipping them cleanly is expected behavior now.

- [ ] **Step 1: Write the failing tests**

`tests/review_branch/test_install.py`:

```python
# ABOUTME: tests for the install subcommand copying scripts to the bin dir
# ABOUTME: covers copy, executable bit, missing-source skip, and env override

import os

import review_tool


def test_install_scripts_copies_and_chmods(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "review_tool.py").write_text("#!/usr/bin/env python3\n")
    (src / "glab_comment.py").write_text("#!/usr/bin/env python3\n")
    dest = tmp_path / "bin"
    installed = review_tool.install_scripts(src, dest)
    assert installed == ["review-branch", "glab-comment"]
    assert (dest / "review-branch").exists()
    assert os.access(dest / "review-branch", os.X_OK)
    assert not (dest / "gh-comment").exists()


def test_cmd_install_uses_env_bin(env, capsys):
    assert review_tool.main(["install"]) == 0
    out = capsys.readouterr().out
    assert str(env / "bin" / "review-branch") in out
    assert (env / "bin" / "review-branch").exists()
    assert "skipped" in out  # comment scripts not present yet
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test`
Expected: FAIL with `AttributeError: ... 'install_scripts'`

- [ ] **Step 3: Implement**

Add to `review_tool.py`, wire `install` into `main` (`return cmd_install()`):

```python
import shutil

INSTALL_MAP = {
    "review_tool.py": "review-branch",
    "glab_comment.py": "glab-comment",
    "gh_comment.py": "gh-comment",
}


def bin_dir() -> Path:
    return Path(os.environ.get("REVIEW_BRANCH_BIN", "~/.local/bin")).expanduser()


def install_scripts(src_dir: Path, dest_dir: Path) -> list[str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    installed = []
    for src_name, dest_name in INSTALL_MAP.items():
        src = src_dir / src_name
        if not src.exists():
            continue
        dest = dest_dir / dest_name
        shutil.copy2(src, dest)
        dest.chmod(0o755)
        installed.append(dest_name)
    return installed


def cmd_install() -> int:
    dest = bin_dir()
    installed = install_scripts(Path(__file__).resolve().parent, dest)
    for name in installed:
        print(f"installed {dest / name}")
    for name in sorted(set(INSTALL_MAP.values()) - set(installed)):
        print(f"skipped {name} (source not present)")
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py tests/review_branch/test_install.py
git commit -m "Add install subcommand copying scripts to the bin dir"
```

---

### Task 12: Reference docs

**Files:**
- Create: `plugins/review-branch/skills/review-branch/references/data-format.md`
- Create: `plugins/review-branch/skills/review-branch/references/http-api.md`
- Create: `plugins/review-branch/skills/review-branch/references/diagrams.md`

**Interfaces:**
- Consumes: the contracts implemented in Tasks 5-10 (these docs must match that code exactly).
- Produces: the specs the rewritten SKILL.md (Task 13) and the future comment-posters plan reference.

- [ ] **Step 1: Write `references/data-format.md`**

```markdown
# Review data format

Two files per review round, with strict ownership. `review.toml` is written
only by the reviewing agent. `state.json` is written only by the review daemon
on behalf of the browser. The renderer and manifest generator merge the two;
the human's edits win. These formats are consumer-agnostic: anything that
writes valid review.toml gets the same HTML, daemon, and manifest behavior.

## Location

`${REVIEW_BRANCH_HOME:-${XDG_DATA_HOME:-~/.local/share}/review-branch}/<repo-id>/<slug>/round-N/`

- repo-id: `<repo-name>-<first 4 hex of sha256(origin url, or main worktree abspath when no remote)>`
- slug: `mr-<n>`, `pr-<n>`, or a slugified branch name
- round-N: one directory per review round; a re-review is a new round, never an edit
- `review-branch init --slug <slug>` (run inside the repo) creates the next round and prints its path

The data root is a git repo; the tool auto-commits every write with messages
shaped `<repo-id> <slug> round-N: <action>`. Comment rewrite history lives in
this git history, not in the files.

## review.toml

    [review]
    title = "MR 124 review - short description"
    vcs = "glab"              # glab | gh | local
    number = 124              # omit in local mode
    url = "https://..."       # MR/PR url; omit in local mode
    source_branch = "..."
    target_branch = "main"
    commits = 4
    files = "20 (+1752 / -43)"
    spec = "docs/specs/..."   # optional

    [overall]
    body = """Markdown prose framing the change and headline asks."""

    [[assets]]                # optional, rendered in order below the header
    type = "svg"              # svg (xml declaration stripped) | html (verbatim)
    path = "diagram.svg"      # relative to the round directory; inlined at render
    caption = "..."           # optional

    [[findings]]
    id = "f1"                 # stable; findings are append-only within a round
    severity = "high"         # high | med | low | info
    title = "..."
    file = "runner/api.py"
    lines = "108-121"         # optional
    lenses = ["security"]     # optional
    body = """Markdown explanation."""
    snippet = '''raw code, renderer escapes'''   # optional
    fix = "one-line suggested fix"               # optional
    comment = """Draft comment body, markdown."""
    comment_rev = 1           # bump on every rewrite of comment
    anchor = "runner/api.py:121"  # postable new-file line; falls back to file + last number in lines
    commentable = true        # false renders without a comment area
    posted_at = "..."         # written by the agent after posting
    posted_url = "..."
    posted_body = """Final text as posted, attribution marker excluded."""

    [[hex]]                   # optional table rows
    boundary = "..."
    change = "..."
    status = "OK"             # OK | OK / nit | Concern | Violation

    [[coverage]]              # optional table rows
    surface = "..."
    covered = "tests/..."     # empty string renders as a dash
    gap = "f2"                # empty string renders as a dash

    [[files_touched]]         # optional table rows
    path = "runner/api.py"
    delta = "+18"
    notes = "see f1, f2"

Prose fields are markdown (commonmark plus tables). The renderer escapes
everything else; never pre-escape content.

## state.json

    {
      "updated_at": "2026-08-08T14:00:00Z",
      "findings": {
        "f1": {
          "disposition": "post",          // "post" | "skip" | null
          "note": "soften this",
          "note_rev": 1,
          "edited_comment": "...",
          "edited_comment_rev": 1
        }
      }
    }

## Merge and staleness rules

- A note or edit is stale when its rev is lower than the finding's
  comment_rev (default 1). Stale entries are flagged, not applied.
- Postable body: edited_comment when edited_comment_rev equals comment_rev,
  else comment.
- When the agent rewrites a comment from a note it bumps comment_rev; the page
  then shows the consumed note as a dimmed "applied" annotation and resets the
  textarea to the new draft.
- `review-branch status <round-dir>` prints the full merged view as JSON.
- `review-branch manifest <round-dir> [--exclude f3,f7]` prints posting
  entries `[{"file", "line", "body"}]` for findings with disposition "post"
  that are commentable and not yet posted.
```

- [ ] **Step 2: Write `references/http-api.md`**

```markdown
# Review daemon HTTP API

One daemon serves every review. Binds 127.0.0.1 only; default port 43117,
override with `REVIEW_BRANCH_PORT`. No auth: localhost trust is the threat
model. Routes are the filesystem: `/<repo-id>/<slug>/round-N/` maps to the
same path under the data root. There is no registry; the daemon serves what
exists on disk.

## Lifecycle

- `review-branch open <round-dir>` starts the daemon if needed (detached,
  survives the launching session), restarts it when the CLI is newer than the
  running daemon, and prints the review URL. Idempotent.
- `review-branch stop` stops it via the pidfile in
  `${XDG_STATE_HOME:-~/.local/state}/review-branch/`. Log: `daemon.log` there.
- The daemon stays up until stopped or reboot.

## Endpoints

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/health` | `{"app": "review-branch", "version", "data_root"}` |
| GET | `/` | index of all reviews, newest activity first |
| GET | `/<rid>/<slug>/round-N/` | review page rendered in memory (served mode) |
| GET | `/<rid>/<slug>/round-N` | 301 to the trailing-slash form |
| GET | `.../api/state` | current state.json (`{"findings": {}}` if absent) |
| GET | `.../api/version` | `{"token": <changes when toml/state/assets change>}` |
| POST | `.../api/state` | validate `{"findings": {...}}`, stamp updated_at, write state.json, refresh review.html snapshot, git commit, return `{"ok": true, "token"}` |
| POST | `/api/shutdown` | stop the daemon (used by the version handshake) |

Unknown routes and paths outside the data root return 404 JSON. Invalid JSON
bodies return 400. The page saves whole-document state (debounced), polls
`api/version` and reloads when clean, holds unsaved changes with a banner and
retry when the daemon is unreachable, and is read-only when opened via
`file://`.
```

- [ ] **Step 3: Write `references/diagrams.md`**

```markdown
# Review diagrams

One or more diagrams at the top of a review help the reviewer understand what
the branch does before reading findings. Pick the shape from what the change
actually is; skip diagrams for trivial or docs-only branches.

## Choosing the diagram

- Sequence diagram (default): control flow across components, request paths,
  new interactions between services or layers.
- ER-style diagram: schema changes, new tables, relationship changes.
- State diagram: lifecycle changes, new status fields, transition rules.
- Component diagram: architectural moves, new services, dependency direction.

Multiple diagrams are fine when the branch does more than one thing; order
them most-important first. When SVG is the wrong tool, an `html` asset passes
a fragment through verbatim.

## Authoring rules

Write the SVG file into the round directory and reference it from
`[[assets]]` with a caption. The renderer inlines it.

- Canvas: width 1000, height as needed. `viewBox` set, no fixed pixel
  width/height attributes beyond the viewBox.
- Palette (matches the tracker theme): background transparent, boxes
  `#1c2030` with `#2a3042` borders, text `#e6e8ee`, muted text `#9aa3b2`,
  accents `#7aa2f7` (primary), `#f7768e` (problem areas), `#9ece6a` (new or
  added elements), `#e0af68` (changed elements).
- Text: minimum font size 12, `font-family="ui-monospace, SFMono-Regular,
  Menlo, monospace"` for identifiers, sans-serif for prose labels.
- Label the diagram in terms of this branch: mark new elements ("new"),
  changed elements ("changed"), and the finding ids they relate to (e.g.
  "f3") where relevant.
- No emojis. No decoration that does not carry information.
```

- [ ] **Step 4: Verify prose rules and commit**

Run: `grep -n "—" plugins/review-branch/skills/review-branch/references/*.md`
Expected: no output (no em-dashes anywhere).

```bash
git add plugins/review-branch/skills/review-branch/references/
git commit -m "Add data-format, http-api, and diagrams references"
```

---

### Task 13: Rewrite SKILL.md, retire the old template, sync plugin metadata

**Files:**
- Rewrite: `plugins/review-branch/skills/review-branch/SKILL.md`
- Delete: `plugins/review-branch/skills/review-branch/assets/template.html`
- Delete: `plugins/review-branch/skills/review-branch/references/html-template.md`
- Modify: `plugins/review-branch/.claude-plugin/plugin.json`
- Rewrite: `plugins/review-branch/README.md`

**Interfaces:**
- Consumes: the CLI surface from Tasks 4-11 and the references from Task 12.
- Produces: the shipped skill. The glab-comment/gh-comment skills arrive in the comment-posters plan; this SKILL.md references them as the sanctioned posting path.

- [ ] **Step 1: Rewrite `SKILL.md`** (full replacement content)

````markdown
---
name: review-branch
description: Deep multi-lens review of an MR, PR, or any local branch. Dispatches 4 parallel subagents (architecture, security, test coverage, naming/API) inside an isolated worktree, writes structured findings to a central review store, and serves a collaborative HTML tracker from a local daemon with tri-state dispositions, editable comment drafts, and notes to Claude that round-trip so checked comments can be posted via the glab-comment or gh-comment skills when explicitly asked. Use when asked to deeply review an MR/PR, do a thorough code review of a branch, get a second opinion on changes, or uses /review-branch. Works against GitLab (glab) and GitHub (gh); auto-detects from the git remote. Also handles local-only branch reviews (no MR/PR yet) by diffing against the default branch.
allowed-tools: Bash(git *), Bash(glab *), Bash(gh *), Bash(jq *), Bash(mkdir *), Bash(test *), Bash(ls *), Bash(open *), Bash(review-branch *), Bash(*review_tool.py *), Read, Write, Edit, Glob, Grep, Agent, Skill
---

# review-branch

Produce a deep, multi-lens code review as structured data rendered into a
collaborative HTML tracker. Findings live in `review.toml`; the human marks
dispositions, edits drafts, and leaves notes in the served page; posting to
the MR/PR happens only through the glab-comment or gh-comment skills and only
when explicitly asked.

## Workflow

```
BOOTSTRAP TOOL --> PARSE INPUT --> DETECT VCS --> RESOLVE BRANCH + INIT ROUND
  --> WORKTREE --> SEED CONTEXT --> DISPATCH 4 LENSES (parallel)
  --> WRITE review.toml --> DIAGRAM --> RENDER + OPEN --> REPORT
```

## Step 0: Bootstrap the tool

```bash
review-branch --version 2>/dev/null
```

If the command is missing or prints a version lower than the plugin's copy
(`"${CLAUDE_PLUGIN_ROOT}/scripts/review_tool.py" --version`), run:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/review_tool.py" install
```

## Step 1: Parse input

The skill accepts one optional argument. Determine shape:

| Input | Meaning |
|---|---|
| digits only (e.g., `124`) | MR/PR number; VCS picked in Step 2 |
| URL containing `/merge_requests/<n>` | GitLab MR; extract `<n>` |
| URL containing `/pull/<n>` | GitHub PR; extract `<n>` |
| anything else | branch name; use directly |
| no argument | use the current branch (`git rev-parse --abbrev-ref HEAD`) |

Error early if:

- Current branch is `main`, `master`, or `trunk` and no argument was given.
- The argument is a number but Step 2 detects no remote; ask the user.

## Step 2: Detect VCS

```bash
remote=$(git remote get-url origin 2>/dev/null || echo "")
case "$remote" in
  *gitlab*) vcs="glab" ;;
  *github*) vcs="gh" ;;
  *)        vcs="local" ;;
esac
```

Local mode: no MR/PR metadata, no prior comments; diff against
`origin/<default-branch>`.

## Step 3: Resolve branch, slug, and round directory

| Input shape | VCS | Source branch |
|---|---|---|
| MR number | `glab` | `glab mr view <n> --output json \| jq -r .source_branch` |
| PR number | `gh` | `gh pr view <n> --json headRefName --jq .headRefName` |
| branch name | any | the input |
| (none) | any | `git rev-parse --abbrev-ref HEAD` |

Target branch: MR `.target_branch`; PR `--json baseRefName`; local
`git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@'`.

Slug: `mr-<n>`, `pr-<n>`, or the branch name through
`tr '/' '-' | tr -c 'a-zA-Z0-9-' '-'` with leading/trailing dashes trimmed.

Create the round directory (run from the main repo, before entering the
worktree) and capture its absolute path:

```bash
REVIEW_DIR=$(review-branch init --slug <slug>)
```

## Step 4: Worktree

Invoke the `worktree` skill via the `Skill` tool with the resolved source
branch (or MR/PR number). It handles branch resolution, env-file copy,
bootstrap, and `EnterWorktree`. Fall back to the inline equivalent from that
skill's documentation only if the skill is unavailable.

## Step 5: Seed context

Ephemeral scratch goes in the worktree's `.llm/` (never in `$REVIEW_DIR`).

```bash
case "$vcs" in
  glab) glab mr diff <n> > .llm/diff.patch ;;
  gh)   gh pr diff <n>   > .llm/diff.patch ;;
  local) git diff origin/<target-branch>...HEAD > .llm/diff.patch ;;
esac
grep '^diff --git' .llm/diff.patch | awk '{print $4}' | sed 's@^b/@@' > .llm/changed-files.txt
```

Prior comments (MR/PR mode only; see `references/glab.md` / `references/gh.md`):

```bash
case "$vcs" in
  glab) glab mr view <n> --comments > .llm/prior-comments.md ;;
  gh)
    OWNER_REPO=$(gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"')
    {
      gh pr view <n> --comments
      echo
      echo "## Inline review comments"
      gh api "repos/${OWNER_REPO}/pulls/<n>/comments" \
        --jq '.[] | "- @\(.user.login) at \(.path):\(.line // .original_line): \(.body)"'
    } > .llm/prior-comments.md
    ;;
esac
```

Hex detection:

```bash
hex_doc=""; hex_mode="false"
test -f docs/hexagonal-architecture.md && { hex_doc="docs/hexagonal-architecture.md"; hex_mode="true"; }
test -d core/ports && hex_mode="true"
test -d src/core/ports && hex_mode="true"
```

Spec detection: if the branch matches a ticket pattern (`[A-Z]+-[0-9]+`),
look for `docs/spec*/<TICKET>*.md` and pass it to the coverage lens.

## Step 6: Dispatch lenses (parallel)

Spawn all 4 lens subagents in a single message. Each prompt carries:
worktree_path, target_branch, diff_path, changed_files, prior_comments_path
(or `none`), hex_mode, hex_doc, spec_path, plus instructions to read
`references/agent-contract.md` and its own `agents/lens-*.md` prompt, and to
return a JSON array per the contract. Lenses: `review-branch:lens-architecture`,
`review-branch:lens-security`, `review-branch:lens-coverage`,
`review-branch:lens-naming`.

If a subagent returns malformed JSON, retry once; if it still fails, log the
lens as "no findings" and continue.

## Step 7: Aggregate into review.toml

Dedupe: same file + line range within 5 lines + same topic (>= 50% word
overlap in title) merge into one entry, keeping highest severity, the most
specific description, concatenated distinct drafts, unioned lenses. Sort by
severity (high, med, low, info), then file path, then line. Ids: `f1`, `f2`,
... in final order.

Write `$REVIEW_DIR/review.toml` incrementally per `references/data-format.md`:

1. First `Write`: the `[review]` table, `[overall]`, and any `[[hex]]`,
   `[[coverage]]`, `[[files_touched]]` rows.
2. Then append findings in batches (one `Edit` per lens's merged findings).
   Never emit the whole document in one tool call.

Every finding that warrants an MR/PR comment gets a `comment` draft (tone per
`references/agent-contract.md`) and an `anchor` on a line the diff touches.
Context-only findings get `commentable = false`.

## Step 8: Diagram

Pick the diagram type per `references/diagrams.md`, author the SVG file(s)
into `$REVIEW_DIR`, and add `[[assets]]` entries. Skip only for trivial
branches.

## Step 9: Render and open

```bash
review-branch render "$REVIEW_DIR"
review-branch open "$REVIEW_DIR"
```

`open` prints the review URL. Offer to open it in the browser:
`open <url>` (macOS).

## Step 10: Report

1. The review URL (and the on-disk fallback `$REVIEW_DIR/review.html`).
2. Summary line: counts per severity.
3. How the collaboration works, in one line: mark Post/Skip, edit drafts,
   leave notes; then ask to post and the comment skills take it from there.
4. Worktree cleanup command: `git worktree remove <worktree-path>`.

Stop after this. Do not summarize again or offer to refine.

## After the human reviews (the collaboration loop)

Read state with `review-branch status "$REVIEW_DIR"`. The human's phrasing
picks the mode:

- "update the html for f8": rewrite that finding's `comment` in review.toml
  (start from their `edited_comment` if present), bump `comment_rev`, run
  `review-branch render`, done; the served page reloads itself.
- "show me the edit here": print the revised body in the terminal instead.
- "post the checked ones" / `/glab-comment` / `/gh-comment`: interpret notes
  and post through the matching comment skill. A clear note produces a
  rewrite (bump `comment_rev`, record in review.toml). An ambiguous note, one
  contradicting the finding, or one that reads as a question holds that
  finding out of the batch (`--exclude`); post the clear ones and raise the
  held ones for discussion. `review-branch manifest "$REVIEW_DIR"` emits the
  batch for the comment skill.
- After posting: write `posted_at`, `posted_url`, `posted_body` into
  review.toml, commit message `<rid> <slug> round-N: fN posted`, re-render.

## Rules and anti-patterns

- **No auto-posting.** Posting happens only through the glab-comment or
  gh-comment skills, and only when explicitly asked. Never call `glab mr
  note`, `gh pr comment`, or raw discussion/review-comment endpoints.
- **Findings are append-only.** Never delete or renumber a finding within a
  round; a wrong finding gets disposition Skip. A re-review after new pushes
  is a new round: `review-branch init` again.
- **review.toml is yours; state.json is not.** Never write state.json; the
  daemon owns it.
- **No confidence threshold.** Every lens finding lands in the tracker.
- **Read full files end-to-end.** The diff is for navigation only.
- **Reproduce when possible.** `reproduced: true` is a much stronger signal.
- **Worktree stays.** Do not auto-remove it.
- **Stop after Step 10.**
````

- [ ] **Step 2: Delete the retired template files**

```bash
git rm plugins/review-branch/skills/review-branch/assets/template.html \
       plugins/review-branch/skills/review-branch/references/html-template.md
```

- [ ] **Step 3: Update `plugin.json`**

Set `version` to `"0.2.0"` and replace `description` with:

```
Deep multi-lens review of an MR, PR, or any local branch. Dispatches 4 parallel subagents (architecture, security, test coverage, naming/API) inside an isolated worktree, writes structured findings to a central review store, and serves a collaborative HTML tracker from a local daemon with tri-state dispositions, editable comment drafts, and notes to Claude. Nothing auto-posts; posting happens through companion comment skills only when explicitly asked. Works against GitLab (glab) and GitHub (gh); auto-detects from the git remote.
```

Keep name, author, and keywords as they are.

- [ ] **Step 4: Rewrite `README.md`** (full replacement content)

````markdown
# review-branch

Deep, multi-lens code review of an MR, PR, or any local branch. Findings are
structured data rendered into a collaborative HTML tracker served by a local
daemon. Nothing auto-posts; posting happens through companion comment skills
only when explicitly asked.

## What it does

Given an MR number, PR number, MR/PR URL, or branch name, the skill:

1. Auto-detects the VCS from `git remote get-url origin` (gitlab, github, or
   local-only mode).
2. Creates a round directory in the central review store
   (`~/.local/share/review-branch/<repo-id>/<slug>/round-N/`).
3. Sets up an isolated worktree via the worktree plugin.
4. Dispatches 4 parallel lens subagents (architecture, security, coverage,
   naming) that read full source files and run tests.
5. Aggregates findings into `review.toml`: severities, draft comments,
   anchors, plus an explanatory SVG diagram of what the branch does.
6. Renders and serves the tracker: `review-branch open` prints a
   `http://127.0.0.1:43117/...` URL.

In the tracker you mark each finding Post / Skip / Undecided, edit the
comment drafts directly, and leave free-text notes ("soften this", "mention
the follow-up MR"). State persists to disk through the daemon and every
change is committed to a git repo at the review store root. When you ask
Claude to post, it interprets your notes, rewrites where asked, and posts the
checked comments through the glab-comment or gh-comment skill with the From
Claude attribution marker.

## Install

```bash
claude plugin install review-branch@tednaleid
claude plugin install worktree@tednaleid       # recommended companion
```

The skill installs the `review-branch` CLI to `~/.local/bin` on first use
(`review_tool.py install`).

## Use

- `/review-branch 124` (MR or PR number, picked by remote)
- `/review-branch https://github.com/owner/repo/pull/42`
- `/review-branch feature/auth-fix` (diff vs the default branch)
- `/review-branch` (current branch)

Useful CLI verbs against a round directory: `open` (serve and print URL),
`render` (refresh the on-disk snapshot), `status` (merged state as JSON),
`manifest` (postable comments), `stop` (stop the daemon).

## Design notes

- Structured data is canonical: `review.toml` (agent-written) and
  `state.json` (browser-written via the daemon) merge at render and post
  time; your edits win. See `skills/review-branch/references/data-format.md`.
- The daemon serves every review on one port; `GET /` is an index of all
  reviews. See `skills/review-branch/references/http-api.md`.
- Findings are append-only within a round; re-reviews create new rounds;
  comment rewrite history lives in the review store's git log.
- The worktree is left in place; the skill prints the cleanup command.
````

- [ ] **Step 5: Sync marketplace metadata and run everything**

```bash
just sync
just check
just test
```

Expected: `All good.` from check; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Rewrite review-branch skill around review_tool and central store"
```

---

## Execution notes

- Tasks are strictly ordered; each leaves `just test` green.
- The comment-posters plan (glab-comment migration, gh-comment) and the
  worktree-script plan are separate documents; nothing here depends on them.
  Until they land, `install` reports the comment scripts as skipped and the
  SKILL.md posting path references skills that ship in the next plugin
  version. Do not bump or tag the plugin release until all three plans land;
  `just bump review-branch` stays a Ted-run step.
- Deviation from spec flagged during planning: `tomli-w` is not a dependency
  because the tool never writes TOML.





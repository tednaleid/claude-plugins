# Comment Posters and Worktree Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the posting path (migrate `glab-comment` into the review-branch plugin, build a sibling `gh-comment`) and the wtp-style worktree-creation script, so a review's checked comments actually post and worktree setup is one command.

**Architecture:** Two standalone uv-shebang poster scripts (`glab_comment.py`, `gh_comment.py`) live in `plugins/review-branch/scripts/` beside `review_tool.py`; `review-branch install` already copies all three to the PATH. Each poster consumes the `review-branch manifest` JSON, prepends the "From Claude" marker, validates diff anchors, and refuses duplicates. A third uv script, `plugins/worktree/scripts/worktree_tool.py`, codifies worktree creation with optional `.worktree.toml` hooks. Each poster and the worktree tool is a single self-contained file (no cross-imports) so it stays copyable to the PATH; the small shared diff-parsing helpers are duplicated across the two posters by deliberate choice, the same standalone-script tradeoff already made for `review_tool.py`.

**Tech Stack:** Python >= 3.12 uv single-file scripts; stdlib (`argparse`, `json`, `re`, `subprocess`, `tomllib`); `glab` and `gh` CLIs; pytest via the existing `just test`.

## Global Constraints

- Scripts are single-file uv-shebang (`#!/usr/bin/env -S uv run --script`) with an inline metadata block, `requires-python = ">=3.12"`, and NO third-party dependencies (stdlib only, incl. `tomllib`).
- Every code file starts with two `ABOUTME: ` comment lines. No emojis, no em-dashes in any code, prose, or docs.
- The attribution marker is exactly `> **From Claude:**` (probe substring `**From Claude:**`), prepended to every posted body, unconditionally.
- Posting rules, verbatim intent from the source skill: post only when the user explicitly asks for that specific post; one ask authorizes one batch; never resolve, approve, merge, or close; a failed-looking POST may have landed, so never hand-retry, re-run and let the duplicate check decide.
- Anchors target new-file lines only. No multi-line ranges, no thread replies, no edit/delete.
- Manifest format (produced by `review-branch manifest`): a JSON array of `{"file": str, "line": int, "body": str}`; also accept `{"file","line","body_file": path}`.
- Genericize on migration: no personal names in shipped code/skills; refer to "the user" or "you", not "Ted". The marker stays "From Claude" (it attributes the author, not the account holder).
- Commit messages: short imperative, no conventional-commit prefixes, ending with a blank line then exactly `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Never `--no-verify`.
- Run tests with `just test`; keep it green before every commit. Poster/worktree unit tests exercise the PURE functions (diff parsing, anchor resolution, marker, manifest loading, hook parsing) with no network and no real `glab`/`gh` calls.
- Each poster script must remain importable as a module for tests (`import glab_comment` / `import gh_comment`) with all side effects behind `if __name__ == "__main__":`. Same for `worktree_tool`.
- Do NOT bump or tag any release in this plan. Versioning/marketplace is the final task and stays local (no push).

## File Structure

```
plugins/review-branch/scripts/glab_comment.py          # Create: migrated from ~/.local/bin/glab-comment
plugins/review-branch/scripts/gh_comment.py            # Create: GitHub sibling
plugins/review-branch/skills/glab-comment/SKILL.md     # Create: genericized skill
plugins/review-branch/skills/gh-comment/SKILL.md       # Create: new skill
plugins/worktree/scripts/worktree_tool.py              # Create: worktree automation
plugins/worktree/skills/worktree/SKILL.md              # Rewrite: shrink to "run the script, EnterWorktree"
plugins/review-branch/skills/review-branch/SKILL.md    # Modify: posting path is now live
plugins/review-branch/README.md                        # Modify: posters ship; install no longer skips them
tests/posters/conftest.py                              # Create: sys.path for the two poster scripts
tests/posters/test_glab_comment.py                     # Create
tests/posters/test_gh_comment.py                       # Create
tests/worktree/conftest.py                             # Create: sys.path for worktree_tool
tests/worktree/test_worktree_tool.py                   # Create
.claude-plugin/marketplace.json                        # Modify: via `just sync` (final task)
plugins/worktree/.claude-plugin/plugin.json            # Modify: version bump (final task)
```

Test discovery note: `tests/posters/` and `tests/worktree/` are collected by the existing `just test` (`pytest tests --ignore=tests/ui`). Each poster/worktree conftest inserts its script directory on `sys.path` exactly like `tests/review_branch/conftest.py` does for `review_tool`.

---

## Group A: glab-comment migration

### Task 1: Migrate glab_comment.py

**Files:**
- Create: `plugins/review-branch/scripts/glab_comment.py`
- Create: `tests/posters/conftest.py`
- Create: `tests/posters/test_glab_comment.py`

**Interfaces:**
- Produces (pure, importable): `parse_diff_lines(diff_text) -> list[dict]`, `find_anchor(diff_lines, line, side="new") -> dict|None`, `ensure_marker(body) -> str`, `find_duplicates(discussions, path, line) -> list`, `nearest_addressable(diff_lines, line, count=3, side="new") -> list[int]`, `build_payload(body, shas, path, anchor, old_path=SAME_PATH) -> dict`, `load_items(args) -> list[dict]`, `MARKER`, `MARKER_PROBE`. CLI `main()` behind `__main__`.

- [ ] **Step 1: Copy the source script verbatim, then genericize the one personal reference**

The proven implementation lives at `~/.local/bin/glab-comment`. Copy its entire contents to `plugins/review-branch/scripts/glab_comment.py` unchanged EXCEPT the comment at the top of the file (currently lines 19-21) that reads:

```python
# The token posts under Ted's account, so this label is the only thing that
# separates Claude's voice from his. Every body carries it, and it stays bare:
# anything past the label competes with the comment for the reader's attention.
```

Replace with:

```python
# The comment posts under the user's account, so this label is the only thing
# that separates Claude's voice from theirs. Every body carries it, and it stays
# bare: anything past the label competes with the comment for the reader's eye.
```

Keep the two `ABOUTME:` lines, the shebang, and all functions (`parse_diff_lines`, `find_anchor`, `find_duplicates`, `build_payload`, `ensure_marker`, `nearest_addressable`, `repo_root`, `glab_api`, `parse_json_stream`, `resolve_mr`, `diff_refs`, `diff_index`, `read_body`, `load_items`, `check_items`, `post_one`, `describe`, `main`) exactly. Then `chmod +x plugins/review-branch/scripts/glab_comment.py`.

- [ ] **Step 2: Write the pure-function tests**

`tests/posters/conftest.py`:

```python
# ABOUTME: pytest path setup for the review-branch poster scripts
# ABOUTME: makes plugins/review-branch/scripts importable as glab_comment / gh_comment

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "review-branch" / "scripts"),
)
```

`tests/posters/test_glab_comment.py`:

```python
# ABOUTME: tests for glab_comment pure functions (diff parsing, anchors, marker, dedup)
# ABOUTME: no network and no real glab calls; only the pure helpers are exercised

import json

import glab_comment as gc

DIFF = """@@ -10,3 +10,4 @@
 context line
-removed line
+added line one
+added line two
 trailing context"""


def test_parse_diff_lines_tracks_old_and_new_numbers():
    lines = gc.parse_diff_lines(DIFF)
    added = [e for e in lines if e["kind"] == "added"]
    assert [e["new_line"] for e in added] == [11, 12]
    removed = [e for e in lines if e["kind"] == "removed"]
    assert removed[0]["old_line"] == 11


def test_find_anchor_added_line_uses_new_line():
    lines = gc.parse_diff_lines(DIFF)
    assert gc.find_anchor(lines, 11) == {"new_line": 11}


def test_find_anchor_context_line_uses_both():
    lines = gc.parse_diff_lines(DIFF)
    anchor = gc.find_anchor(lines, 10)
    assert anchor == {"old_line": 10, "new_line": 10}


def test_find_anchor_missing_line_returns_none():
    lines = gc.parse_diff_lines(DIFF)
    assert gc.find_anchor(lines, 999) is None


def test_ensure_marker_prepends_once():
    body = gc.ensure_marker("hello")
    assert body.startswith("> **From Claude:**")
    assert gc.ensure_marker(body) == body  # idempotent


def test_nearest_addressable_orders_by_distance():
    lines = gc.parse_diff_lines(DIFF)
    assert gc.nearest_addressable(lines, 11, count=2) == [10, 12]


def test_find_duplicates_matches_marker_and_position():
    discussions = [
        {"id": "d1", "notes": [{"body": "> **From Claude:** x",
                                 "position": {"new_path": "a.py", "new_line": 11}}]},
        {"id": "d2", "notes": [{"body": "human note",
                                 "position": {"new_path": "a.py", "new_line": 11}}]},
    ]
    assert gc.find_duplicates(discussions, "a.py", 11) == ["d1"]


def test_load_items_reads_manifest(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"file": "a.py", "line": 11, "body": "hi"}]))
    args = type("A", (), {"manifest": str(manifest), "general": False, "target": None})()
    items = gc.load_items(args)
    assert items == [{"path": "a.py", "line": 11, "body": "hi"}]
```

- [ ] **Step 3: Run the tests**

Run: `just test`
Expected: the new glab tests pass alongside the existing suite.

- [ ] **Step 4: Commit**

```bash
git add plugins/review-branch/scripts/glab_comment.py tests/posters/
git commit -m "Migrate glab-comment poster into the review-branch plugin"
```

### Task 2: Genericized glab-comment skill

**Files:**
- Create: `plugins/review-branch/skills/glab-comment/SKILL.md`

**Interfaces:**
- Consumes: `glab-comment` on PATH (installed by `review-branch install`).
- Produces: the `glab-comment` skill (invocable as `/glab-comment`).

- [ ] **Step 1: Write the skill**

Write `plugins/review-branch/skills/glab-comment/SKILL.md`, adapting the source skill (`~/.claude/skills/glab-comment/SKILL.md`) with the personal references removed. Full content:

````markdown
---
name: glab-comment
description: Post line-anchored review comments to a GitLab merge request. Use ONLY when the user explicitly asks to post a specific comment or set of comments. Never invoke on your own initiative; default to drafting the comment and showing it instead. Handles diff-ref lookup, anchor validation, duplicate detection, and the From Claude attribution marker. Pairs with review-branch: post the comments you marked in the tracker.
allowed-tools: Bash(glab-comment:*)
---

# glab-comment

Posts comments to a GitLab MR under the user's account. GitLab only.

## Before you post

- The user must have asked for this specific post. Drafting is the default; posting is the exception.
- One ask authorizes one post. "Post 4, 5, and 12" does not authorize posting 13 later in the session. Ask again.
- Never resolve, approve, merge, or close. This tool posts comments and nothing else.
- If the ask is ambiguous, or a note you were given reads as a question rather than an edit instruction, write the draft and show it, or raise the question. That is always the safe move.

## Usage

```sh
glab-comment src/api.py:141 --body-file draft.md      # one comment, MR from branch
glab-comment --mr 190 src/api.py:141 --body-file -    # explicit MR, body on stdin
glab-comment --mr 190 --manifest findings.json        # batch, the review-pass case
glab-comment --mr 190 --general --body-file summary.md # unpositioned MR note
glab-comment --mr 190 --manifest findings.json --dry-run # print payloads, post nothing
```

Manifest is a JSON array of `{"file": ..., "line": ..., "body_file": ...}`, or `body` for
inline text. It is exactly what `review-branch manifest <round-dir>` emits. Run `--dry-run`
first on any batch.

`FILE:LINE` is a line number in the **new** file. A comment can only land on a line the MR
diff touches. If the line is not in the diff the script refuses, names the closest
addressable lines, and posts nothing. Re-anchor to a line the MR actually introduced; that
is usually the better anchor anyway.

## Writing the comment

One finding per comment. Two findings, two comments.

The marker costs a line before you start. Spend the rest carefully.

Avoid:

> I noticed that in this function the error handling might potentially be an issue. It
> seems like the exception tuple may not cover all cases, which could possibly lead to
> unexpected behavior. You might want to consider whether this is the intended behavior.

Better:

> `_round_or_none` catches only `TypeError`; a `Decimal` string here raises
> `InvalidOperation` and 500s the endpoint.

- Lead with the claim. Cut "I noticed", "It seems", "You might want to consider".
- Name the failure as input to wrong result, not "could be an issue".
- Do not summarize what the code does. The author wrote it.
- Suggest a fix only if it fits on one line. Otherwise state the problem.
- Unsure? Ask. "Is the empty case intentional?" beats "this is wrong."

## What it does for you

Every body is posted with the marker on its own line, then a blank line, then your comment
and nothing else:

```markdown
> **From Claude:**

The list path gates its envelope; the detail path has no equivalent.
```

The comment posts under the user's account, so that label is the only thing separating
Claude's voice from theirs. Keep it bare. Do not pad it with an explanation of who wrote
the comment or whose account it came from; that is throat-clearing above a comment whose
whole job is to get to the point.

It also re-reads the MR's diff refs on every run, validates each anchor before posting any
of them, and refuses a line that already carries a From Claude comment. A POST that looks
like it failed may have landed, so never retry by hand; re-run the script and let the
duplicate check decide.

## Limits

- Anchors target new-file lines. Commenting on a removed line is not exposed.
- No multi-line (`line_range`) comments, no replies into an existing thread.
- No editing or deleting. Fix a bad comment in the GitLab UI.
- Consider a repo guard (e.g. a veer rule) blocking a raw `glab api ... /discussions -X
  POST`, so the marker, the anchor check, and the duplicate check cannot be bypassed.
````

- [ ] **Step 2: Verify no personal references and no em-dashes**

Run: `grep -niE "ted|—" plugins/review-branch/skills/glab-comment/SKILL.md`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add plugins/review-branch/skills/glab-comment/
git commit -m "Add genericized glab-comment skill"
```

---

## Group B: gh-comment

### Task 3: Build gh_comment.py

**Files:**
- Create: `plugins/review-branch/scripts/gh_comment.py`
- Create: `tests/posters/test_gh_comment.py`

**Interfaces:**
- Consumes: `glab_comment.py` as the structural reference (committed in Task 1); the manifest format.
- Produces (pure, importable): `split_files(diff_text) -> dict[str, str]`, `parse_diff_lines(hunk_text) -> list[dict]`, `find_anchor(diff_lines, line) -> int|None`, `nearest_addressable(diff_lines, line, count=3) -> list[int]`, `ensure_marker(body) -> str`, `find_duplicates(comments, path, line) -> list`, `load_items(args) -> list[dict]`, `MARKER`, `MARKER_PROBE`. CLI `main()` behind `__main__`.

Note on duplication: `ensure_marker`, `nearest_addressable`, and `load_items` are line-for-line the same as `glab_comment.py`; `parse_diff_lines`/`find_anchor` differ (GitHub anchors on a single new-side line with `side: "RIGHT"`, no `old_line`/`new_line` position object). This duplication is deliberate so each poster stays a standalone single-file script.

- [ ] **Step 1: Write the pure helpers and API glue**

Create `plugins/review-branch/scripts/gh_comment.py` (uv shebang, two `ABOUTME:` lines, no deps). Full content:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///

# ABOUTME: posts line-anchored review comments to a GitHub pull request via gh
# ABOUTME: prepends the From Claude marker, validates diff anchors, blocks duplicates

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
FILE_RE = re.compile(r"^\+\+\+ b/(.*)$")

MARKER = "> **From Claude:**"
MARKER_PROBE = "**From Claude:**"


def split_files(diff_text):
    """Map each new-file path to its unified-diff hunk text.

    `gh pr diff` emits one combined diff; file sections start at `diff --git`.
    Key on the `+++ b/<path>` header and keep the text from the first `@@`.
    A `+++ /dev/null` (deleted file) yields no path and is skipped.
    """
    files = {}
    path = None
    hunk_lines = []
    in_hunks = False

    def flush():
        if path and hunk_lines:
            files[path] = "\n".join(hunk_lines)

    for raw in diff_text.splitlines():
        if raw.startswith("diff --git"):
            flush()
            path, hunk_lines, in_hunks = None, [], False
        elif raw.startswith("+++ "):
            m = FILE_RE.match(raw)
            path = m.group(1) if m else None
        elif raw.startswith("@@"):
            in_hunks = True
            hunk_lines.append(raw)
        elif in_hunks:
            hunk_lines.append(raw)
    flush()
    return files


def parse_diff_lines(hunk_text):
    """One entry per hunk-body line, numbered on the new (RIGHT) side."""
    lines = []
    new_line = 0
    for raw in hunk_text.splitlines():
        header = HUNK_RE.match(raw)
        if header:
            new_line = int(header.group(1))
            continue
        if raw.startswith("+"):
            lines.append({"kind": "added", "new_line": new_line})
            new_line += 1
        elif raw.startswith("-"):
            lines.append({"kind": "removed", "new_line": None})
        elif raw.startswith(" "):
            lines.append({"kind": "context", "new_line": new_line})
            new_line += 1
    return lines


def find_anchor(diff_lines, line):
    """The line number if it is an added or context line in the diff, else None.

    GitHub comments anchor to a single new-side line with side RIGHT; a removed
    line has no new-side number and cannot be targeted.
    """
    for entry in diff_lines:
        if entry["new_line"] == line and entry["kind"] in ("added", "context"):
            return line
    return None


def nearest_addressable(diff_lines, line, count=3):
    """Addressable new-side lines closest to a rejected target, nearest first."""
    candidates = {
        e["new_line"]
        for e in diff_lines
        if e["new_line"] is not None and e["kind"] in ("added", "context")
    } - {line}
    return sorted(candidates, key=lambda n: (abs(n - line), n))[:count]


def ensure_marker(body):
    """Return the body with exactly one attribution marker at the top."""
    if MARKER_PROBE in body:
        return body.strip("\n")
    return f"{MARKER}\n\n{body.strip()}"


def find_duplicates(comments, path, line):
    """Ids of Claude-authored review comments already at path:line."""
    hits = []
    for c in comments:
        if MARKER_PROBE not in c.get("body", ""):
            continue
        c_line = c.get("line")
        if c_line is None:
            c_line = c.get("original_line")
        if c.get("path") == path and c_line == line:
            hits.append(c.get("id"))
    return hits


def gh(args, check=True):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if check and out.returncode != 0:
        raise SystemExit(f"gh {' '.join(args)} failed:\n{out.stderr.strip()}")
    return out


def owner_repo():
    out = gh(["repo", "view", "--json", "owner,name",
              "--jq", '"\\(.owner.login)/\\(.name)"'])
    return out.stdout.strip()


def resolve_pr(explicit):
    if explicit:
        return explicit
    out = gh(["pr", "view", "--json", "number", "--jq", ".number"], check=False)
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit("no PR for this branch; pass --pr")
    return int(out.stdout.strip())


def head_sha(n):
    out = gh(["pr", "view", str(n), "--json", "headRefOid", "--jq", ".headRefOid"])
    return out.stdout.strip()


def diff_index(n):
    out = gh(["pr", "diff", str(n)])
    return {path: parse_diff_lines(text) for path, text in split_files(out.stdout).items()}


def existing_comments(repo, n):
    """gh --paginate merges array pages into one array, so json.loads is enough."""
    out = gh(["api", f"repos/{repo}/pulls/{n}/comments", "--paginate"])
    return json.loads(out.stdout or "[]")


def read_body(source):
    if source in (None, "-"):
        return sys.stdin.read()
    return Path(source).read_text()


def load_items(args):
    """Normalise the input shapes into one list of comments to post."""
    if args.manifest:
        raw = json.loads(Path(args.manifest).read_text())
        return [
            {
                "path": item["file"],
                "line": item["line"],
                "body": item.get("body") or Path(item["body_file"]).read_text(),
            }
            for item in raw
        ]
    if args.general:
        return [{"path": None, "line": None, "body": read_body(args.body_file)}]
    path, _, line = args.target.rpartition(":")
    return [{"path": path, "line": int(line), "body": read_body(args.body_file)}]


def check_items(items, index, comments, allow_duplicate):
    """Resolve every anchor before anything is posted. Returns (ready, problems)."""
    ready, problems = [], []
    for item in items:
        if item["path"] is None:
            ready.append({**item, "anchor": None})
            continue
        diff_lines = index.get(item["path"])
        if diff_lines is None:
            problems.append(f"{item['path']}: not in this PR's diff")
            continue
        anchor = find_anchor(diff_lines, item["line"])
        if anchor is None:
            near = nearest_addressable(diff_lines, item["line"])
            near_text = ", ".join(str(n) for n in near) or "none in this file"
            problems.append(
                f"{item['path']}:{item['line']} is not in the diff; "
                f"addressable lines nearby: {near_text}"
            )
            continue
        dupes = find_duplicates(comments, item["path"], item["line"])
        if dupes and not allow_duplicate:
            problems.append(
                f"{item['path']}:{item['line']} already has a From Claude comment "
                f"({dupes[0]}); pass --allow-duplicate to post anyway"
            )
            continue
        ready.append({**item, "anchor": anchor})
    return ready, problems


def post_one(repo, n, item, sha):
    if item["anchor"] is None:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
            handle.write(ensure_marker(item["body"]))
            body_path = handle.name
        out = gh(["pr", "comment", str(n), "--body-file", body_path], check=False)
        return {"ok": out.returncode == 0, "landed": "general note",
                "detail": out.stdout.strip() or out.stderr.strip()}
    payload = {
        "body": ensure_marker(item["body"]),
        "commit_id": sha,
        "path": item["path"],
        "line": item["anchor"],
        "side": "RIGHT",
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(payload, handle)
        payload_path = handle.name
    out = gh(["api", f"repos/{repo}/pulls/{n}/comments", "-X", "POST",
              "--input", payload_path], check=False)
    landed = f"{item['path']}:{item['line']}"
    if out.returncode != 0:
        return {"ok": False, "landed": landed, "detail": out.stderr.strip()}
    resp = json.loads(out.stdout or "{}")
    return {"ok": bool(resp.get("id")), "landed": landed, "id": resp.get("id")}


def describe(item):
    return "general note" if item["path"] is None else f"{item['path']}:{item['line']}"


def main():
    parser = argparse.ArgumentParser(
        description="Post line-anchored review comments to a GitHub PR."
    )
    parser.add_argument("target", nargs="?", help="FILE:LINE anchor in the new file")
    parser.add_argument("--pr", type=int, help="PR number; inferred from the branch when omitted")
    parser.add_argument("--body-file", help="markdown body, or - for stdin")
    parser.add_argument("--manifest", help="JSON array of {file, line, body|body_file}")
    parser.add_argument("--general", action="store_true", help="post an unpositioned PR comment")
    parser.add_argument("--dry-run", action="store_true", help="print payloads only")
    parser.add_argument("--allow-duplicate", action="store_true",
                        help="post even when a From Claude comment already sits on that line")
    args = parser.parse_args()

    if not (args.manifest or args.general or args.target):
        parser.error("give a FILE:LINE target, --manifest, or --general")

    repo = owner_repo()
    n = resolve_pr(args.pr)
    items = load_items(args)
    sha = head_sha(n)
    index = diff_index(n)
    comments = existing_comments(repo, n)

    ready, problems = check_items(items, index, comments, args.allow_duplicate)
    for problem in problems:
        print(f"BLOCKED  {problem}", file=sys.stderr)
    if problems:
        raise SystemExit(f"{len(problems)} of {len(items)} anchors unusable; nothing posted")

    print(f"Posting {len(ready)} comment(s) to PR #{n}, each labeled From Claude:",
          file=sys.stderr)
    for item in ready:
        print(f"  {describe(item)}", file=sys.stderr)

    if args.dry_run:
        for item in ready:
            print(f"\n--- {describe(item)} ---\n{ensure_marker(item['body'])}")
        return 0

    failures = 0
    for item in ready:
        result = post_one(repo, n, item, sha)
        if result["ok"]:
            suffix = f"  id={result['id']}" if result.get("id") else ""
            print(f"OK       {result['landed']}{suffix}")
        else:
            failures += 1
            print(f"FAILED   {describe(item)}  {result.get('detail', '')}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

Then `chmod +x plugins/review-branch/scripts/gh_comment.py`.

- [ ] **Step 2: Write the pure-function tests**

`tests/posters/test_gh_comment.py`:

```python
# ABOUTME: tests for gh_comment pure functions (diff split/parse, anchors, marker, dedup)
# ABOUTME: no network and no real gh calls; only the pure helpers are exercised

import json

import gh_comment as gh

PR_DIFF = """diff --git a/api.py b/api.py
index 111..222 100644
--- a/api.py
+++ b/api.py
@@ -10,3 +10,4 @@ def handler():
 context line
-old line
+added one
+added two
 trailing
diff --git a/new.py b/new.py
new file mode 100644
index 000..333
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+brand new
+second line
"""


def test_split_files_keys_on_new_path():
    files = gh.split_files(PR_DIFF)
    assert set(files) == {"api.py", "new.py"}
    assert files["api.py"].startswith("@@ -10,3 +10,4 @@")


def test_parse_diff_lines_numbers_new_side():
    lines = gh.parse_diff_lines(gh.split_files(PR_DIFF)["api.py"])
    added = [e["new_line"] for e in lines if e["kind"] == "added"]
    assert added == [11, 12]


def test_find_anchor_added_and_context_hit_removed_miss():
    lines = gh.parse_diff_lines(gh.split_files(PR_DIFF)["api.py"])
    assert gh.find_anchor(lines, 11) == 11   # added
    assert gh.find_anchor(lines, 10) == 10   # context
    assert gh.find_anchor(lines, 999) is None


def test_nearest_addressable_orders_by_distance():
    lines = gh.parse_diff_lines(gh.split_files(PR_DIFF)["api.py"])
    assert gh.nearest_addressable(lines, 11, count=2) == [10, 12]


def test_ensure_marker_is_idempotent():
    once = gh.ensure_marker("hello")
    assert once.startswith("> **From Claude:**")
    assert gh.ensure_marker(once) == once


def test_find_duplicates_matches_marker_path_line():
    comments = [
        {"id": 1, "body": "> **From Claude:** x", "path": "api.py", "line": 11},
        {"id": 2, "body": "human", "path": "api.py", "line": 11},
        {"id": 3, "body": "> **From Claude:** y", "path": "api.py", "line": 99},
    ]
    assert gh.find_duplicates(comments, "api.py", 11) == [1]


def test_load_items_reads_manifest(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"file": "api.py", "line": 11, "body": "hi"}]))
    args = type("A", (), {"manifest": str(manifest), "general": False, "target": None})()
    assert gh.load_items(args) == [{"path": "api.py", "line": 11, "body": "hi"}]
```

- [ ] **Step 3: Run the tests**

Run: `just test`
Expected: gh tests pass with the rest.

- [ ] **Step 4: Commit**

```bash
git add plugins/review-branch/scripts/gh_comment.py tests/posters/test_gh_comment.py
git commit -m "Add gh-comment poster for GitHub pull requests"
```

### Task 4: gh-comment skill

**Files:**
- Create: `plugins/review-branch/skills/gh-comment/SKILL.md`

**Interfaces:**
- Consumes: `gh-comment` on PATH (installed by `review-branch install`).
- Produces: the `gh-comment` skill (invocable as `/gh-comment`).

- [ ] **Step 1: Write the skill**

Write `plugins/review-branch/skills/gh-comment/SKILL.md`, mirroring the glab-comment skill with GitHub specifics:

````markdown
---
name: gh-comment
description: Post line-anchored review comments to a GitHub pull request. Use ONLY when the user explicitly asks to post a specific comment or set of comments. Never invoke on your own initiative; default to drafting the comment and showing it instead. Handles head-SHA lookup, anchor validation, duplicate detection, and the From Claude attribution marker. Pairs with review-branch: post the comments you marked in the tracker.
allowed-tools: Bash(gh-comment:*)
---

# gh-comment

Posts comments to a GitHub PR under the user's account. GitHub only.

## Before you post

- The user must have asked for this specific post. Drafting is the default; posting is the exception.
- One ask authorizes one post. "Post 4, 5, and 12" does not authorize posting 13 later. Ask again.
- Never resolve, approve, request changes, merge, or close. This tool posts comments and nothing else.
- If the ask is ambiguous, or a note reads as a question rather than an edit instruction, write the draft and show it, or raise the question first.

## Usage

```sh
gh-comment src/api.py:141 --body-file draft.md       # one comment, PR from branch
gh-comment --pr 42 src/api.py:141 --body-file -      # explicit PR, body on stdin
gh-comment --pr 42 --manifest findings.json          # batch, the review-pass case
gh-comment --pr 42 --general --body-file summary.md  # unpositioned PR comment
gh-comment --pr 42 --manifest findings.json --dry-run # print payloads, post nothing
```

Manifest is a JSON array of `{"file": ..., "line": ..., "body_file": ...}`, or `body` for
inline text; it is exactly what `review-branch manifest <round-dir>` emits. Run `--dry-run`
first on any batch.

`FILE:LINE` is a line number in the **new** file (the RIGHT side of the diff). A comment can
only land on a line the PR diff adds or keeps as context. If the line is not addressable the
script refuses, names the closest addressable lines, and posts nothing.

## Writing the comment

One finding per comment. Lead with the claim; name the failure as input to wrong result;
do not restate what the code does; suggest a fix only if it fits on one line; if unsure,
ask rather than assert. (Same guidance as glab-comment.)

## What it does for you

Every body posts with the marker on its own line, then a blank line, then your comment:

```markdown
> **From Claude:**

The list path gates its envelope; the detail path has no equivalent.
```

The comment posts under the user's account, so that label is the only thing separating
Claude's voice from theirs. Keep it bare.

It re-reads the PR head SHA and diff on every run, validates each anchor before posting any
of them, and refuses a line that already carries a From Claude review comment. A POST that
looks like it failed may have landed, so never retry by hand; re-run and let the duplicate
check decide.

## Limits

- Anchors target new-file (RIGHT-side) lines. Commenting on a removed line is not exposed.
- No multi-line comments, no replies into an existing review thread.
- No editing or deleting. Fix a bad comment in the GitHub UI.
- Consider a repo guard (e.g. a veer rule) blocking a raw `gh api ... /comments -X POST` or
  `gh pr review`, so the marker, the anchor check, and the duplicate check cannot be bypassed.
````

- [ ] **Step 2: Verify no personal references, no em-dashes**

Run: `grep -niE "ted|—" plugins/review-branch/skills/gh-comment/SKILL.md`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add plugins/review-branch/skills/gh-comment/
git commit -m "Add gh-comment skill"
```

---

## Group C: worktree script

### Task 5: Build worktree_tool.py

**Files:**
- Create: `plugins/worktree/scripts/worktree_tool.py`
- Create: `tests/worktree/conftest.py`
- Create: `tests/worktree/test_worktree_tool.py`

**Interfaces:**
- Produces (pure/testable): `slug_dir(branch) -> str` (slashes to dashes), `env_files_to_copy(gitignored_paths) -> list[str]` (keep `.env`, `.env.*`, `.envrc`; drop the rest), `load_hooks(repo_root) -> dict` (parse optional `.worktree.toml` into `{"copy": [...], "symlink": [...], "command": [...]}`), `resolve_branch(arg, vcs) -> str`. CLI `main()` prints the created worktree path.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write the failing tests**

`tests/worktree/conftest.py`:

```python
# ABOUTME: pytest path setup for the worktree plugin script
# ABOUTME: makes plugins/worktree/scripts importable as worktree_tool

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "worktree" / "scripts"),
)
```

`tests/worktree/test_worktree_tool.py`:

```python
# ABOUTME: tests for worktree_tool pure helpers (slug, env-file filter, hook parsing)
# ABOUTME: no git side effects; only the pure functions are exercised

import worktree_tool as wt


def test_slug_dir_replaces_slashes():
    assert wt.slug_dir("feature/auth-fix") == "feature-auth-fix"
    assert wt.slug_dir("main") == "main"


def test_env_files_to_copy_keeps_only_env_and_envrc():
    given = [".env", ".env.local", ".envrc", ".venv/x", "node_modules/y",
             ".DS_Store", "build/z", "notes.txt"]
    assert wt.env_files_to_copy(given) == [".env", ".env.local", ".envrc"]


def test_load_hooks_absent_file_yields_empty(tmp_path):
    hooks = wt.load_hooks(tmp_path)
    assert hooks == {"copy": [], "symlink": [], "command": []}


def test_load_hooks_parses_worktree_toml(tmp_path):
    (tmp_path / ".worktree.toml").write_text(
        '[[copy]]\nfrom = ".env"\nto = ".env"\n\n'
        '[[symlink]]\nfrom = ".bin"\nto = ".bin"\n\n'
        '[[command]]\nrun = "uv sync"\n'
    )
    hooks = wt.load_hooks(tmp_path)
    assert hooks["copy"] == [{"from": ".env", "to": ".env"}]
    assert hooks["symlink"] == [{"from": ".bin", "to": ".bin"}]
    assert hooks["command"] == [{"run": "uv sync"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `just test`
Expected: FAIL with `ModuleNotFoundError: No module named 'worktree_tool'`.

- [ ] **Step 3: Implement worktree_tool.py**

Create `plugins/worktree/scripts/worktree_tool.py` (uv shebang, two `ABOUTME:` lines, stdlib only incl. `tomllib`). Full content:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///

# ABOUTME: creates a git worktree under .claude/worktrees and bootstraps it
# ABOUTME: copies gitignored env files, runs direnv/lockfile setup, applies .worktree.toml hooks

import argparse
import fnmatch
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ENV_GLOBS = (".env", ".env.*", ".envrc")


def run(cwd, *args, check=True, capture=True):
    out = subprocess.run(list(args), cwd=str(cwd), text=True,
                         capture_output=capture, check=False)
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
            import json
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
    out = run(repo_root, "direnv", "status", check=False)
    return "Found RC allowed true" in out.stdout


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
```

Then `chmod +x plugins/worktree/scripts/worktree_tool.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `just test`
Expected: the four worktree tests pass.

- [ ] **Step 5: Commit**

```bash
git add plugins/worktree/scripts/worktree_tool.py tests/worktree/
git commit -m "Add worktree creation script with optional .worktree.toml hooks"
```

### Task 6: Shrink the worktree skill to drive the script

**Files:**
- Rewrite: `plugins/worktree/skills/worktree/SKILL.md`

**Interfaces:**
- Consumes: `plugins/worktree/scripts/worktree_tool.py` (Task 5) via `${CLAUDE_PLUGIN_ROOT}/scripts/worktree_tool.py`; the `EnterWorktree` tool.

- [ ] **Step 1: Rewrite the skill**

Replace `plugins/worktree/skills/worktree/SKILL.md` with a version that delegates to the script. Full content:

````markdown
---
name: worktree
description: Create a git worktree for reviewing an MR/PR or working on a branch in isolation. Use when the user wants to review a merge request or pull request, check out a branch in a separate worktree, or uses /worktree. Accepts an MR/PR number, an MR/PR URL, or a branch name. Runs the worktree_tool script (creates the worktree under .claude/worktrees/, copies gitignored env files, bootstraps, applies optional .worktree.toml hooks), then switches the session into it.
allowed-tools: Bash(*worktree_tool.py *), Bash(git *), Read
---

# Worktree

Create an isolated git worktree and switch the session into it. The heavy lifting is a
standalone script; this skill runs it and enters the result.

## Workflow

1. **Run the script** from the repo root, passing the target (MR/PR number, MR/PR URL, or
   branch name; omit for the current branch):

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/scripts/worktree_tool.py" <target>
   ```

   It resolves the branch, creates the worktree under `.claude/worktrees/<slug>`, copies
   gitignored `.env*`/`.envrc` from the main worktree, bootstraps (direnv when an `.envrc`
   was allowed in the parent, else uv/bun/pnpm/npm by lockfile), applies any
   `.worktree.toml` hooks, and prints the worktree path on stdout with a summary on stderr.

2. **Enter it.** Call the `EnterWorktree` tool (not a Bash command) with `path` set to the
   printed worktree path, so subsequent commands run inside it.

3. **Report** the path and the one-line summary the script emitted.

## Optional per-repo hooks

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

`copy` and `symlink` sources are relative to the main worktree; `command` runs inside the
new worktree. Do not put destructive setup (migrations, resets) in a `command` hook without
the user's say-so.

## Cleanup

When the user is done:

1. `EnterWorktree` with `action: "keep"` to return to the original directory (or just
   `cd` back).
2. `git worktree remove .claude/worktrees/<slug>`
3. If the script created a brand-new local branch (target did not exist anywhere), delete it
   with `git branch -d <branch>` when no longer needed.

## Rules

- The worktree directory is always under `.claude/worktrees/` relative to the repo root.
- Only gitignored `.env*`/`.envrc` are copied. Tracked files are already in the checkout.
- Do not run database migrations or destructive setup without asking.
````

- [ ] **Step 2: Verify no em-dashes**

Run: `grep -n "—" plugins/worktree/skills/worktree/SKILL.md`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add plugins/worktree/skills/worktree/SKILL.md
git commit -m "Shrink worktree skill to drive the worktree_tool script"
```

---

## Group D: wiring and local versioning

### Task 7: Reflect the live posting path in review-branch docs; verify install

**Files:**
- Modify: `plugins/review-branch/skills/review-branch/SKILL.md`
- Modify: `plugins/review-branch/README.md`

**Interfaces:**
- Consumes: `glab_comment.py` / `gh_comment.py` (Tasks 1, 3) present in `plugins/review-branch/scripts/`, which `review_tool.py`'s `INSTALL_MAP` already maps to `glab-comment` / `gh-comment` on PATH.

- [ ] **Step 1: Verify install now places all three scripts**

Run:

```bash
REVIEW_BRANCH_BIN=$(mktemp -d) plugins/review-branch/scripts/review_tool.py install
```

Expected: three `installed ...` lines (`review-branch`, `glab-comment`, `gh-comment`) and NO `skipped` lines. (Before this plan, the two comment scripts printed as skipped.)

- [ ] **Step 2: Update SKILL.md posting wording**

In `plugins/review-branch/skills/review-branch/SKILL.md`, find the collaboration-loop bullet that routes posting through the comment skills and the Step 0 bootstrap. Ensure the text states plainly that `review-branch install` provides `glab-comment` and `gh-comment` on PATH and that "post the checked ones" runs the matching skill on the `review-branch manifest` output. If any wording still hedges that the comment skills are forthcoming or not yet installed, remove that hedge. Do not add UI/keyboard prose (agent-facing doc stays lean). Keep the hard rule that nothing auto-posts and posting needs an explicit ask.

- [ ] **Step 3: Update README**

In `plugins/review-branch/README.md`, update the install section: `review-branch install` now installs `review-branch`, `glab-comment`, and `gh-comment` to `~/.local/bin` (it no longer reports the comment scripts as skipped). In the design-notes / posting description, state that a checked comment posts via `glab-comment` (GitLab) or `gh-comment` (GitHub), chosen by the remote, only when explicitly asked. Keep the human-facing keyboard/collapse notes that already live here.

- [ ] **Step 4: Verify and commit**

```bash
grep -niE "skip|forthcoming|not yet|—" plugins/review-branch/README.md plugins/review-branch/skills/review-branch/SKILL.md
just test
git add plugins/review-branch/README.md plugins/review-branch/skills/review-branch/SKILL.md
git commit -m "Document the live posting path in review-branch"
```

Expected: the grep shows no stale "skipped/forthcoming/not yet" posting wording and no em-dashes; `just test` green.

### Task 8: Sync marketplace and bump the worktree plugin version (local only)

**Files:**
- Modify: `plugins/worktree/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json` (regenerated by `just sync`)

**Interfaces:**
- Consumes: all prior tasks.

- [ ] **Step 1: Bump worktree version and mention the script in its description**

Edit `plugins/worktree/.claude-plugin/plugin.json`: set `version` from `0.1.0` to `0.2.0`, and append to the description that it now runs a standalone `worktree_tool` script with optional `.worktree.toml` hooks. Leave `review-branch`'s version at `0.2.0` (the in-progress, not-yet-released version now gains the posting skills). Do NOT edit any other plugin.

- [ ] **Step 2: Sync and verify**

```bash
just sync
just check
just test
```

Expected: `just check` prints `All good.` (marketplace regenerated and consistent); `just test` green.

- [ ] **Step 3: Commit (do NOT push, do NOT tag)**

```bash
git add plugins/worktree/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "Bump worktree to 0.2.0 and sync marketplace"
```

This plan ends with everything committed locally on the `comment-posters` branch. Merging to
main, tagging (`just bump`), and pushing are deliberately out of scope and remain manual,
per the release hold.

---

## Execution notes

- Tasks are ordered but Groups A/B/C are largely independent; if executed out of order, each
  still leaves `just test` green.
- Deliberate duplication: the pure diff/marker helpers appear in both poster scripts so each
  stays a standalone single-file uv script (copyable to the PATH by `review-branch install`).
  This is the same single-file tradeoff already chosen for `review_tool.py`; a reviewer
  should treat it as intended, not a DRY defect.
- No network in tests: the poster and worktree suites exercise only pure functions. The real
  `glab`/`gh`/`git` integration is verified by hand against a throwaway MR/PR/branch, not in
  `just test`.
- Release stays held: no `just bump`, no tag, no push anywhere in this plan.



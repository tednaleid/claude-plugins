# review-branch Volume, Bugs, and Contract Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut review-branch's finding volume by moving low/info to a terse `[[minor]]` list under a strict lens bar, and fix four field-report bugs plus five contract clarifications.

**Architecture:** Two script changes carry real logic and tests - `scripts/review_tool.py` (render the new `[[minor]]` table and a minor-aware summary; render the `also` multi-site list) and `scripts/glab_comment.py` (backfill collapsed diffs from `/changes`). The rest are prose edits to the skill and lens contract, verified by reading. Severity routing (high/med to `[[findings]]`, low/info to `[[minor]]`) is agent behavior driven by `SKILL.md`, not code; the renderer just displays whatever `review.toml` contains.

**Tech Stack:** Python 3.12 single-file `uv` scripts (stdlib + `markdown-it-py`), pytest, TOML (`tomllib`), the GitLab/GitHub CLIs (`glab`/`gh`). Tests run under `just test` (browser-free).

## Global Constraints

- Prose (skill, contract, docs, comments): no em-dashes, no emojis, single hyphens only.
- The HTML renderer escapes every non-prose value with `esc()` and renders prose only through `md_html()` (MarkdownIt `commonmark`, `{"html": False}`). Never pre-escape; never emit unescaped user content.
- `[[findings]]` carries only `high`/`med`. `[[minor]]` carries `low`/`info`, has no severity/draft/anchor/Post toggle, and is NOT append-only (may be promoted or removed).
- The lens bar is unconditional: no `--thorough` knob, no `confidence` field.
- `glab_api(path, paginate=True)` returns a flattened list; a single-value response returns that object. `/changes` must be called WITHOUT `paginate` and read from `.changes`.
- `main_worktree()` already resolves the repo via `git rev-parse --git-common-dir`; do not add new resolution logic for `init`.
- Run tests with: `uv run --python 3.12 --with pytest --with markdown-it-py pytest tests --ignore=tests/ui -q` (or `just test`). Poster tests need no extra deps.
- Commit after each task. Never use `--no-verify`.

---

## File Structure

- `plugins/review-branch/scripts/glab_comment.py` - GitLab poster. Task 1 edits `diff_index`.
- `plugins/review-branch/scripts/review_tool.py` - review store + renderer. Task 3 adds `minor_html`, changes `summary_cards`, edits `finding_card` and `compose`.
- `plugins/review-branch/skills/review-branch/references/data-format.md` - schema doc. Tasks 3 and 5 document `[[minor]]`, `also`, `head_sha`/`merge_base`.
- `plugins/review-branch/skills/review-branch/references/agent-contract.md` - lens output contract. Task 4 rewrites the bar, the prior-comments rule, and adds `also`.
- `plugins/review-branch/agents/lens-coverage.md` - coverage lens prompt. Task 4 adds the mutation-testing technique.
- `plugins/review-branch/skills/review-branch/SKILL.md` - orchestration. Tasks 2 and 5 edit Steps 3-10 and the rules block.
- Tests: `tests/posters/test_glab_comment.py` (Task 1), `tests/review_branch/test_init.py` (Task 2), `tests/review_branch/test_compose.py` + `test_render.py` (Task 3).

Task order: 1 and 2 are independent bug fixes; 3 is the render code the volume change needs; 4 and 5 are prose that reference the `[[minor]]`/`also` shapes defined in 3. Do them in order.

---

## Task 1: glab-comment backfills collapsed diffs (A3)

**Files:**
- Modify: `plugins/review-branch/scripts/glab_comment.py:206-215` (`diff_index`)
- Test: `tests/posters/test_glab_comment.py`

**Interfaces:**
- Consumes: `glab_api(path, method="GET", input_file=None, paginate=False)` (returns a flattened list when paginated, or the single decoded object), `parse_diff_lines(diff_text)`.
- Produces: `diff_index(iid)` unchanged signature, returning `{new_path: {"lines": [...], "old_path": str|None}}`, now with collapsed files backfilled.

- [ ] **Step 1: Write the failing tests**

Add to `tests/posters/test_glab_comment.py`:

```python
import pytest


def test_diff_index_backfills_collapsed_files_from_changes(monkeypatch):
    diffs_page = [
        {"new_path": "small.py", "old_path": "small.py", "new_file": False,
         "diff": "@@ -1,1 +1,2 @@\n context\n+added\n", "collapsed": False},
        {"new_path": "big.md", "old_path": "big.md", "new_file": True,
         "diff": "", "collapsed": True},
    ]
    changes = {"changes": [
        {"new_path": "big.md", "diff": "@@ -0,0 +1,2 @@\n+line one\n+line two\n"},
    ], "overflow": False}

    def fake_api(path, **kw):
        if "/diffs" in path:
            return diffs_page
        if "/changes" in path:
            return changes
        raise AssertionError(f"unexpected api path: {path}")

    monkeypatch.setattr(gc, "glab_api", fake_api)
    index = gc.diff_index(7)
    assert index["small.py"]["lines"], "primary diff kept"
    assert index["big.md"]["lines"], "collapsed file backfilled from /changes"


def test_diff_index_fails_when_overflow_leaves_paths_unmapped(monkeypatch):
    diffs_page = [{"new_path": "big.md", "old_path": "big.md", "new_file": True,
                   "diff": "", "collapsed": True}]
    changes = {"changes": [], "overflow": True}

    def fake_api(path, **kw):
        return diffs_page if "/diffs" in path else changes

    monkeypatch.setattr(gc, "glab_api", fake_api)
    with pytest.raises(SystemExit):
        gc.diff_index(7)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest tests/posters/test_glab_comment.py -q`
Expected: FAIL - the current `diff_index` never calls `/changes`, so `big.md` has an empty line map (first test fails), and it never raises on overflow (second test fails).

- [ ] **Step 3: Implement the backfill**

Replace `diff_index` (`glab_comment.py:206-215`) with:

```python
def diff_index(iid):
    """Map each changed path to its parsed diff lines and its old path.

    Files GitLab collapsed (over its per-file diff-size limit) return an empty
    diff on /diffs; their text is only available from /changes with
    access_raw_diffs, so backfill just those, and fail loudly if an overflowed
    /changes still leaves paths unaddressable.
    """
    index = {}
    collapsed = []
    for entry in glab_api(f"projects/:id/merge_requests/{iid}/diffs", paginate=True):
        old_path = None if entry.get("new_file") else entry.get("old_path")
        diff = entry.get("diff", "")
        if not diff and entry.get("collapsed"):
            collapsed.append(entry["new_path"])
        index[entry["new_path"]] = {
            "lines": parse_diff_lines(diff),
            "old_path": old_path,
        }
    if collapsed:
        raw = glab_api(
            f"projects/:id/merge_requests/{iid}/changes?access_raw_diffs=true"
        )
        backfilled = []
        for entry in raw.get("changes", []):
            path = entry["new_path"]
            if path in collapsed and entry.get("diff"):
                index[path]["lines"] = parse_diff_lines(entry["diff"])
                backfilled.append(path)
        if backfilled:
            print(f"backfilled collapsed diffs from /changes: {', '.join(backfilled)}",
                  file=sys.stderr)
        missing = [p for p in collapsed if p not in backfilled]
        if missing:
            names = ", ".join(missing)
            if raw.get("overflow"):
                raise SystemExit(f"/changes overflowed; unaddressable files: {names}")
            print(f"warning: no diff available for: {names}", file=sys.stderr)
    return index
```

(`sys` is already imported in this file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --python 3.12 --with pytest pytest tests/posters/test_glab_comment.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/review-branch/scripts/glab_comment.py tests/posters/test_glab_comment.py
git commit -m "Backfill collapsed GitLab diffs from /changes in glab-comment"
```

---

## Task 2: init works from a worktree - regression test + doc fix (A4)

The tool already resolves the main repo via `main_worktree()` -> `git rev-parse --git-common-dir`, so `init` produces a stable repo-id from inside a worktree. This task locks that in with a test and removes the misleading "run from the main repo" instruction in the skill.

**Files:**
- Test: `tests/review_branch/test_init.py`
- Modify: `plugins/review-branch/skills/review-branch/SKILL.md:85-90` (Step 3 wording)

**Interfaces:**
- Consumes: `review_tool.cmd_init(slug, repo_dir) -> Path`, `review_tool.repo_id(repo_dir) -> str`.

- [ ] **Step 1: Write the failing test**

Add to `tests/review_branch/test_init.py` (uses the same `REVIEW_BRANCH_HOME` env the `env` fixture sets; build a real repo + worktree):

```python
import subprocess


def test_init_from_worktree_matches_main_repo(env, tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        subprocess.run(["git", "-C", str(repo), "config", k, v], check=True)
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    wt = repo / ".claude" / "worktrees" / "feature-x"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "-b",
                    "feature/x", str(wt)], check=True)

    from review_tool import repo_id, cmd_init
    assert repo_id(wt) == repo_id(repo)
    round_from_wt = cmd_init("myslug", wt)
    assert round_from_wt.name == "round-1"
    assert repo_id(repo) in str(round_from_wt)
```

- [ ] **Step 2: Run the test**

Run: `uv run --python 3.12 --with pytest --with markdown-it-py pytest tests/review_branch/test_init.py -q`
Expected: PASS immediately - this behavior already works; the test is a regression guard. (If it fails, `repo_id`/`main_worktree` regressed; fix them, do not weaken the test.)

- [ ] **Step 3: Fix the misleading skill wording**

In `SKILL.md` Step 3, replace lines 85-90:

```markdown
Create the round directory (run from the main repo, before entering the
worktree) and capture its absolute path:

```bash
REVIEW_DIR=$(review-branch init --slug <slug>)
```
```

with:

```markdown
Create the round directory and capture its absolute path. `init` resolves the
main repo via `git --git-common-dir`, so it works from the main repo or from
inside a worktree:

```bash
REVIEW_DIR=$(review-branch init --slug <slug>)
```
```

- [ ] **Step 4: Verify the doc reads correctly**

Read `SKILL.md` Step 3 and confirm it no longer instructs running only from the main repo.

- [ ] **Step 5: Commit**

```bash
git add tests/review_branch/test_init.py plugins/review-branch/skills/review-branch/SKILL.md
git commit -m "Test init from a worktree and correct the run-location note"
```

---

## Task 3: render the `[[minor]]` table, minor-aware summary, and `also` list (C-render + B1-render)

**Files:**
- Modify: `plugins/review-branch/scripts/review_tool.py` (`summary_cards:251`, `finding_card:301`, `compose:867`; add `minor_html`)
- Modify: `plugins/review-branch/skills/review-branch/references/data-format.md`
- Test: `tests/review_branch/test_compose.py`, `tests/review_branch/test_render.py:194`

**Interfaces:**
- Consumes: `esc(s)`, `md_html(text)`, `merged_findings(review, state)`, `TEMPLATE`.
- Produces: `minor_html(minor: list[dict]) -> str`; `summary_cards(findings: list[dict], minor_count: int) -> str` (new second arg); `finding_card` renders an optional `also` list. `review.toml` gains `[[minor]]` rows (`lens`, `file`, `line`, `note`) and findings gain optional `also = ["path:line", ...]`.

- [ ] **Step 1: Write failing tests**

Add to `tests/review_branch/test_compose.py`:

```python
def test_minor_notes_render_in_collapsed_section_without_post_toggle():
    review = {
        "review": {"title": "t"},
        "findings": [],
        "minor": [
            {"lens": "naming", "file": "a.py", "line": "12", "note": "shadowed `x`"},
        ],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    assert "<details" in page and "Minor notes (1)" in page
    assert "a.py:12" in page and "shadowed" in page
    # the minor block itself carries no finding controls
    start = page.index('<details class="minor"')
    block = page[start:page.index("</details>", start)]
    assert "data-fid" not in block and "post-chk" not in block


def test_summary_counts_minor_separately_from_findings():
    review = {
        "review": {"title": "t"},
        "findings": [{"id": "f1", "severity": "high", "title": "boom", "file": "a.py"}],
        "minor": [{"lens": "naming", "file": "a.py", "note": "n1"},
                  {"lens": "coverage", "file": "b.py", "note": "n2"}],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    assert '<div class="num low">2</div>' in page  # the Minor notes card shows 2


def test_finding_also_list_renders_extra_sites():
    review = {
        "review": {"title": "t"},
        "findings": [{"id": "f1", "severity": "high", "title": "log interp",
                      "file": "postgres.py", "lines": "110",
                      "also": ["memory.py:79", "omni_projects.py:201"]}],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    assert "memory.py:79" in page and "omni_projects.py:201" in page
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --python 3.12 --with pytest --with markdown-it-py pytest tests/review_branch/test_compose.py -q`
Expected: FAIL - no minor rendering, `summary_cards` takes one arg, no `also` rendering.

- [ ] **Step 3: Add `minor_html` and update `summary_cards`**

After `summary_cards` (ends at `review_tool.py:262`), add:

```python
def minor_html(minor: list[dict]) -> str:
    if not minor:
        return ""
    rows = []
    for m in minor:
        loc = f'{m.get("file", "")}:{m["line"]}' if m.get("line") else m.get("file", "")
        rows.append(
            "<tr>"
            f'<td>{esc(m.get("lens", ""))}</td>'
            f"<td><code>{esc(loc)}</code></td>"
            f"<td>{md_html(m.get('note', ''))}</td>"
            "</tr>"
        )
    head = "<tr><th>Lens</th><th>Location</th><th>Note</th></tr>"
    body = "\n".join(rows)
    return (
        f'<details class="minor"><summary>Minor notes ({len(minor)})</summary>\n'
        f"<table>\n{head}\n{body}\n</table>\n</details>"
    )
```

Replace `summary_cards` (`review_tool.py:251-262`) with:

```python
def summary_cards(findings: list[dict], minor_count: int = 0) -> str:
    counts: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1
    cards = []
    for sev, name in (("high", "High"), ("med", "Medium")):
        cards.append(
            f'<div class="card"><div class="num {sev}">{counts.get(sev, 0)}</div>'
            f'<div class="label">{name}</div></div>'
        )
    cards.append(
        f'<div class="card"><div class="num low">{minor_count}</div>'
        f'<div class="label">Minor notes</div></div>'
    )
    return "\n".join(cards)
```

- [ ] **Step 4: Render `also` in `finding_card` and wire `compose`**

In `finding_card` (`review_tool.py:301`), after the `file_html` line (currently line 308), build an optional also block:

```python
    also = f.get("also") or []
    also_html = (
        f'<div class="also">also: '
        + ", ".join(f"<code>{esc(a)}</code>" for a in also)
        + "</div>"
    ) if also else ""
```

Then in the `parts` list, insert `also_html` right after the `<div class="file">...</div>` entry:

```python
        f'<div class="file">{file_html}</div>',
        also_html,
```

(Empty-string parts are dropped when `compose` joins; `finding_card` returns its own string, so guard the join: change the final `return "\n".join(parts)` to `return "\n".join(p for p in parts if p)`.)

In `compose` (`review_tool.py:867`), compute the minor list and pass it through. After `findings = merged_findings(review, state)` add:

```python
    minor = review.get("minor", [])
```

Change the summary replacement to `summary_cards(findings, len(minor))`, and append the minor section to `content` after the `files_touched` table block:

```python
    content.append(minor_html(minor))
```

- [ ] **Step 5: Update the existing summary test**

`tests/review_branch/test_render.py:194` (`test_summary_shows_med_zero_hides_low_zero`) asserts the old four-card behavior. Update it to the new shape: High and Medium cards always present, a Minor notes card always present, and no separate Low/Out-of-scope cards. Read the test, then rewrite its assertions to check for `Minor notes` and the absence of `Low / nits`/`Out-of-scope flags` labels.

- [ ] **Step 6: Document the schema**

In `data-format.md`, after the `[[files_touched]]` block, add:

```markdown
    [[minor]]                 # optional; low/info observations, terse and unpostable
    lens = "naming"           # the single lens that raised it
    file = "runner/api.py"
    line = "88"               # optional; single line or range
    note = "..."              # one-sentence markdown; the nit itself
```

And in the `[[findings]]` block, add under `lines`:

```markdown
    also = ["memory.py:79", "omni_projects.py:201"]  # optional extra sites of the same issue
```

- [ ] **Step 7: Run the full review-branch suite**

Run: `uv run --python 3.12 --with pytest --with markdown-it-py pytest tests/review_branch -q`
Expected: PASS (including the updated summary test).

- [ ] **Step 8: Commit**

```bash
git add plugins/review-branch/scripts/review_tool.py \
        plugins/review-branch/skills/review-branch/references/data-format.md \
        tests/review_branch/test_compose.py tests/review_branch/test_render.py
git commit -m "Render minor notes, minor-aware summary, and multi-site also list"
```

---

## Task 4: lens contract - strict bar, prior-comments rule, `also`, mutation testing (C-bar + B2 + B1-schema + B4)

Prose only; verified by reading. No unit tests.

**Files:**
- Modify: `plugins/review-branch/skills/review-branch/references/agent-contract.md`
- Modify: `plugins/review-branch/agents/lens-coverage.md`

- [ ] **Step 1: Replace the severity-calibration section with the strict bar**

In `agent-contract.md`, replace the "Severity calibration" section (lines 91-98) with:

```markdown
## What to surface (the bar)

Surface a finding only when you are confident it is real AND a competent author
would want to know. When you are unsure it matters, drop it. Do not manufacture
nits to fill the review - a noisy review trains the author to skip your findings.

- `high` / `med` are full findings with a draft comment.
- `low` / `info` are surfaced as terse one-line notes (no draft, no snippet):
  a real but minor footgun, an out-of-scope flag worth a mention. If it would
  not survive the bar above, do not report it at all.
- Do not tag `high` unless production behavior or security is at risk. Do not
  tag `med` for something you would be fine seeing in a follow-up MR.
```

- [ ] **Step 2: Reword the prior-comments rule**

In `agent-contract.md`, under "What you must NOT flag", replace the line:

```markdown
- Topics already addressed in `prior_comments_path` (read it before generating findings).
```

with:

```markdown
- A topic that prior discussion in `prior_comments_path` has **resolved** (read
  it first). A topic that is raised and still open is fair game, but add new
  evidence - a further trigger, a wider blast radius, or a correction - rather
  than repeating what is already on the thread.
```

- [ ] **Step 3: Add the `also` field to the schema**

In `agent-contract.md`, in the "Field rules" list (after the `line_range` rule), add:

```markdown
- **`also`** -- optional list of `"path:line"` strings for the same issue at
  other sites. Keep the primary site in `file`/`line_range`; list the rest here.
```

- [ ] **Step 4: Promote mutation testing in the coverage lens**

Read `agents/lens-coverage.md`, then add this paragraph to its guidance on finding gaps:

```markdown
To prove a branch is untested, add an assertion that would fail if the new code
were exercised, then run the suite (`just test`, else the project's runner). If
the suite still passes, the path is uncovered - report it with `reproduced: true`.
```

- [ ] **Step 5: Verify by reading**

Read both files end to end. Confirm: no occurrence of "generous" remains in `agent-contract.md`; the bar, the reworded prior-comments rule, the `also` field, and the coverage mutation-testing paragraph are all present; no em-dashes or emojis were introduced.

- [ ] **Step 6: Commit**

```bash
git add plugins/review-branch/skills/review-branch/references/agent-contract.md \
        plugins/review-branch/agents/lens-coverage.md
git commit -m "Rewrite lens bar strict, fix prior-comments rule, add also and mutation testing"
```

---

## Task 5: SKILL orchestration - diff extraction, lens dispatch, dedupe, routing, provenance (A1 + A2 + B3 + C-routing + B5 + B6)

Prose only; verified by reading. No unit tests. All edits are to `SKILL.md` plus one schema line in `data-format.md`.

**Files:**
- Modify: `plugins/review-branch/skills/review-branch/SKILL.md`
- Modify: `plugins/review-branch/skills/review-branch/references/data-format.md`

- [ ] **Step 1: A1 - build changed-files with git, and assert**

In `SKILL.md` Step 5, replace the diff block (lines 103-110) with:

```markdown
```bash
BASE=$(git merge-base "origin/<target-branch>" HEAD)
git diff "$BASE"...HEAD > .llm/diff.patch
grep '^diff --git' .llm/diff.patch | awk '{print $4}' | sed 's@^b/@@' \
  | sort -u > .llm/changed-files.txt
```

`glab mr diff` / `gh pr diff` emit a plain unified diff with no `diff --git`
headers, so parsing them yields an empty file list. The worktree is pinned to
the MR/PR head, so `git diff` produces real headers for glab, gh, and local
alike. Assert the extraction worked: if `.llm/diff.patch` is non-empty but
`.llm/changed-files.txt` is empty, stop and report rather than dispatching
lenses with no file list.
```

- [ ] **Step 2: B5 - record provenance in Step 3**

In `SKILL.md` Step 3, after capturing `REVIEW_DIR`, add:

```markdown
Record the commit provenance so a round is anchored to what it reviewed:

```bash
HEAD_SHA=$(git rev-parse HEAD)
MERGE_BASE=$(git merge-base "origin/<target-branch>" HEAD)
```

Write these into `[review]` as `head_sha` and `merge_base` in Step 7.
```

- [ ] **Step 3: A2 - pass absolute lens paths and validate keys**

In `SKILL.md` Step 6, replace the dispatch description (lines 144-153) with:

```markdown
Spawn all 4 lens subagents in a single message. Each prompt carries:
worktree_path, target_branch, diff_path, changed_files, prior_comments_path
(or `none`), hex_mode, hex_doc, spec_path, and - as ABSOLUTE paths built from
this skill's base directory (injected as `Base directory for this skill:` in the
prompt header) - `contract_path: <skill_base>/references/agent-contract.md` and
`lens_prompt_path: <skill_base>/agents/lens-<name>.md`. Do not rely on the
subagent resolving `references/...` relatively; one lens could not find its files
and returned wrong keys. Lenses: `review-branch:lens-architecture`,
`review-branch:lens-security`, `review-branch:lens-coverage`,
`review-branch:lens-naming`.

Validate each returned object against the contract schema. If the JSON is
malformed OR the keys do not match (e.g. `line` instead of `line_range`, a
missing `draft_comment`, an invented field), re-prompt that lens once with the
correct field list; if it still fails, log the lens as "no findings" and continue.
```

- [ ] **Step 4: B3 + C-routing - dedupe by topic and route by severity in Step 7**

In `SKILL.md` Step 7, replace the dedupe paragraph (lines 157-161) with:

```markdown
Dedupe by topic, not proximity: merge two findings only when their descriptions
name the same defect. Two findings that share a line but describe different
issues stay separate; nearness alone never merges. When merging, keep the
highest severity, the most specific description, concatenated distinct drafts,
and unioned lenses.

Route by severity. `high` and `med` become `[[findings]]` (with `comment`
drafts and `anchor`s). `low` and `info` become `[[minor]]` rows - one line each
(`lens`, `file`, `line`, `note`), no draft, no anchor. Sort findings by severity
(high, med), then file, then line; ids `f1`, `f2`, ... in final order.
```

- [ ] **Step 5: B5 posting-warn + record head_sha in the toml write**

In `SKILL.md` Step 7, in the "First `Write`" bullet (line 165-166), add `head_sha` and `merge_base` to the `[review]` table it describes:

```markdown
1. First `Write`: the `[review]` table (including `head_sha` and `merge_base`
   from Step 3), `[overall]`, and any `[[hex]]`, `[[coverage]]`,
   `[[files_touched]]`, `[[minor]]` rows.
```

In the "After the human reviews" section, in the "post the checked ones" bullet, add a staleness check:

```markdown
  Before building the manifest, compare the current MR/PR head to the round's
  `head_sha`; if it has moved, warn the human that anchors may have shifted and
  ask before posting.
```

- [ ] **Step 6: C - drop the no-threshold rule and B6 - document the status parse-check**

In `SKILL.md`, remove the rule at line 230:

```markdown
- **No confidence threshold.** Every lens finding lands in the tracker.
```

and replace it with:

```markdown
- **Surface by the bar, route by severity.** Lenses surface only what clears the
  contract's bar; high/med land in `[[findings]]`, low/info in `[[minor]]`.
```

In Step 7, after the batch-append instruction (line 168), add:

```markdown
Run `review-branch status "$REVIEW_DIR"` after each five-finding batch: it
parses the TOML and prints the merged view, so a syntax error surfaces while you
still know which batch caused it.
```

- [ ] **Step 7: Document head_sha/merge_base in data-format.md**

In `data-format.md`, in the `[review]` table, add after `files`:

```markdown
    head_sha = "41a8604f..."     # source HEAD the findings were produced against
    merge_base = "f7abf751..."   # merge-base with the target branch
```

- [ ] **Step 8: Verify by reading**

Read `SKILL.md` end to end. Confirm: Step 5 uses `git diff` with the assertion; Step 6 passes absolute paths and validates keys; Step 7 dedupes by topic and routes low/info to `[[minor]]`; the no-threshold rule is gone; provenance and the status parse-check are present. Confirm no em-dashes or emojis were introduced.

- [ ] **Step 9: Commit**

```bash
git add plugins/review-branch/skills/review-branch/SKILL.md \
        plugins/review-branch/skills/review-branch/references/data-format.md
git commit -m "Orchestrate strict routing, git diff extraction, absolute lens paths, provenance"
```

---

## Final verification

- [ ] Run `just test` - the full browser-free suite passes.
- [ ] Run `just check` - marketplace stays in sync (no plugin.json version change in this plan; version bump is a separate release decision).
- [ ] Grep the changed prose for em-dashes and emojis; there should be none.

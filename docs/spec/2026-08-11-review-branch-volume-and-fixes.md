# review-branch: finding volume, field-report bugs, and contract tweaks

Design spec for the first implementation pass responding to two field reports
(a round-2 review of GitLab MR !236, and a glab-comment failure on MR !231)
plus the maintainer's headline concern: reviews surface 20+ findings and the
low-priority tail is noise that is rarely posted and wasteful to assemble.

Round-2 / re-review support is the natural next feature but is explicitly out
of scope here; see "Deferred" at the end. This spec covers three buckets:

- **C - Volume:** shift the lenses from exhaustive capture to a strict bar, and
  demote whatever low/info survives into terse notes.
- **A - Bugs:** four mechanical correctness fixes.
- **B - Tweaks:** five small contract/prompt clarifications.

Affected component tree (all under `plugins/review-branch/`):

- `skills/review-branch/SKILL.md` - the orchestration
- `skills/review-branch/references/agent-contract.md` - the lens output contract
- `skills/review-branch/references/data-format.md` - the review.toml schema doc
- `agents/lens-*.md` - the four lens prompts
- `scripts/review_tool.py` - init, render, manifest, the HTML template
- `scripts/glab_comment.py` - the GitLab poster

---

## Bucket C - Finding volume

### Problem

The design deliberately maximizes volume. `agent-contract.md` line 97 says
"`low` and `info` are fine to be generous with -- the human checks them off,"
and `SKILL.md` line 230 says "No confidence threshold. Every lens finding lands
in the tracker." A 26-file MR produced 30 findings (1 high / 6 med / 19 low /
4 info). The 23 low/info entries cost tokens to find, draft, dedupe, and render,
and are almost never posted.

### Design

Two levers that compose: a strict bar at the source cuts how many low/info are
generated at all; demotion makes the survivors cheap.

**1. Strict bar in the contract (source-level suppression).**

Rewrite `agent-contract.md`:

- Replace the "Severity calibration" section's "`low` and `info` are fine to be
  generous with" guidance with a strict bar: *surface a finding only when you
  are confident it is real AND a competent author would want to know. When you
  are unsure it matters, drop it. Do not manufacture nits to fill the review.*
- Keep the four-level `severity` scale - the lens still rates what it surfaces -
  but the scale no longer licenses generosity.
- The bar is unconditional: no per-run knob, no `confidence` field. (A tunable
  strictness knob and a self-rated confidence field were both considered and
  rejected - the knob as unneeded for the default workflow, the field as
  unreliable self-rating that adds schema surface the lenses have already
  tripped on.)

**2. Severity split (demote the survivors).**

The aggregator routes by severity:

- `high` / `med` -> full `[[findings]]` exactly as today (draft `comment`,
  `anchor`, `snippet`, Post toggle in the tracker).
- `low` / `info` -> terse `[[minor]]` notes: one line each, no draft, no anchor,
  no snippet, no Post toggle.

**3. Data - new `[[minor]]` table in `review.toml`.**

Modeled on the existing context tables (`[[coverage]]`, `[[hex]]`,
`[[files_touched]]`):

    [[minor]]
    lens = "naming"           # single lens that raised it
    file = "runner/api.py"
    line = "88"               # optional; single line or range
    note = "..."              # one-sentence markdown; the nit itself

The `[[findings]]` list therefore contains only `high`/`med` - the entries the
human actually dispositions.

**4. Render - `review_tool.py` HTML template.**

- Add a collapsed "Minor notes" section below the findings list: a plain list
  of `lens` - `file:line` - `note`, no Post checkboxes, no comment area.
- The per-severity summary line still counts all four levels, so the human sees
  "1 high / 6 med" up top and "23 minor" without scrolling.
- Promotion is on-demand only: to post a minor note the human asks ("post the
  note about X") and Claude promotes it to a full `[[findings]]` entry then
  (writing a `comment` and `anchor`). Minor notes are not append-only; a
  promoted note moves to `[[findings]]` and may be removed from `[[minor]]`.

**5. SKILL.md.**

- Drop the "No confidence threshold. Every lens finding lands in the tracker"
  rule (line 230).
- Step 7 (aggregate) routes `high`/`med` to `[[findings]]` and `low`/`info` to
  `[[minor]]`.

### Acceptance

- A review of a mixed-severity branch writes `high`/`med` as `[[findings]]` and
  `low`/`info` as `[[minor]]`, and the rendered page shows the minor section
  collapsed with no Post toggles.
- The lens prompts contain the strict-bar language and no longer contain
  "generous."

---

## Bucket A - Bugs

### A1. Changed-files extraction silently empties on GitLab

`SKILL.md` Step 5 (lines 105-110) runs `glab mr diff <n>` and greps for
`^diff --git` headers. `glab mr diff` emits a plain unified diff with no
`diff --git` headers, so `changed-files.txt` is created empty and no error
fires; every lens then receives an empty `changed_files` list.

**Fix.** In the worktree (already pinned to the MR head), build the diff with
git so the headers are real and the command is identical across glab/gh/local:

    BASE=$(git merge-base "origin/<target-branch>" HEAD)
    git diff "$BASE"...HEAD > .llm/diff.patch
    grep '^diff --git' .llm/diff.patch | awk '{print $4}' | sed 's@^b/@@' \
      | sort -u > .llm/changed-files.txt

Add an assertion: if `.llm/diff.patch` is non-empty but `.llm/changed-files.txt`
is empty, stop and report rather than dispatching lenses with no file list.

**Acceptance.** On a GitLab MR, `changed-files.txt` lists every changed path;
an empty result against a non-empty diff halts the run.

### A2. A lens could not find its own reference files

One of four lenses reported it could not locate `references/agent-contract.md`
or `agents/lens-security.md`, and produced wrong field names (`line` for
`line_range`, `detail` for `description`), an invented `confidence` field, a
missing `draft_comment`, and absolute instead of repo-relative paths. The
returned JSON was well-formed, so today's malformed-JSON retry (Step 6) did not
catch it.

**Fix (two parts).**

- In each lens dispatch, pass the contract and lens-prompt locations as
  absolute paths built from the skill's injected base directory, rather than
  relying on the subagent to resolve `references/...` relatively:

      contract_path: <skill_base>/references/agent-contract.md
      lens_prompt_path: <skill_base>/agents/lens-<name>.md

- In Step 6 aggregation, validate each returned object's keys against the
  contract schema and re-prompt the lens once on a key mismatch (not only on
  malformed JSON).

**Acceptance.** A dispatched lens receives absolute, resolvable paths; a lens
that returns wrong keys is re-prompted once before its output is used.

### A3. glab-comment cannot anchor in collapsed-diff files

`scripts/glab_comment.py` `diff_index()` (around line 206) reads
`/merge_requests/:iid/diffs`. GitLab returns `collapsed: true` and `diff: ""`
for files over its per-file diff-size limit, so those files get an empty line
map and every anchor in them is rejected as "not in the diff." On MR !231, 4 of
13 files collapsed and held 14 of 35 commentable findings; the failure mode is
common on docs-heavy or generated-file MRs.

**Fix.** Keep `/diffs` as the paginated primary source; backfill only the
collapsed entries from `/changes?access_raw_diffs=true`:

- `/changes` is unpaginated and returns a single object; call it without
  `paginate` and read `.changes`. (`access_raw_diffs`/`unidiff` are ignored on
  `/diffs`; they only take effect on `/changes`.)
- If `/changes` reports `overflow: true` and paths are still unmapped, fail with
  a message naming those paths rather than leaving a silent empty map.
- Print on stderr which files needed the fallback, so a future change in
  GitLab's behavior is visible.

**Acceptance.** Against MR !231, an anchor inside a collapsed file
(`docs/module-development/backend-security-contract.md:222`) resolves under
`--dry-run` instead of printing `BLOCKED ... none in this file`.

### A4. `init` must run from the main repo

`review-branch init` resolves the repo from the current directory, which is
awkward when the session is already inside a worktree.

**Fix.** Resolve the main repository via `git rev-parse --git-common-dir` so
`init` works from inside a worktree. (A `--repo <path>` override is an optional
secondary path; the git-common-dir resolution is the primary fix.)

**Acceptance.** `review-branch init --slug <s>` run from inside a worktree
creates the round under the correct repo-id and prints its path.

---

## Bucket B - Contract and prompt tweaks

### B1. Multi-site findings (#3)

The contract has no shape for one issue spanning several files; a lens invented
a placeholder path. Add an optional `also` list to the finding schema:

    also = ["memory.py:79", "omni_projects.py:201"]

The primary site stays in `file`/`lines`; the renderer shows `also` as a small
list under the finding. Documented in `agent-contract.md` and `data-format.md`.

### B2. prior-comments rule conflates "discussed" with "settled" (#6)

`agent-contract.md` line 38 tells lenses not to flag "Topics already addressed
in `prior_comments_path`." In a re-review the prior thread contains both settled
topics and live, unfixed ones; obeying the rule literally drops a still-open
defect. Reword to:

> Do not restate a topic that prior discussion has **resolved**. A topic that is
> raised and still open is fair game, but add new evidence - a further trigger, a
> wider blast radius, or a correction - rather than repeating the thread.

### B3. Dedupe is proximity-first (#7)

`SKILL.md` Step 7 merges on "same file + line range within 5 lines + >= 50% word
overlap in title." Two genuinely different findings that share lines were saved
only by the weak title-overlap test. Invert the priority so **topic decides,
proximity only breaks ties**: merge two findings only when their descriptions
name the same defect; nearness alone never merges.

### B4. Promote mutation-testing in the coverage lens

The coverage lens's strongest findings came from dropping an assertion into the
branch and re-running the suite. Promote this from an implication to an explicit
suggestion in `agents/lens-coverage.md`:

> To prove a branch is untested, add an assertion that would fail if the new code
> were exercised, and run the suite; if it still passes, the path is uncovered.

### B5. Record provenance in `[review]` (#4)

Findings are line-anchored, so a round is only meaningful against a commit, and
the author may push while the review runs. Add to `[review]`:

    head_sha = "41a8604f..."     # source-branch HEAD the findings were produced against
    merge_base = "f7abf751..."   # merge-base with the target branch

`SKILL.md` records these in Step 3/7. At posting time the skill compares the
current MR/PR head to `head_sha` and warns the human if it has moved (anchors
may have shifted). This value also seeds the deferred round-2 work.

### B6. Documentation: `status` as a parse-check

Document in `SKILL.md` Step 7 that running `review-branch status "$REVIEW_DIR"`
after each five-finding append batch catches a TOML error while it is still
clear which batch caused it. No code change - this is the existing recommended
practice made explicit.

---

## Testing

- `scripts/review_tool.py`: unit-test the severity routing (a mixed-severity
  finding set produces the expected `[[findings]]` vs `[[minor]]` split) and the
  `[[minor]]` render (collapsed section, no Post inputs). Extend the Playwright
  suite only if the minor section adds interactive behavior; it should not.
- `scripts/glab_comment.py`: unit-test `diff_index` backfill with a fixture where
  one entry is `collapsed: true`/empty and `/changes` supplies its diff, plus the
  `overflow`-still-missing failure path.
- `init` git-common-dir resolution: a git-backed test that runs `init` from a
  worktree subdirectory and asserts the round lands under the main repo's repo-id.
- Prompt/contract changes (A2 paths, B1-B4, C bar) are text and are verified by
  reading the rendered dispatch, not by unit tests.

## Deferred (not in this spec)

Round-2 / re-review support (field report item #5): carrying the prior round,
auto-building the "already raised" block, a disposition table for prior findings,
and reusing an existing worktree at the MR head. It builds on the demotion shape
and on `head_sha`/`merge_base` from B5, and gets its own spec next.

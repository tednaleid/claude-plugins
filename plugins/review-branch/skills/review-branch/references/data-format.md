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

The data root is a git repo. Every write the tool itself performs (render, browser state saves) is auto-committed with messages shaped `<repo-id> <slug> round-N: <action>`. Writes made directly by the agent, such as review.toml edits, are swept into the next such commit; run `review-branch render` after editing review.toml so a comment rewrite lands in history.

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
    head_sha = "41a8604f..."     # source HEAD the findings were produced against
    merge_base = "f7abf751..."   # merge-base with the target branch
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
    also = ["memory.py:79", "omni_projects.py:201"]  # optional extra sites of the same issue
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

    [[minor]]                 # optional; low/info observations, terse and unpostable
    lens = "naming"           # the single lens that raised it
    file = "runner/api.py"
    line = "88"               # optional; single line or range
    note = "..."              # one-sentence markdown; the nit itself

Prose fields are markdown (commonmark plus tables). The renderer escapes
everything else; never pre-escape content.

## state.json

    {
      "updated_at": "2026-08-08T14:00:00Z",
      "findings": {
        "f1": {
          "disposition": "post",          // "post" | null (the toggle is off by default)
          "note": "soften this",
          "note_rev": 1,
          "edited_comment": "...",
          "edited_comment_rev": 1
        }
      }
    }

## Merge and staleness rules

- A note is stale when its note_rev is lower than the finding's
  comment_rev (default 1). An edit is current only when its
  edited_comment_rev equals comment_rev; any other value is stale. Stale
  entries are flagged, not applied.
- Postable body: edited_comment when edited_comment_rev equals comment_rev,
  else comment.
- When the agent rewrites a comment from a note it bumps comment_rev; the
  formerly-current note becomes stale and is exposed as such by `status`.
- `review-branch status <round-dir>` prints the merged view as JSON (review metadata plus merged findings).
- `review-branch manifest <round-dir> [--exclude f3,f7]` prints posting
  entries `[{"file", "line", "body"}]` for findings with disposition "post"
  that are commentable and not yet posted.

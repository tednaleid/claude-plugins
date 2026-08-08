# review-branch collaborative review design

Date: 2026-08-08
Status: draft, pending Ted's review

## Purpose

Evolve the review-branch plugin from a one-way HTML report generator into a
collaborative review loop: Claude produces structured findings, Ted marks them
up in the browser (dispositions, direct edits, notes to Claude), and Claude
reads that state back to revise and post comments to the MR/PR. Along the way,
fix four standing problems: HTML output overflowing agent context, missing
explanatory diagrams, inconsistent output placement, and manual worktree setup.

## Decisions summary

- Structured data is canonical. Claude writes `review.toml`; a Python tool
  renders HTML from it. Claude never emits full HTML documents.
- Review artifacts live centrally under the XDG data dir, not in per-repo
  `.llm/` directories. One git repo at the data root auto-commits every change.
- A single localhost daemon on a fixed port serves all reviews. Routes carry
  review identity. `GET /` is an index of all reviews.
- Browser state persists to `state.json` via the daemon. localStorage is
  removed. Opening rendered HTML via `file://` is a read-only snapshot.
- Ted's markup per finding: tri-state disposition (Post / Skip / Undecided), a
  directly editable comment body, and a free-text note instructing Claude.
- Posting: glab-comment migrates from dotfiles into the plugin; a sibling
  gh-comment is built now. Both share one manifest format and the mandatory
  "From Claude" marker. Nothing posts without an explicit ask.
- The worktree plugin gets a script codifying worktree creation, with optional
  `.worktree.toml` hooks (wtp-style copy/symlink/command).
- Everything stays in this plugin repo, but each script is self-contained and
  the formats are documented as specs, so extraction to a standalone project
  later is a `git mv`, not a rewrite.

## Architecture: two layers, decoupled

The deterministic layer is real software: renderer, daemon, manifest
generation, posting CLIs, worktree tool. It knows nothing about Claude. Any
agent (or a human with an editor) could produce `review.toml` and get the same
HTML, the same server, the same posting behavior.

The judgment layer is skill prose: lens agents, aggregation rules, diagram
selection, note interpretation, posting norms. It drives the deterministic
layer through documented interfaces only: the TOML/JSON schemas, the CLI
subcommands, and the HTTP API.

Boundary rules that keep the layers separable:

- Scripts are single-file uv-shebang Python. No imports from plugin machinery,
  no assumptions about running from a plugin directory.
- Schemas and the HTTP API are documented in `references/` as specs, written
  for any consumer, not as Claude-only prose.
- Tests live in this repo next to the scripts and run without Claude.
- Inversion stays cheap: the tool could later ship standalone and install the
  skills itself, because the skills only ever call the public CLI surface.

## Storage layout

Data root: `${REVIEW_BRANCH_HOME:-${XDG_DATA_HOME:-~/.local/share}/review-branch}`

Daemon plumbing (pidfile, log): `${XDG_STATE_HOME:-~/.local/state}/review-branch/`

```
<data-root>/                        # git repo, auto-committed by the tool
  <repo-id>/                        # e.g. omni-a3f2
    mr-124/                         # slug: mr-<n>, pr-<n>, or branch slug
      round-1/
        review.toml                 # Claude-authored
        state.json                  # daemon-authored (browser state)
        review.html                 # rendered view, regenerable
        diagram.svg                 # assets referenced from review.toml
      round-2/                      # re-review after new pushes
```

- `repo-id` = `<repo-name>-<hash4>` where hash4 is the first 4 hex chars of
  SHA-256 of the origin remote URL, falling back to the main worktree's
  absolute path for remote-less repos. Remote-based hashing keeps identity
  stable when a checkout moves on disk. Caveat: moving a remote-less repo
  orphans its old id; acceptable.
- The git repo at the data root is created on first use. Every write by the
  tool (render, state save, posted results) runs `git add -A && git commit`
  with a message like `omni-a3f2 mr-124 round-1: state update`. History is
  noisy by design; it is read forensically, not linearly. A remote can be
  added by hand for the rare push-it-somewhere case.
- The review worktree's own `.llm/` holds only ephemeral scratch during a
  review run (diff.patch, changed-files.txt, prior-comments.md for lens
  seeding). Nothing durable lands there anymore.

## Data model

### review.toml (Claude-authored, the only file Claude writes)

```toml
[review]
title = "MR 124 review - OMNI-15209 per-repo starting refs"
vcs = "glab"                # glab | gh | local
number = 124                # absent in local mode
url = "https://gitlab...."  # absent in local mode
source_branch = "omni-15209-per-repo-starting-refs"
target_branch = "main"
commits = 4
files = "20 (+1752 / -43)"
spec = "docs/specs/OMNI-15209.md"   # optional

[overall]
body = """Markdown prose framing the change and the headline asks."""

[[assets]]                  # rendered in order below the header; zero or more
type = "svg"                # svg | html (html passes through verbatim)
path = "diagram.svg"        # relative to the round directory
caption = "Run-creation sequence"

[[findings]]
id = "f1"
severity = "high"           # high | med | low | info
title = "Validation skips the empty-repo case"
file = "runner/api.py"
lines = "108-121"
lenses = ["security"]
body = """Markdown explanation: what, why it matters, what triggers it."""
snippet = '''raw code; the renderer escapes it'''   # optional
fix = "one-line suggested fix"                      # optional
comment = """Draft comment body, markdown, as it would post."""
comment_rev = 1             # bumped each time Claude rewrites the comment
anchor = "runner/api.py:121"    # postable new-file line; defaults from file/lines
commentable = true          # false renders the card without a comment area
posted_at = "2026-08-08T14:02:11Z"   # written by Claude after posting
posted_url = "https://gitlab..../notes/98765"
posted_body = """Final text as posted, marker excluded."""

[[coverage]]
surface = "CreateRunRequest schema"
covered = "tests/unit/test_schemas.py"
gap = ""                    # or a finding id like "f2"

[[hex]]                     # only when the architecture lens ran in hex mode
boundary = "RepoRegistryPort"
change = "Added list_by_project_slug to protocol + adapter + test double"
status = "OK"               # OK | OK / nit | Concern | Violation

[[files_touched]]
path = "runner/api.py"
delta = "+18"
notes = "Validation block; see f1, f2"
```

Prose fields are markdown; the renderer converts and HTML-escapes. Claude
appends findings incrementally (one Write or Edit per lens batch), so no
single tool call carries the whole document. This is the fix for context
overflow.

### state.json (daemon-authored, on behalf of the browser)

```json
{
  "updated_at": "2026-08-08T14:00:00Z",
  "findings": {
    "f1": {
      "disposition": "post",          // "post" | "skip" | null (undecided)
      "note": "soften this, mention it could be a follow-up MR",
      "note_rev": 1,                  // comment_rev the note was written against
      "edited_comment": null,         // set once Ted touches the textarea
      "edited_comment_rev": 1
    }
  }
}
```

### Ownership and staleness

- `review.toml` is written only by Claude. `state.json` is written only by the
  daemon. The renderer and manifest generator merge the two; Ted's edits win.
- Posted results are Claude's action and audit record, so they live in
  `review.toml` (`posted_at`, `posted_url`, `posted_body`).
- When Claude rewrites a comment per a note, the new draft lands in
  `review.toml` with `comment_rev` bumped. The page treats `note` and
  `edited_comment` with a rev older than `comment_rev` as consumed: it clears
  the note box and textarea prefill. Nothing is lost because Claude read both
  the edit and the note when rewriting.
- Merge rule for the postable body: `edited_comment` if its rev equals
  `comment_rev`, else `comment`.

## The tool: review_tool.py

Single uv-shebang script shipped at `plugins/review-branch/scripts/`. Reading
TOML uses stdlib `tomllib`; dependencies: `markdown-it-py`, `tomli-w`. The
HTML template is embedded in the script as a string so the installed copy is
one file.

Subcommands:

- `init --slug <slug>` - run from inside a repo. Computes repo-id, picks the
  next round number, creates the round directory, prints its absolute path.
- `render <review-dir>` - reads review.toml, state.json, assets; writes
  review.html with the last-saved state baked in; auto-commits. SVG and html
  assets are inlined into the page, so review.html is self-contained for
  `file://` viewing.
- `open <review-dir>` - ensures the daemon is running (starts it detached if
  the port is not answering), prints the review URL. Idempotent. Compares its
  own version to the daemon's health endpoint and gracefully restarts an older
  daemon.
- `status <review-dir>` - prints the merged view as JSON: dispositions, notes,
  staleness, posted markers. This is what Claude reads before revising or
  posting.
- `manifest <review-dir> [--exclude f3,f7]` - emits the posting manifest JSON
  for findings with disposition `post`, using the merge rule above. Excludes
  let Claude hold ambiguous items out of a batch.
- `install` - copies itself and its sibling comment scripts (from the
  directory the invoked script lives in, i.e. the plugin's `scripts/`) to
  `~/.local/bin/` as `review-branch`, `glab-comment`, and `gh-comment`. The
  skills re-run install when the plugin copy is newer than the installed one.
- `daemon` - runs the server in the foreground (used internally by `open`).
- `stop` - stops the daemon via pidfile.
- `--version` on everything.

## The daemon

- Binds 127.0.0.1 only, default port 43117, override via `REVIEW_BRANCH_PORT`.
  No auth; localhost trust is the threat model.
- Routes are the filesystem: `/<repo-id>/<slug>/round-N/` maps to the same
  path under the data root. No registry. The daemon serves what exists.
- `GET /` - index page: all reviews sorted by last activity, showing title,
  repo, severity counts, disposition progress.
- `GET /<route>/` - renders the page in memory on each request, so Claude
  edits to review.toml appear on refresh. The on-disk review.html snapshot is
  refreshed (and committed) only by `render` and after each state save, never
  by page views.
- `GET /<route>/api/state` - seeds the page on load.
- `POST /<route>/api/state` - writes state.json, auto-commits. The route in
  the URL decides the target file, so a stale tab can never write into a
  different review. Unknown route returns 404 with a clear message.
- `GET /<route>/api/version` - cheap change token (mtime hash of review.toml,
  state.json, assets). The page polls every ~2s and reloads on change.
- `GET /api/health` - app name, version, data root. Used by `open` for the
  version handshake and to distinguish our daemon from a port squatter.
- Lifecycle: started on demand by `open`, detached (survives any Claude
  session), stays up until `stop` or reboot. Port bind is the single-instance
  mutex. A sleepy Python process is cheap; no idle reaper.
- Plugin update while running: next `open` sees the version mismatch and
  restarts it. Open tabs ride through via the reconnect path.

### Failure behavior in the page

- The page keeps working from in-memory state when the daemon is unreachable.
  A banner shows "server unreachable - N unsaved changes held in this tab"
  with the exact recovery command, retries with backoff, and flushes
  automatically on reconnect.
- Closing a tab with unsaved changes triggers a beforeunload warning. The
  banner includes a "copy unsaved state" link as the disaster hatch: Ted
  pastes the JSON to Claude, who merges it by hand.
- `file://` open (no daemon): read-only snapshot of the last render, with a
  banner naming the `open` command to make it live. No localStorage anywhere.

## Page UX

- One card per finding (the separate findings and comments sections merge).
  Card: severity badge, title, `file:lines`, lens tags, prose, snippet,
  suggested fix, then the comment area: textarea prefilled with the current
  draft (edits save as `edited_comment`), a note box ("tell Claude how to
  adjust this"), and the Post / Skip / Undecided control (default Undecided).
- Findings with `commentable = false` render without the comment area.
- Posted findings show a posted badge linking to `posted_url`; their inputs
  freeze.
- Progress line: "3 post, 2 skip, 4 undecided". Dark theme and visual style
  carry over from the existing template.
- Saves are debounced a few seconds and sent whole-document to the state
  endpoint.

## Posting flow

Ted's phrasing picks the mode:

- "update the html for #8" - Claude rewrites the comment in review.toml
  (starting from Ted's edited body if present), bumps `comment_rev`,
  re-renders; the page auto-reloads.
- "show me the edit here" - Claude shows the revised body in the terminal.
- bare `/glab-comment` or `/gh-comment` or "post the checked ones" - interpret
  notes and post directly.

Posting mechanics:

1. Claude runs `status`, reads dispositions and notes.
2. For noted comments: a clear note produces a rewrite (rev bump, recorded in
   review.toml). An ambiguous note, one that contradicts the finding, or one
   that reads as a question to Claude gets held: the clear ones post, the held
   ones are raised for discussion in the terminal. Posting is never blocked on
   discussion unless the note itself is unclear.
3. `manifest --exclude <held>` produces the batch. Dry-run first (anchor
   validation), then the real run.
4. Claude writes `posted_at`, `posted_url`, `posted_body` into review.toml,
   re-renders; the open tab shows posted badges.

Hard rules, carried verbatim from the dotfiles skill: the "From Claude" marker
is prepended unconditionally by the scripts; one ask authorizes one batch;
never resolve, approve, merge, or close; duplicate detection refuses a line
that already carries a From Claude comment; a failed-looking POST is never
retried by hand, re-run and let the duplicate check decide.

## Comment skills

The plugin grows two skills beside review-branch, each wrapping a script in
`plugins/review-branch/scripts/` (also installed to PATH by `install`):

- `glab-comment` - Ted's existing script moved nearly as-is. The dotfiles
  skill and hand-managed `~/.local/bin` copy retire.
- `gh-comment` - new sibling, same manifest format, marker, dry-run, anchor
  validation (parsing `gh pr diff`), duplicate detection (scan existing review
  comments for the marker at the same path:line). Posts via
  `POST /repos/{owner}/{repo}/pulls/{n}/comments` with `commit_id` = head SHA,
  `path`, `line`, `side=RIGHT`. General comments via `gh pr comment`.
- Shared limits: anchors target new-file lines only; no replies into threads;
  no editing or deleting; fix a bad comment in the web UI.
- Veer rules: the existing block on raw `glab api ... /discussions -X POST`
  stays; add the matching block for raw gh review-comment POSTs.

Manifest format (unchanged from the existing glab-comment):
`[{"file": ..., "line": ..., "body_file": ...}]` with `body` allowed for
inline text.

## Worktree script

The worktree plugin gets `scripts/worktree_tool.py` (uv shebang) codifying the
current manual steps:

1. Resolve branch from MR number, PR number, URL, or branch name (glab/gh
   detection from the origin remote).
2. `git fetch origin`, `git worktree add` under `.claude/worktrees/` (slashes
   in branch names become dashes in the directory).
3. Copy gitignored `.env*` and `.envrc` from the main worktree only.
4. `direnv allow` only if the parent directory was already allowed.
5. Bootstrap by lockfile: uv / bun / pnpm / npm.
6. Optional `.worktree.toml` in the repo root adds wtp-style hooks:
   `[[copy]]`, `[[symlink]]`, `[[command]]` entries run after creation.

The worktree SKILL.md shrinks to: run the script, call EnterWorktree, report.
The review-branch skill keeps delegating to the worktree skill unchanged.

## Diagrams

New `references/diagrams.md` in the review-branch skill. After aggregation,
Claude picks the diagram by what the branch does:

- sequence diagram (default): any control-flow change across components
- ER-style diagram: schema or table changes
- state diagram: lifecycle or status-field changes
- component diagram: architectural moves, new services, dependency changes
- none: trivial or docs-only branches

Diagrams are SVG files authored by Claude into the round directory and
referenced from `[[assets]]` with captions. The reference doc pins the palette
(the template's dark-theme variables), minimum text size, and canvas width so
diagrams are consistent across reviews. `type = "html"` assets remain the
escape valve for shapes SVG does not fit.

## Plugin layout after this work

```
plugins/review-branch/
  .claude-plugin/plugin.json
  agents/lens-*.md                      # unchanged
  skills/review-branch/SKILL.md         # rewritten: toml + render + open flow
  skills/review-branch/references/
    data-format.md                      # review.toml + state.json spec
    http-api.md                         # daemon routes and payloads
    diagrams.md                         # diagram selection and style
    glab.md, gh.md, agent-contract.md   # carried over
  skills/glab-comment/SKILL.md
  skills/gh-comment/SKILL.md
  scripts/review_tool.py
  scripts/glab_comment.py
  scripts/gh_comment.py

plugins/worktree/
  skills/worktree/SKILL.md              # shrinks to script + EnterWorktree
  scripts/worktree_tool.py
```

`assets/template.html` and `references/html-template.md` are removed; the
template lives inside review_tool.py and the data format spec replaces the
substitution guide.

### review-branch SKILL.md changes

Steps 1-2 (parse input, detect VCS) unchanged. Step 3 replaces slug/filename
logic with `review_tool.py init`. Step 4 (worktree) unchanged. Step 5 (seed
context) unchanged except scratch stays ephemeral. Step 6 (lenses) unchanged.
Step 7 (aggregate) now writes findings into review.toml incrementally. Step 8
becomes: author diagram assets, run `render`, run `open`. Step 9 reports the
review URL (not a file path), severity counts, and worktree cleanup commands.
The "no auto-posting" rule gains the pointer to the glab-comment/gh-comment
skills as the sanctioned path.

## How the original problems map to this design

1. Context overflow: Claude writes TOML incrementally; the renderer produces
   the HTML. No large tool calls.
2. Diagrams: `[[assets]]` slots plus references/diagrams.md selection guidance.
3. Comment posting: glab-comment migrates into the plugin, gh-comment is
   built, posting stays explicit-ask-only with judgment for ambiguous notes.
4. Placement and worktrees: central XDG data root ends the placement lottery
   and survives worktree destruction; worktree_tool.py automates setup.
5. Collaborative state: daemon + state.json round-trip, tri-state
   dispositions, edits, notes, revision tracking, posted audit trail.

## Error handling summary

- Daemon down: page banners, holds state, retries, flushes on reconnect;
  copy-state hatch as last resort.
- Stale tab or deleted review dir: 404 by route; no cross-review writes are
  possible by construction.
- Port squatter: health endpoint identifies foreign processes; `open` picks
  the failure message over silently talking to the wrong server.
- Anchor refusal: the posting scripts already name the closest addressable
  lines and post nothing; Claude re-anchors and retries the batch.
- Malformed review.toml: `render` and `status` fail with the TOML parse error
  and line number; nothing is partially written.
- Repo without origin remote: repo-id falls back to path hash; local mode
  already handles no-MR flows.

## Testing

Pytest via a justfile target in this repo, no Claude involvement:

- Golden-file render tests: review.toml fixtures in, expected HTML out.
- State merge and staleness: edited/noted/consumed rev combinations.
- Manifest generation including excludes and the merge rule.
- Anchor parsing against fixture diffs (glab and gh shapes).
- Daemon smoke test: start on a random port, POST state, confirm file content
  and auto-commit, health and version endpoints.
- Worktree script: branch resolution table tests; hook execution against a
  fixture `.worktree.toml` in a temp repo.

## Out of scope for this round

- Multi-line (line-range) comments and thread replies in either poster.
- Editing or deleting posted comments.
- A standalone repo or brew distribution (extraction path kept cheap; see
  Architecture).
- Live collaborative editing (multiple simultaneous browsers on one review);
  last-writer-wins whole-document saves are accepted.
- Pushing the data-root repo to a remote automatically.

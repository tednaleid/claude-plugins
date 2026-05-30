# HTML template rendering

The output is built by reading `assets/template.html` and substituting placeholder markers with rendered content. There is no template engine -- substitution is done with the `Edit` tool using `replace_all: false` per marker.

## Placeholders

Every marker appears **exactly once** in `template.html`. Replace each with the rendered string described below.

| Marker | What it is | Required |
|---|---|---|
| `{{TITLE}}` | Page title text. Appears twice -- once in `<title>` and once in `<h1>`. Replace both with `replace_all: true`. | Yes |
| `{{SUBTITLE}}` | One-line context, e.g. "Code review notes for Ted to use when commenting on the MR. Author: Tom Martz." | Yes |
| `{{META_ROW}}` | The `<span>...</span>` items inside the meta row. See "Meta row" below. | Yes |
| `{{SUMMARY_GRID}}` | The `.card` divs counting findings per severity. See "Summary grid" below. | Yes |
| `{{OVERALL_BODY}}` | One or two `<p>` paragraphs framing the change and the headline asks. | Yes |
| `{{FINDINGS_BODY}}` | All finding `<div class="finding ...">` blocks concatenated. See "Finding card" below. | Yes |
| `{{HEX_TABLE_BLOCK}}` | The hex compliance H2 + table, or empty string when hex doesn't apply. | Conditional |
| `{{COVERAGE_TABLE_BLOCK}}` | The "What the tests do and don't cover" H2 + table. Always include even if brief. | Yes |
| `{{FILES_TABLE_BLOCK}}` | The "Files touched" H2 + table. | Yes |
| `{{COMMENTS_BLOCK}}` | All `<div class="comment-block">` blocks. See "Suggested comment" below. | Yes |
| `{{LOCAL_STORAGE_KEY}}` | Per-review key. Format: `<output-filename-without-.html>-checks-v1`. Example: `mr-124-review-checks-v1`. | Yes |

If a finding or comment is empty (no content), leave a one-line `<p class="small">None.</p>` rather than skipping the section -- consistency matters.

## Meta row

One `<span>` per fact. Order: link to MR/PR -> branch -> commits -> files -> spec (optional).

```html
<span><strong>MR:</strong> <a href="https://gitlab.example.com/.../-/merge_requests/124">!124</a></span>
<span><strong>Branch:</strong> feature-name -> main</span>
<span><strong>Commits:</strong> 4</span>
<span><strong>Files:</strong> 20 (+1752 / -43)</span>
<span><strong>Spec:</strong> docs/specs/OMNI-15209-per-repo-starting-refs.md</span>
```

For GitHub PRs, swap the label: `<strong>PR:</strong> <a href="...">#42</a>`.
For local-only branch reviews (no MR/PR), drop the MR/PR span and start with the branch.

## Summary grid

One `.card` per severity that has at least one finding. Always show High and Med even if zero (signals what was looked for); show Low/Info only if non-zero.

```html
<div class="card"><div class="num high">1</div><div class="label">High</div></div>
<div class="card"><div class="num med">5</div><div class="label">Medium</div></div>
<div class="card"><div class="num low">5</div><div class="label">Low / nits</div></div>
<div class="card"><div class="num info">3</div><div class="label">Out-of-scope flags</div></div>
```

## Finding card

Severity drives the class on `.finding` AND the `.badge`. Number them sequentially (`#1`, `#2`, ...) in the order they appear after sorting.

```html
<div class="finding high">
  <div class="head">
    <input type="checkbox" class="chk" data-id="f1" />
    <span class="num">#1</span>
    <span class="title">Short, specific title. Inline <code>like-this</code> is fine.</span>
    <span class="badge high">High</span>
  </div>
  <div class="file">path/to/file.py:108-121</div>
  <p>Prose explanation: what the issue is, why it matters, what triggers it.</p>
<pre><code>// optional code snippet, escape &lt; &gt; &amp; properly
</code></pre>
  <p><strong>Suggested fix:</strong> short, actionable. Skip if obvious.</p>
</div>
```

Rules:

- `data-id` is unique across all findings AND comments in the file. Use `f1`, `f2`, ... for findings and `c1`, `c2`, ... for comments. The localStorage key uses this id.
- Severity classes: `high`, `med`, `low`, `info`. Use both on the `.finding` div and on the `.badge` span.
- `.file` is monospace and shows the path with optional line range. Pre-existing issues introduced before this MR should still have a line range to point Ted at the right spot.
- HTML-escape any user content (`<`, `>`, `&`). Especially diff snippets and quoted code.
- Use `<em>` for emphasis (avoid `<i>`).

## Suggested comment

Same checkbox + `data-id` scheme, but in a `comment-block`:

```html
<div class="comment-block" data-cid="c1">
  <div class="comment-head">
    <input type="checkbox" class="chk" data-id="c1" />
    <h3>Comment on path/to/file.py:108-121</h3>
  </div>
<pre><code>The comment body, written as if you were typing it directly into the MR.
Keep it short. Use the question-based tone (see references/agent-contract.md).
Multi-line is fine.</code></pre>
</div>
```

## Hex compliance table (conditional)

Only emit when hex applies (the architecture lens ran in hex mode). One row per boundary touched:

```html
<h2>Hexagonal architecture compliance</h2>
<table>
  <tr><th>Boundary</th><th>Change</th><th>Status</th></tr>
  <tr><td><code>RepoRegistryPort</code></td><td>Added <code>list_by_project_slug</code> to protocol + adapter + test double</td><td>OK</td></tr>
  <tr><td>SQL location</td><td>New query lives in adapter, not service</td><td>OK</td></tr>
  <tr><td>Composition root</td><td>No new <code>EXECUTOR_MODE</code> branching</td><td>OK</td></tr>
</table>
```

Status values: `OK`, `OK / nit`, `Concern`, `Violation`. Findings referenced in the table should cross-link via `<strong>Finding #N</strong>`.

## Coverage table

Two columns: what's covered, what's a gap. Cross-reference finding numbers for the gaps.

```html
<h2>What the tests do and don't cover</h2>
<table>
  <tr><th>Surface</th><th>Covered</th><th>Gap</th></tr>
  <tr><td><code>CreateRunRequest</code> schema</td><td><code>tests/unit/test_schemas.py</code></td><td>&mdash;</td></tr>
  <tr><td>API 422 paths</td><td>&mdash;</td><td><strong>Finding #2</strong></td></tr>
</table>
```

Use `&mdash;` (em-dash) for "none" in either column.

## Files-touched table

Quick reference. Order by importance, not alphabetically. Cross-reference findings.

```html
<h2>Files touched (quick reference)</h2>
<table>
  <tr><th>File</th><th>+/-</th><th>Notes</th></tr>
  <tr><td><code>runner/api.py</code></td><td>+18</td><td>Validation block; see #1, #2</td></tr>
  <tr><td><code>tests/*</code></td><td>+229 / -2</td><td>5 new tests; see #2, #3, #4</td></tr>
</table>
```

## Render workflow

1. Read `assets/template.html` (it ships with the skill).
2. Compose each section as a string (or a small set of strings concatenated).
3. Use `Edit` with `replace_all: true` for `{{TITLE}}` (it appears twice -- in `<title>` and `<h1>`).
4. Use `Edit` once per other placeholder.
5. Write the result to `.llm/reviews/<slug>-review.html`.

Easier alternative: read `template.html` into memory, do all substitutions in-Claude as a string, then `Write` the final file in one call. Either way works -- pick whichever is fewer tool calls.

## What NOT to do

- **Do not** modify the CSS, the JS, or the structural skeleton. The template is the visual contract; consistency across reviews matters.
- **Do not** add new sections. If you have content that doesn't fit a placeholder, put it in `{{OVERALL_BODY}}` as an extra paragraph.
- **Do not** use emojis or em-dashes in prose. The HTML uses `&mdash;` in tables for "none" -- that's the only exception.
- **Do not** auto-generate the LocalStorage KEY from a random nonce. Use the output filename so re-runs (overwrite mode) preserve checkbox state, and new-round files (mr-124-review-2.html) get their own state automatically.

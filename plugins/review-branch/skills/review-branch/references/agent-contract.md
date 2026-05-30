# Lens agent contract

Every lens subagent shares this output schema and tone. The aggregator depends on the schema being consistent across all 4 lenses.

## Inputs each lens receives

Provided in the prompt by the orchestrating SKILL.md:

| Input | What it is |
|---|---|
| `worktree_path` | Absolute path to the isolated worktree of the source branch. Subagents read source files from here. |
| `diff_path` | Path to a file containing the unified diff (`glab mr diff` / `gh pr diff` output). |
| `changed_files` | Newline-separated list of file paths that were modified, added, or deleted in the diff. |
| `target_branch` | The branch the diff is against (e.g., `main`). Useful for reading the pre-change version of files. |
| `target_worktree_path` | Optional: a second worktree pinned to `origin/<target_branch>`. If absent, use `git show <target_branch>:<path>` for old versions. |
| `prior_comments_path` | Path to a markdown file containing prior MR/PR discussion. May be absent for local-only branch reviews. |
| `spec_path` | Optional: path to a design or spec doc the diff implements. |
| `lens_specific_context` | Lens-specific extras (e.g., the architecture lens gets `hex_mode: true|false` and the path to `docs/hexagonal-architecture.md` if present). |

## How to read code

- **Read full files end-to-end.** Use the `Read` tool with the path from `worktree_path`. Never use `head`, `tail`, or grep to skim. The diff is for navigation; the source is for understanding.
- **Read 2+ comparable files** for any pattern comparison. If you're flagging a deviation from convention, the prompt needs to cite which files set the convention.
- **Trace execution paths.** Before flagging a bug, walk the call graph to confirm reachability.
- **Reproduce when you can.** If the bug suggests "this test would fail," try running it (`just test` if a justfile is present; else fall back to `uv run pytest`, `bun test`, `go test`, whichever fits the project). Mark findings with `reproduced: true | false | n/a`.

## What you may flag

- Issues **introduced or made worse** by this diff.
- Pre-existing issues that become acute because of this diff (note them as pre-existing).
- Things on the diff that are obviously fine but should be called out as out-of-scope for the MR (commit hygiene, unrelated bundled changes, MR description quality).

## What you must NOT flag

- Pre-existing issues unrelated to the diff. Out of scope.
- Style preferences not in any CLAUDE.md, AGENTS.md, or other in-repo guidance.
- Things a linter / type checker / formatter would catch.
- Topics already addressed in `prior_comments_path` (read it before generating findings).

## Output format

Return ONLY a JSON array. First character `[`, last character `]`. No markdown, no code fences, no explanation.

```json
[
  {
    "file": "runner/api.py",
    "line_range": "108-121",
    "search_text": "if req.start_refs and not req.project_slug",
    "title": "Short, specific title. Inline `like-this` is fine.",
    "severity": "high",
    "lens": "security",
    "description": "What the issue is, why it matters, what triggers it. Prose, not bullets.",
    "snippet": "if req.start_refs and not req.project_slug:\n    raise HTTPException(422, ...)",
    "suggested_fix": "Hoist the get_project_by_slug check out of the conditional so any non-null project_slug is validated.",
    "reproduced": "n/a",
    "draft_comment": "Optional: a copy-paste-ready MR/PR comment body. Use the question-based tone (see below). Skip if the finding doesn't lend itself to a comment."
  }
]
```

Field rules:

- **`file`** -- relative path from repo root, exactly as it appears in `changed_files`.
- **`line_range`** -- single line (`108`) or range (`108-121`). Use the source line numbers, not diff hunk offsets.
- **`search_text`** -- a short, unique substring near the issue. Used to navigate when line numbers shift. Plain text only -- no shell metachars (`$`, `(`, `{`, backticks).
- **`title`** -- under ~80 chars. Inline `<code>` (backticks become `<code>` in the HTML render) is allowed.
- **`severity`** -- exactly one of: `high`, `med`, `low`, `info`.
  - `high`: a real bug, security issue, data-loss risk, or a contract violation that will affect production behavior.
  - `med`: a real correctness concern in a less-traveled path, a meaningful test gap, or a structural issue worth fixing this MR.
  - `low`: a nit, a small footgun, a readability improvement.
  - `info`: out-of-scope flags -- commit hygiene, MR description gaps, follow-up suggestions, pre-existing issues worth noting but not for this MR.
- **`lens`** -- one of: `architecture`, `security`, `coverage`, `naming`. Matches the lens producing the finding (helps the aggregator dedupe).
- **`description`** -- a paragraph or two of plain prose. Concrete and specific. Reference file paths and line numbers.
- **`snippet`** -- optional. Include only when the code is short and the visual helps. Verbatim from source.
- **`suggested_fix`** -- optional. Concrete and short. Skip if the description already makes the fix obvious.
- **`reproduced`** -- `true` (you ran a test that confirms the bug), `false` (you tried to reproduce and couldn't, but still believe it's a bug), or `n/a` (didn't apply, e.g. naming / coverage findings).
- **`draft_comment`** -- optional but encouraged for `high` / `med` findings. The exact text you'd paste into the MR/PR. Use the tone below.

Empty result is `[]`. Nothing else.

## Tone guidelines for descriptions and draft comments

- **Be kind.** There's a human author on the other side.
- **Use questions for comments.** "What happens if..." not "This will crash." "Have you considered..." not "You should." "Is this intentional?" not "This is wrong."
- **Be specific.** Cite the file, the line, the condition. Don't generalize ("error handling is weak"); describe the case ("if `start_refs` is set and `project_slug` is null, the 422 never fires").
- **Acknowledge correct intent.** If the code obviously works in the common path, say so before describing the edge case.
- **Skip the fluff.** No "great work overall" preambles. No emojis. No em-dashes (`--` if you must). No exclamation points.
- **For pre-existing issues you flag anyway**, say so up front: "Not introduced by this MR -- but ..."

## Severity calibration

When in doubt, drop one level. A noisy review trains the human reviewer to skip your findings.

- Don't tag `high` unless production behavior or security is at risk.
- Don't tag `med` for things you'd be fine seeing in a follow-up MR.
- `low` and `info` are fine to be generous with -- the human checks them off.

## Lens dedup hints (for the aggregator)

The same issue may surface from two lenses (e.g., a missing input validation is both a `security` finding and a `coverage` finding). When this happens:

- Each lens reports its own framing.
- The aggregator picks the highest severity, keeps the most specific description, and merges the `draft_comment` if both have one.

To make this easier, when you flag something a sibling lens would also flag, include the relevant cross-cutting concern in the description (e.g., "from the security angle, this is a validation gap; from the coverage angle, it's also an untested error path").

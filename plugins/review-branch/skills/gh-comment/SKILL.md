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

# Relay doc template

Use this skeleton when drafting a relay doc. Drop any section whose content
would be empty or forced — a shorter honest doc beats a padded one. Order is
fixed so a receiver knows where to look.

Inline only what isn't already captured somewhere the receiver can read.
Everywhere else, link: commit SHAs, plan file paths, issue numbers, specific
`path:line` references. Progressive disclosure is the point — the receiver
should be able to scan the doc in under a minute and dig into links only where
they need to.

```markdown
# <Topic> — Context Relay

> **Resume prompt.** Paste this into a fresh Claude Code session in this repo:
>
> ```
> Read <absolute-path-to-this-doc> and continue the work described there.
> ```

## Context

Why this work is happening. What the user is trying to accomplish. Constraints
that shape the solution (deadline, stakeholder, compatibility, compliance).
2–5 sentences.

## Current state

What is done and durable — merged PRs, shipped commits, files that exist on
disk. Reference commits by SHA and short message: `abc1234 add foo handler`.
If a file was created, say so (`src/foo.ts created`). This section should let
the receiver trust that the named artifacts actually exist.

## Active work

What is in flight right now but not yet durable: uncommitted changes, a branch
in progress, a spec being drafted. Name the branch, name the files, point to
specific lines where useful. Describe the state precisely enough that the
receiver could pick up `git status` and recognize everything.

## Next steps

Concrete and actionable. A fresh instance should be able to execute the first
item without asking "do what exactly?". Number them. Each step should name the
file(s) it touches and the specific change.

Bad: "1. Finish the auth work."
Good: "1. In `src/auth/middleware.ts`, replace the TODO on line 42 with a call
to `verifyToken(req.headers.authorization)` from `src/auth/jwt.ts`."

## Key decisions

Choices already made and *why*, so the receiver doesn't re-litigate them. One
bullet per decision. The "why" matters more than the "what" — without it, a
fresh instance will second-guess and waste time.

- Chose X over Y because <reason from the session>.
- Agreed to defer Z until after the <constraint>.

## References

Links and pointers, grouped. Drop groups that don't apply.

- **Plans / specs:** `docs/spec/foo.md`, `.claude/plans/bar.md`
- **Commits:** `<SHA> <short msg>`, `<SHA> <short msg>`
- **Issues / PRs:** `#123`, `PR#45`
- **Files to know about:** `path/to/file.ts:42–67` — <one-line role>
- **External docs:** <URL> — <one-line why it matters>

## Gotchas

Non-obvious knowledge that only exists in the current session's head. The
things you'd lean over and whisper to a colleague before you left for vacation.

- The test suite passes only after `just seed-db` — CI does this automatically
  but local runs look broken without it.
- `config/prod.yaml` looks identical to `config/staging.yaml` but a hidden
  env substitution in the deploy script changes one value. Don't diff them and
  assume they're the same.
- <etc>

## Known uncertainties

*Only include this section if the review loop hit its iteration cap with
substantive questions unresolved.* List each as a question the receiver
should confirm with the user before acting on the relevant next step.
```

## Rules for filling the template

- **Verify facts against the repo.** Use `git log`, `git status`, Read, and
  Grep before writing any claim. Do not rely on conversation memory alone — it
  drifts.
- **Use absolute paths for the resume prompt.** Relative paths break if the
  receiver starts Claude from a different directory.
- **Prefer `path:line` refs over prose descriptions** of code locations.
- **Do not inline whole files or whole plan docs.** Link them.
- **Do not add sections not in the template.** Resist the urge to add "Testing
  notes" or "Open questions" sidebars. If a section would be empty, drop it.
- **No emojis, em-dashes, or hyperbole.** Match the style of existing docs in
  the repo.

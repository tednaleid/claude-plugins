---
name: context-relay
description: Serialize a long Claude Code session's working state into a relay markdown doc, iteratively refine it by consulting a fresh-context reviewer subagent, and emit a copy-paste resume prompt for a brand-new Claude instance. Use whenever the user mentions context getting full, wanting to hand off a session, before running /clear, before compaction, passing the baton to a fresh Claude, checkpointing current work, saving session state, or asking for a resume prompt. Also use proactively when the user notices the conversation is getting long and valuable context would be lost if the session ends.
---

# context-relay

Pass the baton from one Claude session to the next without dropping it.

This skill produces a *relay doc*: a markdown file that captures what the
current session knows so a fresh Claude instance can continue the work with no
Q&A round. A dedicated reviewer subagent (`relay-reviewer`) opens the doc cold
and surfaces substantive ambiguities, which the current Claude resolves by
editing the doc. The loop repeats up to three times, tightening the grip on
the baton before the actual pass.

## Workflow

```
DETECT-LOCATION --> DRAFT --> REVIEW-LOOP (<=3) --> FINALIZE
```

Work through each step in order. Do not skip the review loop — a fresh
reviewer catches things the writer cannot see.

## Step 1: Detect location

Pick where the relay doc will live. Probe the repo, then confirm with the user.

### Probe for existing conventions

Check, in order. First match wins as the *suggested* default:

| Path | Signal |
|------|--------|
| `docs/spec/` or `docs/specs/` | Project uses spec docs |
| `specs/` or `plans/` | Top-level plan convention |
| `.claude/plans/` | ideation plugin convention |
| `.claude/relays/` | Dedicated relay convention (if the project has used this skill before) |

If none exist, the suggested default is `docs/spec/` (create the directory).

### Confirm with the user

Use `AskUserQuestion` to let the user:

- Confirm the suggested location, or
- Pick a different directory, or
- Choose "throwaway" — the doc won't be checked in. Use `.llm/relays/` if a
  `.llm/` directory is already gitignored at the repo root, else
  `/tmp/claude-relays/`.

### Derive the filename

Format: `<slug>-relay.md`. Build `<slug>` in this priority order:

1. **Git branch name**, if not `main` / `master` / `trunk`. Slugify with
   `git rev-parse --abbrev-ref HEAD | tr '/' '-' | tr -c 'a-zA-Z0-9-' '-'`.
   Example: `feature/auth-fix` → `feature-auth-fix`.
2. **Claude session display name**, if the session was named. Check these in
   order and stop at the first hit:
   - The `CLAUDE_SESSION_NAME` env var.
   - The session's display name in `~/.claude/projects/<project>/<sessionId>/`
     metadata, if readable.
3. **Ask the user** for a short slug (3–5 words) if neither signal is
   meaningful.

If both the branch and session name are meaningful and differ, combine them:
`<branch>-<session>-relay.md`. If the resulting file already exists, append
`-2`, `-3`, etc. — never overwrite. Relays are append-only across sessions on
the same branch.

## Step 2: Draft

Read the template at `references/template.md` and fill it in. The template
defines the section order and rules; follow it.

### Ground the draft in facts, not memory

Before writing any claim, verify it against the repo:

- `git log --oneline -20` for recent commits.
- `git status` for uncommitted work.
- `git diff` for active in-flight changes.
- Read existing plan / spec files referenced in conversation.
- Grep for functions or symbols mentioned in "Next steps" to confirm they
  exist at the named paths.

Memory drifts over the course of a session — the git history and filesystem
do not. When memory and the repo disagree, trust the repo and note the
correction in the draft.

### Progressive disclosure

Inline only what isn't already captured somewhere the receiver can read.
Everywhere else, link:

- Plans and specs → `path/to/plan.md`
- Past decisions → commit SHA + short message
- Related work → issue or PR number
- Code locations → `path:line` or `path:start-end`

The receiver has the same tools you do. Their first move after reading the
relay doc will be to follow links — make the links specific.

## Step 3: Review loop

Up to 3 iterations.

### Dispatch the reviewer

Use the `Agent` tool to spawn the `relay-reviewer` subagent. This subagent
runs in a fresh context window — it does not inherit this conversation.

```
Agent(
  subagent_type: "context-relay:relay-reviewer",
  description: "Review relay doc",
  prompt: "Review the relay doc at <absolute-path>. Raise only substantive,
           non-trivial questions a fresh Claude instance couldn't resolve by
           reading the repo itself. Return NO_SUBSTANTIVE_QUESTIONS if the
           doc is sufficient."
)
```

### Evaluate what came back

The reviewer returns either `NO_SUBSTANTIVE_QUESTIONS` or a numbered list.

**If `NO_SUBSTANTIVE_QUESTIONS`** → exit the loop. Proceed to Finalize.

**If the list is non-empty**, judge each question:

- *Substantive* — the answer lives in your head and nowhere else in the repo.
  Example: "Why was approach X chosen over Y?" when both are mentioned but the
  rationale isn't stated.
- *Trivial* — the reviewer could have answered it with Read / Grep / `git log`
  or by following a link the doc already provides.

If every returned question is trivial, the reviewer has hit diminishing
returns. Exit the loop and proceed to Finalize. (This is a judgment call; the
reviewer is expected to self-filter, but residual trivial questions still
sometimes slip through.)

If any questions are substantive, edit the relay doc directly using `Edit`.
Weave the answer into the relevant section — do not append a "Q&A" block at
the bottom. The receiver should read a clean document, not a transcript.

### Iteration cap

Stop after 3 full review rounds regardless of outcome. If the reviewer still
has substantive questions at iteration 3, the remaining uncertainty is likely
a genuine ambiguity in the work itself, not a doc-writing failure. Add a
`## Known uncertainties` section listing the unresolved questions as items
the receiver should confirm with the user before acting on the relevant next
step. Then proceed to Finalize.

## Step 4: Finalize

Print three things to the user:

1. **Absolute path** to the relay doc.
2. **The exact resume prompt**, as a copy-paste block:
   ```
   Read <absolute-path> and continue the work described there.
   ```
3. **Number of review iterations** used (e.g., "2 review rounds; reviewer
   returned NO_SUBSTANTIVE_QUESTIONS on round 3").

Do not mention your own continued work, next steps for this session, or
offer to do more. The relay is a terminal action — the user is about to
/clear or hand off.

## Rules and anti-patterns

- **Verify, don't recite.** `git log` beats memory every time.
- **Link, don't inline.** If a plan doc already captures the decision,
  reference it. Duplication rots.
- **Edit the doc, don't append.** Q&A trails make the doc worse each round.
- **Trust the reviewer, but exercise judgment.** The reviewer is pushy about
  substance by design; residual trivial questions shouldn't derail the loop.
- **Three iterations is a cap, not a floor.** If the reviewer returns
  `NO_SUBSTANTIVE_QUESTIONS` on round 1, stop immediately. Don't manufacture
  questions to justify more rounds.
- **Don't add sections the template doesn't have.** Drift creeps in through
  "just one more helpful section."
- **Absolute paths in the resume prompt.** Relative paths break when the
  receiver cd's into a different directory.

---
name: onboard-codebase
description: Survey a codebase and write ONBOARDING.md (under 100 lines) covering stack, build/test/lint commands, architecture, entry points, and CI/CD. Use when the user asks to be onboarded to a repo, oriented to a new project, or wants their onboarding docs refreshed. Lives beside CLAUDE.md and loads on demand, so orientation doesn't bloat every turn.
---

# onboard-codebase

Produce `ONBOARDING.md` at the repo root: what a fresh reader (human or Claude)
needs to get productive. CLAUDE.md holds evergreen rules; ONBOARDING.md holds
orientation facts, loaded on demand.

## Output

- `ONBOARDING.md` at repo root, **100 lines max**.
- Overflow to `docs/*.md` when a topic needs more than ~15 lines. Link to them from a `## Dig deeper` section at the bottom of ONBOARDING.md.
- CLAUDE.md gets a one-line pointer to ONBOARDING.md. Create a minimal CLAUDE.md if none exists. Never `@`-include ONBOARDING.md -- the whole point is on-demand loading.

## Workflow

```
SURVEY --> SYNTHESIZE --> CHECK LENGTH --> WRITE --> RECONCILE CLAUDE.md
```

## Step 1: Survey

Breadth-first. Glob and Grep, not wholesale reads. You are pointing, not summarizing.

### Always check

- `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md` -- existing guidance usually names the build tool, test runner, entry points
- Top-level directory listing -- names reveal project shape
- `git log --oneline -20` -- what is actively changing

### Language and build (read the manifest)

| File(s) | Language | Build |
|---------|----------|-------|
| `Cargo.toml` | Rust | cargo |
| `package.json` + lockfile | TS/JS | bun / pnpm / npm |
| `pyproject.toml`, `setup.py`, `requirements*.txt` | Python | uv / poetry / pip |
| `go.mod` | Go | go |
| `build.zig(.zon)` | Zig | zig build |
| `Package.swift`, `project.yml` + `*.xcodeproj` | Swift | SwiftPM / Xcode |
| `pom.xml`, `build.gradle(.kts)` | Java / Kotlin | Maven / Gradle |
| `Gemfile` | Ruby | bundler |
| `mix.exs` | Elixir | mix |
| `composer.json` | PHP | composer |

### Task runner (authoritative if present)

If one of these exists, it is the source of truth for build/test/lint/run. Do not write raw-toolchain commands when a task file already defines them.

- `justfile` -- `just --list`
- `Makefile` -- grep targets
- `Taskfile.yml` -- go-task
- `package.json` `"scripts"` -- TS/JS projects without a separate runner

### Test, lint, typecheck

- Test: `pytest.ini`, `jest.config.*`, `vitest.config.*`, `playwright.config.*`; built-in for cargo / go
- Lint: `.eslintrc*`, `ruff.toml`, `clippy.toml`, `.golangci.yml`, `rubocop.yml`, `biome.json`
- Typecheck: `tsconfig.json`, `mypy.ini`, `pyrightconfig.json`, `ty.toml`

### Entry points

- Rust: `src/main.rs`, `src/lib.rs`, `src/bin/*.rs`
- Go: `main.go`, `cmd/*/main.go`
- Python: `__main__.py`, `[project.scripts]` in `pyproject.toml`
- TS/JS: `src/index.*`, `src/main.*`, `"main"` / `"bin"` in `package.json`
- Swift: `@main` annotation
- Web frameworks: `next.config.*`, `vite.config.*`, `nuxt.config.*`, `astro.config.*`

### CI/CD and deploy

- `.github/workflows/*.yml`, `.gitlab-ci.yml`, `.circleci/config.yml`
- `Dockerfile`, `docker-compose*.yml`
- `fly.toml`, `render.yaml`, `vercel.json`, `netlify.toml`, `wrangler.toml`

### Flag, don't guess

If the survey is ambiguous (no test framework, two conflicting ones, README references commands that don't exist), note it plainly. A correct "unknown" beats a confident fabrication.

## Step 2: Synthesize

Template. Drop sections that don't apply. Total under 100 lines.

```markdown
# Onboarding

<2-3 sentences: what this project is and what it does>

## Stack

- Language: <language and version>
- Frameworks: <major frameworks / libraries>
- Build: <tool, e.g. cargo, bun, uv>
- Task runner: <justfile / Makefile / npm scripts> (authoritative)

## Common commands

Use the task runner's actual recipe names. Drop rows the project does not have; do not invent a recipe just to fill the line.

- Build:     `<recipe>`
- Test:      `<recipe>`
- Lint:      `<recipe>`
- Typecheck: `<recipe>`
- Format:    `<recipe>`
- Run:       `<recipe>`

## Architecture

<2-4 sentences: the pieces and how they talk. Omit if docs/architecture.md covers it.>

## Key paths

- `src/main.rs` -- entry point
- `src/lib.rs`  -- public API
- `Cargo.toml`  -- manifest and dependencies
- `tests/`      -- integration tests
- `.github/workflows/` -- CI
- `justfile`    -- task recipes

## How to run

<one or two commands that get it running locally>
```

(Add a `## Dig deeper` section only if Step 3 created `docs/*.md` overflow files. Don't include it by default.)

One fact per line. Every path listed should answer "where does X live?". No preamble, no emojis, no em dashes, no hyperbole.

## Step 3: Complexity check

If the draft is over 100 lines, or any section is sprawling, extract to `docs/`:

| Topic | File |
|-------|------|
| Module / package layout | `docs/architecture.md` |
| Request lifecycle, data flow | `docs/data-flow.md` |
| Build and release pipeline | `docs/build.md` |
| Deployment targets | `docs/deployment.md` |
| Database schema | `docs/schema.md` |
| API surface | `docs/api.md` |

ONBOARDING.md is an index, not a textbook. When you create overflow files, add a `## Dig deeper` section at the bottom of ONBOARDING.md listing them with a one-line description each.

## Step 4: Reconcile with CLAUDE.md

**Use a plain markdown link, not `@`-include.** The whole point of this skill is that ONBOARDING.md loads on demand. If CLAUDE.md `@`-includes it, it gets injected into every turn and the design is defeated. Never write `@ONBOARDING.md`. The pointer text that goes into CLAUDE.md is just:

```markdown
For project orientation (stack, build/test commands, architecture, entry points), see [ONBOARDING.md](./ONBOARDING.md).
```

Do not add "read on demand" or "do not @-include" to CLAUDE.md itself -- those are instructions for you, not for the file.

### If CLAUDE.md exists

1. Add the pointer line near the top if it is not already there.
2. Scan CLAUDE.md for orientation facts that now live in ONBOARDING.md -- sections like "Structure", "Build", "Architecture", "Adding a ...", stack descriptions, command references, key path lists. These belong in ONBOARDING.md, not in both files.
3. Propose an edit that strips those sections from CLAUDE.md, leaving only evergreen rules (policies, conventions like "always use uv", style rules) and the pointer.
4. Show the full diff of both files before writing so the user can approve or reject the CLAUDE.md cleanup.

### If CLAUDE.md does not exist

Create a minimal one: a `# <project-name>` title and the pointer line. Nothing else.

CLAUDE.md is for evergreen rules that apply to every question; ONBOARDING.md is reference material pulled in only when orienting. Each fact should live in exactly one place.

## Refreshing an existing ONBOARDING.md

1. Read the existing file first.
2. Re-survey. Things shift: renamed commands, moved dirs, new CI, dropped deps.
3. Preserve hand-edited commentary that still applies; drop content that is now wrong.
4. Show the diff before writing so the user can flag anything you would have dropped.

## Anti-patterns

- **Reading every source file.** Orientation is pointing, not summarizing.
- **Inventing commands.** If the justfile says `just test`, use that.
- **Padding.** 60 good lines beat 100 mediocre ones.
- **Duplicating CLAUDE.md.** Rules (like "always use uv") belong in CLAUDE.md; facts in ONBOARDING.md.
- **Drift.** When refreshing, fix stale commands and paths. Do not preserve broken content.
- **Inventing how-to sections.** Stick to the template. ONBOARDING.md answers "what is this" and "where do things live", not "how do I do X". Release procedures, contribution steps, and task-specific guides are docs, not orientation.

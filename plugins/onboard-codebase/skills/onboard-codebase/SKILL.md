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
- Overflow to `docs/*.md` when a topic needs more than ~15 lines. Link from "Dig deeper".
- CLAUDE.md gets a one-line pointer to ONBOARDING.md. Create a minimal CLAUDE.md if none exists. Never `@`-include ONBOARDING.md -- the whole point is on-demand loading.

## Workflow

```
SURVEY --> SYNTHESIZE --> CHECK LENGTH --> WRITE --> LINK FROM CLAUDE.md
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

Prefer the task runner. Raw toolchain only when none exists.

- Build:     `just build`
- Test:      `just test`
- Lint:      `just lint`
- Typecheck: `just check`
- Format:    `just fmt`
- Run:       `just run`

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

## Dig deeper

- `docs/architecture.md` -- module graph
- `docs/data-flow.md`    -- request lifecycle
```

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

ONBOARDING.md is an index, not a textbook.

## Step 4: Link from CLAUDE.md

If CLAUDE.md exists, add this line near the top (if not already present):

```markdown
For project orientation (stack, build/test commands, architecture, entry points), see [ONBOARDING.md](./ONBOARDING.md). Read on demand; do not `@`-include.
```

If CLAUDE.md does not exist, create a minimal one with a title and that line.

Never inline ONBOARDING.md into CLAUDE.md, and never `@`-include it. CLAUDE.md is for evergreen rules that apply to every question; ONBOARDING.md is reference material pulled in only when orienting.

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

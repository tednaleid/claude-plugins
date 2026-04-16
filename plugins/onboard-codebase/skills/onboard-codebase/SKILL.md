---
name: onboard-codebase
description: Survey an unfamiliar codebase and generate a concise ONBOARDING.md (under 100 lines) covering language, frameworks, build/test/lint commands, high-level architecture, entry points, and CI/CD. Use whenever the user says "onboard me to this codebase", "orient me to this repo", "I'm new to this project", "help me understand this codebase", "survey this project", or asks for onboarding documentation. Also use to refresh an existing ONBOARDING.md after the project has changed. Keeps CLAUDE.md focused on evergreen rules by parking orientation facts in a separate file loaded on demand.
---

# onboard-codebase

Generate a lean onboarding guide for a fresh reader (human or Claude) meeting
this codebase for the first time. The point of the skill is progressive
disclosure: CLAUDE.md holds evergreen project rules, ONBOARDING.md holds
orientation facts that only get pulled in when someone needs them.

## What to produce

Primary output: `ONBOARDING.md` at the repo root, **at most 100 lines**.

If the project is complex enough that 100 lines can't cover it, split detail
into `docs/*.md` files (create the directory if needed) and link from
ONBOARDING.md. A good signal: if you're drafting more than roughly 15 lines on
a single topic (request flow, module graph, deployment), extract it.

Secondary output: ensure `CLAUDE.md` has a one-line pointer to `ONBOARDING.md`.
Create a minimal `CLAUDE.md` only if none exists. Never `@`-include
`ONBOARDING.md` from CLAUDE.md -- the whole point is that it's loaded on
demand, not every turn.

## Workflow

```
SURVEY --> SYNTHESIZE --> CHECK LENGTH --> WRITE --> LINK FROM CLAUDE.md
```

## Step 1: Survey

The goal is "enough to draft a useful orientation", not "read every file".
Survey breadth-first. Prefer Glob and Grep over wholesale file reads. You do
not need to understand the code to orient someone; you need to point them at
the right starting places.

### Always check

- `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md` -- existing
  guidance usually names the build tool, test runner, and entry points
- Top-level directory listing -- directory names reveal the project's shape
- Recent commits (`git log --oneline -20`) -- signals what is actively changing

### Language and build system

Read the primary manifest at minimum. It tells you language version, direct
dependencies, and often scripts or task aliases.

| File(s) | Language | Build / package |
|---------|----------|-----------------|
| `Cargo.toml` | Rust | cargo |
| `package.json` + `bun.lockb` / `pnpm-lock.yaml` / `package-lock.json` | TS/JS | bun / pnpm / npm |
| `pyproject.toml`, `setup.py`, `requirements*.txt` | Python | uv / poetry / pip (check lock) |
| `go.mod` | Go | go |
| `build.zig`, `build.zig.zon` | Zig | zig build |
| `Package.swift`, `project.yml` + `*.xcodeproj` | Swift | SwiftPM / Xcode |
| `pom.xml`, `build.gradle(.kts)` | Java / Kotlin | Maven / Gradle |
| `Gemfile` | Ruby | bundler |
| `mix.exs` | Elixir | mix |
| `composer.json` | PHP | composer |

### Task runner (authoritative when present)

If one of these exists, it is the source of truth for build / test / lint /
run commands. Do not infer raw-toolchain commands when a task file already
defines them.

- `justfile` / `.justfile` -- run `just --list` to enumerate recipes
- `Makefile` -- grep targets
- `Taskfile.yml` -- go-task
- `package.json` `"scripts"` block -- for TS/JS projects without a separate runner

### Test, lint, typecheck

- Test config: `pytest.ini`, `jest.config.*`, `vitest.config.*`, `playwright.config.*`, presence of `cargo test`, `go test ./...`
- Lint: `.eslintrc*`, `ruff.toml` / `.ruff.toml`, `clippy.toml`, `.golangci.yml`, `rubocop.yml`, `biome.json`
- Typecheck: `tsconfig.json`, `mypy.ini`, `pyrightconfig.json`, `ty.toml`

### Entry points

- Rust: `src/main.rs`, `src/lib.rs`, `src/bin/*.rs`
- Go: `main.go`, `cmd/*/main.go`
- Python: `__main__.py`, `src/{pkg}/cli.py`, `[project.scripts]` in `pyproject.toml`
- TS/JS: `src/index.*`, `src/main.*`, `bin/*`, and the `"main"` / `"bin"` fields in `package.json`
- Swift: `@main` annotation, `App.swift`
- Web frameworks: `next.config.*`, `vite.config.*`, `nuxt.config.*`, `astro.config.*`

### CI / CD and deploy

- `.github/workflows/*.yml` -- GitHub Actions
- `.gitlab-ci.yml` -- GitLab CI
- `.circleci/config.yml` -- CircleCI
- `Dockerfile`, `docker-compose*.yml` -- container build or local stack
- `fly.toml`, `render.yaml`, `vercel.json`, `netlify.toml`, `wrangler.toml` -- deploy targets

### Flag, don't guess

If something isn't clear from the survey (no test framework detected, two
conflicting ones, README references commands that don't exist), note it
plainly in ONBOARDING.md rather than inventing a plausible answer. A correct
"unknown" is more useful than a confident fabrication.

## Step 2: Synthesize

Use this template. Drop sections that don't apply. Keep the total file under
100 lines.

```markdown
# Onboarding

<2-3 sentences: what this project is, who it is for, what it does>

## Stack

- Language: <language and version from the toolchain file>
- Frameworks: <major frameworks / libraries>
- Build: <tool, e.g. cargo, bun, uv>
- Task runner: <justfile / Makefile / npm scripts> (authoritative)

## Common commands

Prefer the task runner. If none exists, fall back to raw toolchain.

- Build:     `just build`
- Test:      `just test`
- Lint:      `just lint`
- Typecheck: `just check`
- Format:    `just fmt`
- Run:       `just run`

## Architecture

<2-4 sentences: the pieces and how they talk. Omit if docs/architecture.md covers this.>

## Key paths

- `src/main.rs` -- entry point
- `src/lib.rs`  -- public API
- `Cargo.toml`  -- manifest and dependencies
- `tests/`      -- integration tests (unit tests live alongside source)
- `.github/workflows/` -- CI (lint, test, release)
- `justfile`    -- task recipes

## How to run

<one or two commands that get the app running locally>

## Dig deeper

- `docs/architecture.md` -- module graph and boundaries
- `docs/data-flow.md`    -- request lifecycle
```

Style notes for the body of ONBOARDING.md:

- One fact per line. The reader should scan, not read.
- Every path listed should answer a likely question ("where does X live?").
- Don't restate what's obvious from `ls` at the repo root.
- Skip preamble like "This document describes..." -- go straight to content.
- No emojis, em dashes, or hyperbole.

## Step 3: Complexity check

Count the lines in your draft. If ONBOARDING.md would be over 100 lines, or
any single section is sprawling, extract detail into `docs/`:

| Topic | Candidate file |
|-------|----------------|
| Module / package layout | `docs/architecture.md` |
| Request lifecycle, data flow | `docs/data-flow.md` |
| Build and release pipeline | `docs/build.md` |
| Deployment targets and environments | `docs/deployment.md` |
| Database schema | `docs/schema.md` |
| API surface | `docs/api.md` |

Link from ONBOARDING.md's "Dig deeper" section. ONBOARDING.md should behave
like an index, not a textbook.

## Step 4: Link from CLAUDE.md

Open `CLAUDE.md`. If it exists, add (or verify) a pointer near the top:

```markdown
For project orientation (stack, build/test commands, architecture, entry points), see [ONBOARDING.md](./ONBOARDING.md). Read on demand; do not `@`-include.
```

If `CLAUDE.md` does not exist, create a minimal one:

```markdown
# <project-name>

For project orientation (stack, build/test commands, architecture, entry points), see [ONBOARDING.md](./ONBOARDING.md). Read on demand; do not `@`-include.
```

Do not inline ONBOARDING.md's content into CLAUDE.md, and do not `@`-include
it. CLAUDE.md is for evergreen rules that apply to every question in the repo;
ONBOARDING.md is reference material that only matters when orienting.

## Re-running on an existing ONBOARDING.md

If `ONBOARDING.md` already exists, treat this run as a refresh, not a rewrite:

1. Read the existing file first so you know what was there.
2. Re-survey the codebase. State may have changed -- new commands, renamed
   dirs, new CI, dropped dependencies.
3. Produce an updated version. Preserve hand-edited commentary that still
   applies; drop content that is now wrong.
4. Show the diff before writing so the user can flag anything you would have
   dropped unintentionally.

## Anti-patterns

- **Reading every source file.** Use Glob and Grep. Orientation is about
  pointing, not summarizing.
- **Inventing commands.** If the justfile says `just test`, use that. Do not
  write `cargo test` as a "friendlier alternative".
- **Padding.** 60 good lines beat 100 mediocre ones. If a section just
  restates the manifest, cut it.
- **Duplicating CLAUDE.md.** ONBOARDING.md is orientation facts. CLAUDE.md is
  rules. "Always use uv, never pip" is a rule and belongs in CLAUDE.md.
- **Drift.** If you spot stale commands or paths while re-running, fix them.
  Do not preserve obviously broken content just because it was there before.

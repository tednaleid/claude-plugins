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
- CLAUDE.md gets a one-line markdown link to ONBOARDING.md, not its content. Create a minimal CLAUDE.md if none exists.

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

The output shape (total under 100 lines):

```markdown
# Onboarding

<summary paragraph>

## Stack
- Language:
- Frameworks:
- Build:
- Task runner:

## Common commands
- Build:
- Test:
- Lint:
- Typecheck:
- Format:
- Run:

## Architecture
<architecture paragraph>

## Key paths
- <path> -- <one-line role>

## How to run
<one or two commands>

## Dig deeper
- <path> -- <one-line role>
```

How to fill it:

**One rule applies to every section that shows a command: if a task runner recipe exists for that command, show only the recipe.** Never pair it with the raw toolchain command as an alternative, fallback, or trailing comment. The raw command does not appear anywhere in the file when a recipe exists. This rule overrides the natural tendency to be "helpful" by showing both.

Wrong:

```
bun install          # or: just install
npm test             (alternative: just test)
```

Right:

```
just install
just test
```

- **Project summary.** 2-3 sentences. What it is and what it does. No marketing.
- **Stack.** From the manifest. Mark the task runner as authoritative if there is one.
- **Common commands.** Use the task runner's actual recipe names. Drop rows the project has no recipe for; do not invent one to fill the line. If no task runner exists, fall back to raw toolchain for what actually exists.
- **Architecture.** 2-4 sentences on the pieces and how they talk. Omit if `docs/architecture.md` covers it.
- **Key paths.** Each entry answers "where does X live?". Skip paths a newcomer can find with `ls`.
- **How to run.** Omit if the project is not a runnable app (library, plugin distribution, config repo).
- **Dig deeper.** Links to further reading: existing top-level docs (README.md, TESTING.md, CONTRIBUTING.md, `adr/`), `docs/*.md` overflow created in Step 3, design specs, adjacent skills, architecture diagrams. Omit the section when there is nothing worth linking.

Drop any section whose content would be empty or forced. Do not add sections beyond the shape above. One fact per line. No preamble, emojis, em dashes, or hyperbole.

## Step 3: Complexity check

If the draft is over 100 lines, or any section is sprawling, find a home for the overflow.

Check existing docs first. If the project already has a top-level doc that covers the topic (README.md, TESTING.md, DESKTOP-APP.md, CONTRIBUTING.md, `adr/*.md`, etc.), link it from `Dig deeper` rather than creating a parallel `docs/*.md`. Do not fragment documentation by duplicating what existing docs already say.

Only when no existing doc covers the topic, create a new overflow file under `docs/`:

| Topic | File |
|-------|------|
| Module / package layout | `docs/architecture.md` |
| Request lifecycle, data flow | `docs/data-flow.md` |
| Build and release pipeline | `docs/build.md` |
| Deployment targets | `docs/deployment.md` |
| Database schema | `docs/schema.md` |
| API surface | `docs/api.md` |

ONBOARDING.md is an index, not a textbook. Link any overflow files from the `Dig deeper` section.

## Step 4: Reconcile with CLAUDE.md

The pointer text that goes into CLAUDE.md is one line:

```markdown
For project orientation (stack, build/test commands, architecture, entry points), see [ONBOARDING.md](./ONBOARDING.md).
```

### If CLAUDE.md exists

1. Add the pointer near the top if it is not already there.
2. Check headings. Any CLAUDE.md section whose heading or content overlaps a section you drafted in ONBOARDING.md (Stack, Structure, Build, Architecture, Key paths, Adding a ..., command references, stack descriptions) is orientation, not rule.
3. Move that content: fold it into the matching ONBOARDING.md section so nothing is lost, then delete it from CLAUDE.md.
4. What stays in CLAUDE.md: evergreen rules only -- policies, style constraints, architectural principles. Nothing that describes what the project IS or HOW to operate it.
5. Reconcile first, write second. "Left it alone because it felt evergreen" is not an acceptable outcome. When a section is borderline, make your best call based on rules 2-4; git diff is the user's review channel. After writing, briefly summarize what moved and what stayed.

### If CLAUDE.md does not exist

Create one with a `# <project-name>` title and the pointer line. Nothing else.

Each fact should live in exactly one file.

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

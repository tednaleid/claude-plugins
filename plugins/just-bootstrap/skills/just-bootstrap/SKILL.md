---
name: just-bootstrap
description: Audit and set up CI, release, Justfile, and Homebrew infrastructure for any repo. Detects language (Rust, Zig, Swift, TypeScript/Bun) and project type (CLI, macOS app) automatically. Use this whenever the user mentions CI setup, release automation, homebrew tap, justfile recipes, bump/retag commands, pre-commit hooks, or wants to normalize build infrastructure across projects. Also use when the user asks about GitHub Actions workflows for building, testing, or releasing their project.
---

# just-bootstrap

Audit a repo's build/release infrastructure and generate what's missing,
normalized to battle-tested patterns from production projects.

## Workflow

```
DETECT --> AUDIT --> CHECKLIST --> GENERATE --> VERIFY --> SUGGEST
```

Work through each step in order. Do not skip detection or audit.

## Step 1: Detection

Read the repo to determine language, project type, and existing conventions.
This drives all downstream decisions.

### Detection Signals

Check for these files at the repo root:

| File | Language | Build System |
|------|----------|-------------|
| `Cargo.toml` | Rust | Cargo |
| `build.zig.zon` | Zig | zig build |
| `project.yml` + `*.xcodeproj` | Swift | Xcode via XcodeGen |
| `Package.swift` | Swift | Swift Package Manager |
| `package.json` + `bun.lockb` | TypeScript | Bun |
| `package.json` + `package-lock.json` | TypeScript | npm |

### Project Type

Determine CLI vs macOS app -- this affects homebrew (formula vs cask) and
whether Apple code signing is relevant:

- **macOS app**: `project.yml` with app target, or `Info.plist` with `CFBundleIdentifier`
- **CLI**: everything else (Rust, Zig, TypeScript CLIs, libraries)

### Existing Conventions

Gather these before generating anything:

1. **Tag prefix**: run `git tag -l` and check existing tags. If tags use `v`
   prefix (e.g., `v1.2.3`), preserve that. If bare (e.g., `1.2.3`), preserve
   that. If no tags exist, default to `v` prefix.

2. **Version file locations**: varies by language.
   - Rust: `Cargo.toml` (`version = "x.y.z"`)
   - Zig: `build.zig.zon` (`version = "x.y.z"`) + `src/main.zig` (`const version = "x.y.z"`)
   - Swift macOS: `Resources/Info.plist` (`CFBundleShortVersionString`)
   - TypeScript/Bun: `package.json` (`version`), possibly multiple packages

3. **GitHub owner/repo**: extract from `git remote get-url origin`.

4. **Current version**: extract from the canonical version file.

Record all detection results before proceeding to the audit.

## Step 2: Audit

Check each concern and classify as present, partial, or missing.

### Concerns to Audit

**Justfile**: Does a `justfile` or `Justfile` exist? If yes, which of these
standard recipes are present: `check`, `test`, `lint`, `fmt`, `build`,
`install`, `clean`, `bump`, `retag`, `install-hooks`?

**CI workflow**: Does `.github/workflows/ci.yml` exist? Does it use `just check`
(or install just + call `just check`)? If CI runs individual commands (e.g.,
`cargo test` + `cargo clippy` separately instead of `just check`), classify as
**partial** -- individual commands can drift from the justfile's `check` recipe,
meaning local checks and CI checks diverge silently.

**Release workflow**: Does `.github/workflows/release.yml` exist? Does it
build for multiple platforms? Does it create a GitHub release? Does it use
`--notes-from-tag` (or equivalent) for release notes? Does it update a
homebrew tap? Also check: are `actions/*` versions current (v5 for checkout
and artifacts)? Are there redundant test/lint jobs that duplicate what CI
already runs?

**Homebrew**: Does `scripts/setup-homebrew-tap.sh` exist? Is there a homebrew
tap update step in the release workflow? For CLIs, this means a formula. For
macOS apps, a cask.

**Bump recipe**: Does a bump recipe exist in the justfile? Does it create
annotated tags (not lightweight)? Does it generate release notes via
`claude -p` (with fallback)?

**Retag recipe**: Does a retag recipe exist? Does it preserve the existing
tag annotation before deleting and recreating?

**Pre-commit hook**: Does an `install-hooks` recipe exist in the justfile?
Does `.git/hooks/pre-commit` exist?

**CLAUDE.md**: Does the project's CLAUDE.md mention CI commands, testing
workflow (red/green), or `just check`?

### Classification

- **[x] Present**: fully matches the normalized pattern
- **[~] Partial**: exists but is missing key features (e.g., bump exists but
  uses lightweight tags, or release workflow exists but doesn't update homebrew)
- **[ ] Missing**: does not exist at all

## Step 3: Present Checklist

Display the audit results as a formatted checklist, then use `AskUserQuestion`
with `multiSelect: true` to let the user pick what to set up or upgrade.

**Example format:**

```
## Infrastructure Audit: {project} ({language} {type})

[x] Justfile         -- present (check, test, lint, fmt, build, install, clean, bump, retag)
[x] CI workflow       -- present (.github/workflows/ci.yml)
[~] Release workflow  -- PARTIAL (builds + releases, but no homebrew update)
[ ] Homebrew tap      -- MISSING
[~] Bump recipe       -- PARTIAL (uses lightweight tags, no Claude release notes)
[~] Retag recipe      -- PARTIAL (does not preserve tag annotations)
[ ] Pre-commit hook   -- MISSING
[x] CLAUDE.md         -- present (has CI/testing section)
```

For the AskUserQuestion, list each missing or partial item as a selectable
option. Include a "Set up all missing/partial items" option as the first
choice for convenience.

## Step 4: Generate

For each selected item, read the corresponding reference file from
`references/` and generate the appropriate files. Generate in dependency order:

1. **Justfile** (read `references/justfile.md`) -- other recipes depend on this
2. **CI workflow** (read `references/ci.md`) -- uses `just check`
3. **Release workflow** (read `references/release.md`) -- uses tag trigger
4. **Homebrew** (read `references/homebrew.md`) -- setup script + release integration
5. **Bump + retag** (read `references/bump.md`) -- creates tags that trigger release
6. **Pre-commit hook** (read `references/pre-commit.md`) -- runs `just check`

### Generation Rules

When reading a reference file, find the section for the detected language and
adapt the template by filling in:
- `{OWNER}` -- GitHub username (e.g., `tednaleid`)
- `{REPO}` -- repository name (e.g., `veer`)
- `{BINARY_NAME}` -- the executable name (e.g., `veer`)
- `{DESC}` -- one-line project description (from README or ask user)
- `{TAG_PREFIX}` -- `v` or empty string, based on detection
- `{VERSION}` -- current version string

When modifying an existing justfile, preserve all existing recipes. Add new
recipes or replace partial ones. Match the indentation and style of the
existing file.

When modifying an existing release workflow, add the homebrew update steps
rather than rewriting the whole file. Preserve existing build matrix and
packaging steps if they work.

### GitHub Actions Versions

When modifying existing workflows, upgrade all `actions/*` references to match
the versions in the reference templates. Currently:
- `actions/checkout@v5`
- `actions/upload-artifact@v5`
- `actions/download-artifact@v5`
- `actions/cache@v4`
- `extractions/setup-just@v3`

Old action versions cause real bugs (e.g., v4 checkout has issues with
annotated tag fetching). This is not optional -- always upgrade.

### Redundant Jobs in Release Workflows

If a release workflow contains a standalone test/lint job that duplicates what
the CI workflow already runs on push/PR, remove it. Release workflows should
focus on building, packaging, and publishing. Testing belongs in CI. If the
release workflow currently has a redundant test job, flag it in the audit as
part of the release workflow being partial, and remove it when generating.

### Bump and Retag Convention

Both `just bump` and `just retag` always accept a **bare version number**
(e.g., `just bump 1.2.3`), never with a tag prefix. The recipe adds the
prefix internally based on the project's convention. This is non-negotiable
and must be consistent across all languages.

### CLAUDE.md Updates

After generating infrastructure, check the project's CLAUDE.md. If it doesn't
already cover these, add a brief section:

```markdown
## Build and Test

- `just check` -- run all tests, linting, and type checking (used by CI)
- `just test` -- run tests only
- `just lint` -- run linter only
- `just clean` -- remove build artifacts and caches (use this, never bare rm -rf)
- `just bump` -- bump version, generate release notes, tag, and push
- `just retag` -- re-trigger release workflow for an existing version

Red/green testing: write a failing test before implementing, then make it pass.
All commits should pass `just check`.
```

Keep it brief. Don't duplicate what's already documented.

## Step 5: Verify

After generation, verify the changes work:

1. Run `just check` (if the justfile was modified or created)
2. If a new CI workflow was created, suggest: "Push a branch to verify the
   CI workflow runs successfully."
3. If homebrew was set up, remind the user to run the setup script and
   configure the HOMEBREW_TAP_TOKEN secret before the first release.

## Step 6: Suggest Optional Enhancements

After the main generation is complete, briefly suggest enhancements that make
sense for the detected project type. These are not generated -- just mentioned
as things the user might want to add later:

- **Coverage badges** -- useful for TypeScript/Bun projects with vitest or
  jest coverage. Uses a GitHub Gist + dynamic badge action.
- **Binary size checks** -- useful for Zig and Rust CLIs where small binary
  size is a goal. Adds a CI job that fails if the binary exceeds a threshold.
- **Benchmark CI runs** -- useful for projects with benchmark suites (cargo
  bench, zig build bench). Runs benchmarks on release tags and archives results.
- **Dependency update bots** -- useful for projects with submodules or
  lockfiles. Creates a workflow that checks for updates on a schedule and
  opens a PR.

Only suggest enhancements that are relevant. A TypeScript web app doesn't
need binary size checks. A Zig CLI without benchmarks doesn't need benchmark
CI.

## Bundled Resources

### References

Read these on demand during Step 4 (Generate). Each file contains complete,
copy-paste-ready templates organized by language with parameterized
placeholders.

- `references/justfile.md` -- Standard Justfile recipes per language
- `references/ci.md` -- GitHub Actions CI workflow templates
- `references/release.md` -- GitHub Actions release workflow templates
- `references/homebrew.md` -- Homebrew formula/cask templates, setup script, release integration
- `references/bump.md` -- Bump and retag Justfile recipe templates
- `references/pre-commit.md` -- install-hooks recipe

### Examples

- `examples/audit-output.md` -- Example audit checklist for a Zig CLI project

## Important Notes

- Every project must have a `just clean` recipe for removing build artifacts,
  caches, and generated files. Never use bare `rm -rf` commands -- always use
  `just clean` instead. This keeps destructive operations auditable, safe, and
  consistent. The clean recipe should remove only project-local artifacts (build
  output, caches inside the project), never global or user-level directories.
- No secrets are stored in generated files. All secrets (HOMEBREW_TAP_TOKEN,
  APPLE_CERTIFICATE, etc.) live in GitHub's encrypted secrets and are
  referenced only by name in workflow YAML.
- Bump and retag always take bare version numbers. The recipe adds the tag
  prefix. This is normalized across all languages.
- When upgrading partial infrastructure, preserve existing functionality.
  Add to what's there rather than rewriting from scratch.
- The homebrew setup script is a one-time operation. It creates the tap repo
  and prints instructions for the user to create a fine-grained PAT. The
  release workflow then uses that PAT (stored as HOMEBREW_TAP_TOKEN) to push
  formula/cask updates automatically.

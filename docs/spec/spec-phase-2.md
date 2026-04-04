# Spec: Phase 2 -- Reference Templates

**Contract**: ./contract.md
**Estimated Effort**: L

## Technical Approach

Write all 6 reference files containing complete, copy-paste-ready templates
for each supported language. These are the "heavy content" that SKILL.md
points to. Each file is organized by concern with language-specific sections.

Templates are derived from actual working configurations in sumpig (Rust),
veer (Zig), montty (Swift macOS app), and limn (TypeScript/Bun). They use
parameterized placeholders (OWNER, REPO, BINARY_NAME, DESC) that the skill
fills in from detection results.

## New Files

| File | Purpose |
|------|---------|
| `references/justfile.md` | Justfile recipe templates per language |
| `references/ci.md` | GitHub Actions CI workflow templates |
| `references/release.md` | GitHub Actions release workflow templates |
| `references/homebrew.md` | Formula + Cask + setup script + release integration |
| `references/bump.md` | Bump + retag Justfile recipes |
| `references/pre-commit.md` | install-hooks recipe |

All paths relative to `plugins/just-bootstrap/skills/just-bootstrap/`.

## Implementation Details

### references/justfile.md

Standard recipe set for each language. Every language gets: check, test, lint,
fmt, build, install. The `test` recipe accepts an optional argument for running
individual tests where the language supports it.

**Source patterns:**
- Rust: `../sumpig/justfile` -- check, test, lint (clippy), fmt, fmt-check, build, install
- Zig: `../veer/justfile` -- check, test, lint (zig fmt --check), fmt, build, release, install
- Swift macOS: `../montty/justfile` -- check (test+lint+build), test, lint (swiftlint), generate, build
- TypeScript/Bun: `../limn/justfile` -- check (coverage+lint+typecheck), test, lint, typecheck, build

Include a table mapping recipe names to concrete commands per language.
Note that bump, retag, and install-hooks are covered in their own reference files.

### references/ci.md

Complete GitHub Actions CI workflow YAML per language. Each workflow:
- Triggers on push to main + pull requests
- Uses `just check` as the primary CI command
- Installs language toolchain + just

**Key details per language:**
- Rust: `dtolnay/rust-toolchain@stable`, runs on ubuntu + macos matrix
- Zig: `mlugg/setup-zig@v2` with pinned version, ubuntu-latest
- Swift macOS: `macos-26` runner, `taiki-e/install-action@v2` (just), brew install swiftlint + xcodegen
- TypeScript/Bun: `oven-sh/setup-bun@v2`, `taiki-e/install-action@v2` (just), ubuntu-latest

### references/release.md

Complete release workflow YAML. Two major variants:

**CLI release (Rust, Zig):**
- Trigger: tag push `v*`
- Build matrix with cross-compile targets
- Package as tar.gz per target
- Create GitHub release with `gh release create --notes-from-tag`
- Homebrew formula update (conditional on HOMEBREW_TAP_TOKEN)

**macOS app release (Swift):**
- Trigger: tag push matching version pattern
- Single macos-26 runner
- Build release configuration
- Conditional Apple code signing + notarization
- DMG creation via hdiutil
- GitHub release upload
- Homebrew cask update (conditional on HOMEBREW_TAP_TOKEN)

**Source patterns:**
- Rust CLI: `../sumpig/.github/workflows/release.yml`
- Zig CLI: `../veer/.github/workflows/release.yml` (needs homebrew addition)
- Swift macOS: `../montty/.github/workflows/release.yml`
- TypeScript/Bun: `../limn/.github/workflows/release.yml` + `release-desktop.yml`

### references/homebrew.md

Four sections:

1. **Formula template** (for CLI binaries) -- Ruby with platform/arch conditionals
   - Source: sumpig Formula/sumpig.rb pattern
   - Supports: macOS arm64 + x86_64, Linux x86_64

2. **Cask template** (for macOS apps) -- Ruby cask with DMG URL
   - Source: montty Casks/montty.rb pattern
   - Includes zap trash paths

3. **Setup script template** -- Parameterized bash script
   - Source: `../sumpig/scripts/setup-homebrew-tap.sh` and `../montty/scripts/setup-homebrew-tap.sh`
   - Parameters: OWNER, TAP_REPO, MAIN_REPO, BINARY_NAME, DESC, IS_CASK
   - Creates tap repo, seeds formula/cask, prints PAT instructions

4. **Release workflow integration** -- The SHA-256 + tap update steps
   - Formula variant: compute SHA per platform, generate Formula/NAME.rb
   - Cask variant: compute DMG SHA, generate Casks/NAME.rb

### references/bump.md

Complete bump and retag recipe bodies for each language.

**Bump recipe pattern (all languages):**
1. Extract current version from canonical source
2. Compute new version (patch increment default, explicit version argument)
3. Update all version files
4. git add + commit
5. Generate release notes (claude -p with fallback)
6. Create annotated tag with notes
7. Push commits + tags

**Retag recipe pattern (universal):**
1. Save existing annotation
2. Delete GitHub release + remote tag + local tag
3. Recreate annotated tag from saved notes
4. Push

Both recipes always take bare version numbers (no v prefix).

**Language-specific version file handling:**
- Rust: sed Cargo.toml, cargo generate-lockfile
- Zig: sed build.zig.zon + src/main.zig
- Swift: PlistBuddy on Info.plist
- TypeScript/Bun: may need external script for multiple version files

**Source patterns:**
- Rust: `../sumpig/justfile` lines 46-98
- Zig: current `../veer/justfile` lines 81-106 (needs upgrade to annotated tags)
- Swift: `../montty/justfile` bump/retag recipes
- TypeScript/Bun: `../limn/justfile` + `../limn/scripts/bump-version.ts`

### references/pre-commit.md

Simple `install-hooks` recipe that creates `.git/hooks/pre-commit` running
`just check`. Universal across all languages.

**Source pattern:** `../limn/justfile` install-hooks recipe

## Validation

1. Verify each reference file has sections for all supported languages
2. Verify YAML templates are syntactically valid
3. Verify parameterized placeholders are consistently named
4. Verify all source pattern file paths are correct
5. Cross-check that SKILL.md references match the actual file names

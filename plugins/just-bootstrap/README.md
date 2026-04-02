# just-bootstrap

Audit and set up CI, release, Justfile, and Homebrew infrastructure for any
repo. Detects language and project type automatically and generates normalized
build/release tooling.

## Usage

```
/just-bootstrap
```

The skill will:
1. Detect your language, build system, and project type
2. Audit what infrastructure exists vs what's missing
3. Present a checklist and let you pick what to set up
4. Generate the selected components
5. Verify everything works

## What It Sets Up

- **Justfile** -- check, test, lint, fmt, build, install, bump, retag, install-hooks
- **CI workflow** -- GitHub Actions running `just check` on push/PR
- **Release workflow** -- Cross-platform builds, GitHub releases, homebrew updates
- **Homebrew** -- Formula (CLI) or Cask (macOS app) with tap setup script
- **Bump/retag** -- Version bumping with Claude-generated release notes and annotated tags
- **Pre-commit hooks** -- `just install-hooks` to run `just check` before each commit

## Language Support

Successfully tested with Rust, Zig, Swift, TypeScript/Bun, Go, and Python, but
should work with almost any language. The skill detects your build system and
adapts its output accordingly.

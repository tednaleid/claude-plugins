# CI Workflow Templates

GitHub Actions CI workflows that run on every push and pull request. Each
workflow uses `just check` as the primary command, ensuring CI runs the same
checks as local development.

## Table of Contents

- [Rust (Cargo)](#rust-cargo)
- [Zig](#zig)
- [Swift macOS App](#swift-macos-app)
- [TypeScript/Bun](#typescriptbun)

---

## Rust (Cargo)

Runs on both Ubuntu and macOS. Uses the official Rust toolchain action.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  check:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v5
      - uses: dtolnay/rust-toolchain@stable
      - run: cargo test
      - run: cargo clippy -- -D warnings
      - run: cargo fmt -- --check
```

**Notes:**
- Runs on both platforms because Rust cross-compilation can have
  platform-specific issues
- Uses `dtolnay/rust-toolchain@stable` for reliable toolchain setup
- Runs individual commands rather than `just check` because `just` is not
  pre-installed on GitHub runners. Alternative: add `extractions/setup-just@v3`
  and use `just check`

### With Just (alternative)

If you prefer `just check` for consistency with local dev:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  check:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v5
      - uses: dtolnay/rust-toolchain@stable
      - uses: extractions/setup-just@v3
      - run: just check
```

---

## Zig

Runs on Ubuntu. Uses `mlugg/setup-zig` with a pinned version.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: mlugg/setup-zig@v2
        with:
          version: {ZIG_VERSION}
      - uses: extractions/setup-just@v3
      - run: just check
```

Replace `{ZIG_VERSION}` with the project's pinned Zig version (e.g., `0.15.2`).
Check `build.zig.zon` or `CLAUDE.md` for the required version.

**Notes:**
- Zig has excellent cross-compilation, so a single Ubuntu runner is sufficient
  for CI (release builds still cross-compile on multiple targets)
- `mlugg/setup-zig@v2` caches the Zig compiler
- The `just check` recipe runs `zig build test` + `zig fmt --check`

---

## Swift macOS App

Runs on macOS only (required for Xcode). May need caching for expensive
framework builds.

### Simple (no heavy dependencies)

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  check:
    runs-on: macos-26
    steps:
      - uses: actions/checkout@v5
      - uses: extractions/setup-just@v3
      - name: Install SwiftLint and xcodegen
        run: brew install swiftlint xcodegen
      - name: Generate Xcode project
        run: just generate
      - name: Check (test + lint + build)
        run: just check
```

### With framework caching (e.g., submodule-built xcframework)

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  check:
    runs-on: macos-26
    steps:
      - uses: actions/checkout@v5
        with:
          submodules: recursive

      - uses: extractions/setup-just@v3

      - name: Cache {FRAMEWORK_NAME}
        id: cache-framework
        uses: actions/cache@v4
        with:
          path: |
            {FRAMEWORK_CACHE_PATHS}
          key: {FRAMEWORK_NAME}-${{ hashFiles('{CACHE_KEY_FILE}') }}

      - name: Build {FRAMEWORK_NAME}
        if: steps.cache-framework.outputs.cache-hit != 'true'
        run: just setup

      - name: Install SwiftLint and xcodegen
        run: brew install swiftlint xcodegen

      - name: Generate Xcode project
        run: just generate

      - name: Check (test + lint + build)
        run: just check
```

**Notes:**
- `macos-26` is the current latest macOS runner
- SwiftLint and xcodegen are installed via Homebrew in CI
- `just generate` must run before `just check` (generates .xcodeproj)
- Framework caching is only needed for projects with expensive submodule
  builds (e.g., Ghostty xcframework). Skip for simple projects.

**Placeholders:**
| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{FRAMEWORK_NAME}` | Name of cached framework | `GhosttyKit` |
| `{FRAMEWORK_CACHE_PATHS}` | Paths to cache (multiline) | `ghostty/macos/GhosttyKit.xcframework` |
| `{CACHE_KEY_FILE}` | File whose hash keys the cache | `.git/modules/ghostty/HEAD` |

---

## TypeScript/Bun

Runs on Ubuntu. Uses the official Bun setup action.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: oven-sh/setup-bun@v2
      - uses: extractions/setup-just@v3
      - run: just install
      - run: just check
```

**Notes:**
- `just install` runs `bun install` to set up dependencies before checks
- `just check` runs tests + lint + typecheck
- No macOS runner needed -- TypeScript is platform-independent for CI
- If using npm instead of bun, replace `oven-sh/setup-bun@v2` with
  `actions/setup-node@v4`

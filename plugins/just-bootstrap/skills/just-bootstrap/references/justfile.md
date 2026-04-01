# Justfile Recipe Templates

Standard recipes for each supported language. Every project gets a consistent
set of recipes that work the same way. The `check` recipe is the main entry
point -- it runs everything CI checks, and is used by both CI and pre-commit.

Every project must have a `clean` recipe for removing build artifacts and
caches. This replaces any bare `rm -rf` usage -- destructive cleanup should
always go through `just clean` so it's auditable and safe.

Bump, retag, and install-hooks recipes are in their own reference files
(`bump.md` and `pre-commit.md`).

## Table of Contents

- [Rust (Cargo)](#rust-cargo)
- [Zig](#zig)
- [Swift macOS App](#swift-macos-app)
- [TypeScript/Bun](#typescriptbun)

---

## Rust (Cargo)

```just
# Install required toolchain components
setup:
    rustup component add clippy rustfmt

# Run all checks (test + lint + format)
check: test lint fmt-check

# Run all tests
test *ARGS:
    cargo test {{ARGS}}

# Run clippy lints (warnings are errors)
lint:
    cargo clippy -- -D warnings

# Format code
fmt:
    cargo fmt

# Check formatting without modifying
fmt-check:
    cargo fmt -- --check

# Build release binary
build:
    cargo build --release

# Install to ~/.cargo/bin
install:
    cargo install --path .

# Build and run with arbitrary arguments
run *ARGS:
    cargo run -- {{ARGS}}

# Remove build artifacts
clean:
    cargo clean
```

**Notes:**
- `test *ARGS` lets you run a single test: `just test test_name`
- `check` runs test + lint + fmt-check (all three)
- `lint` uses `clippy` with warnings-as-errors
- `fmt-check` is separate from `fmt` so CI can check without modifying

---

## Zig

```just
default: check

# Run tests + lint
check: test lint

# Run all tests
test *ARGS:
    zig build test --summary all {{ARGS}}

# Check formatting (fails if unformatted)
lint:
    zig fmt --check src/

# Auto-format source files
fmt:
    zig fmt src/

# Build debug binary
build:
    zig build

# Build optimized release binary
release:
    zig build -Doptimize=ReleaseSmall

# Build release and symlink to ~/.local/bin/{BINARY_NAME}
install:
    #!/usr/bin/env bash
    set -euo pipefail
    zig build -Doptimize=ReleaseSmall
    mkdir -p ~/.local/bin
    ln -sf "$(pwd)/zig-out/bin/{BINARY_NAME}" ~/.local/bin/{BINARY_NAME}
    echo "Installed: ~/.local/bin/{BINARY_NAME} -> $(pwd)/zig-out/bin/{BINARY_NAME}"
    if ! echo "$PATH" | tr ':' '\n' | grep -qx "$HOME/.local/bin"; then
        echo "Make sure ~/.local/bin is in your PATH."
    fi

# Clean build artifacts
clean:
    rm -rf zig-out/ zig-cache/ .zig-cache/
```

**Notes:**
- `test *ARGS` passes extra args to `zig build test` (e.g., `--fuzz`)
- Zig uses `zig fmt --check` for linting (no separate linter)
- The `release` recipe uses `ReleaseSmall` for minimal binary size
- `install` symlinks rather than copies, so rebuilds update in place
- Adjust `src/` path in `lint` and `fmt` if source lives elsewhere

---

## Swift macOS App

```just
# Build output lives outside the project tree to avoid iCloud resource forks
# that break codesign.
build_dir := "/tmp/{REPO}-build"

# Generate Xcode project from project.yml
generate:
    xcodegen generate

# Build the app
build:
    xcodebuild -project {REPO}.xcodeproj -scheme {REPO} -configuration Debug build SYMROOT={{build_dir}}

# Run unit tests
test:
    xcodebuild -project {REPO}.xcodeproj -scheme {REPO}-unit -destination 'platform=macOS' test SYMROOT={{build_dir}}

# Run SwiftLint
lint:
    swiftlint lint --strict

# Run tests, lint, and build (CI check)
check: test lint build

# Build and launch the app (foreground)
run: build
    {{build_dir}}/Debug/{APP_NAME}.app/Contents/MacOS/{APP_NAME}

# Build and launch the app (background, for scripted testing)
run-bg: build
    @{{build_dir}}/Debug/{APP_NAME}.app/Contents/MacOS/{APP_NAME} &
    @sleep 2
    @echo "{APP_NAME} launched in background. Use 'just stop' to quit."

# Quit the running app gracefully
stop:
    @osascript -e 'tell application "{APP_NAME}" to quit' 2>/dev/null || echo "{APP_NAME} is not running"

# Remove build artifacts
clean:
    rm -rf {{build_dir}}
    rm -rf DerivedData/
```

**Notes:**
- `{REPO}` is the Xcode project/scheme name (e.g., `montty`)
- `{APP_NAME}` is the macOS app bundle name (e.g., `Montty`)
- Build dir is in `/tmp/` to avoid iCloud resource fork corruption of codesign
- `check` runs test + lint + build (build is included because Swift compilation catches type errors)
- Requires `swiftlint` and `xcodegen` installed (`brew install swiftlint xcodegen`)
- The test scheme (`{REPO}-unit`) must be defined in `project.yml`
- Adjust paths if using Swift Package Manager instead of XcodeGen

---

## TypeScript/Bun

```just
# Install dependencies
install:
    bun install

# Run all checks (test + lint + typecheck)
check: test lint typecheck

# Run tests
test *ARGS:
    bun run test {{ARGS}}

# Run tests in watch mode
test-watch:
    bun run test -- --watch

# Run linter
lint:
    bun run lint

# Run TypeScript type checker
typecheck:
    bunx tsc -b

# Build for production
build:
    bun run build

# Format code (if eslint has --fix or prettier is configured)
fmt:
    bun run lint -- --fix

# Remove build artifacts and dependencies
clean:
    rm -rf node_modules/ dist/ .cache/
```

**Notes:**
- `test *ARGS` allows `just test -- --filter "pattern"` for individual tests
- TypeScript projects have three separate checks: test, lint, typecheck
- `check` runs all three -- this is what CI and pre-commit use
- Adjust `bun run test`, `bun run lint`, etc. to match package.json scripts
- If using npm instead of bun, replace `bun` with `npm` / `npx`
- `fmt` assumes eslint --fix; adjust if using prettier directly

---

## Placeholders

These placeholders appear in templates above. Replace them with actual values:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{BINARY_NAME}` | Name of the built executable | `veer` |
| `{REPO}` | Repository/project name | `montty` |
| `{APP_NAME}` | macOS app bundle display name | `Montty` |

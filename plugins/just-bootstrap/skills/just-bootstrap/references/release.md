# Release Workflow Templates

GitHub Actions release workflows triggered by tag push. Two major variants:
CLI (cross-compile to tar.gz) and macOS app (build DMG with optional signing).

Both variants create a GitHub release with notes from the annotated tag and
optionally update a Homebrew tap.

**Important:** Release workflows should not contain standalone test/lint jobs.
Testing runs in CI on every push/PR. The release workflow triggers on tags
and should focus solely on building, packaging, releasing, and updating
homebrew. If the existing release workflow has a redundant test job, remove it.

## Table of Contents

- [Rust CLI](#rust-cli)
- [Zig CLI](#zig-cli)
- [Swift macOS App](#swift-macos-app)
- [TypeScript/Bun](#typescriptbun)
- [Homebrew Integration](#homebrew-integration)

---

## Rust CLI

Cross-compiles for macOS (arm64 + x86_64) and Linux (x86_64). Packages each
target as a tar.gz.

```yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  build:
    strategy:
      matrix:
        include:
          - target: x86_64-apple-darwin
            os: macos-26
          - target: aarch64-apple-darwin
            os: macos-26
          - target: x86_64-unknown-linux-gnu
            os: ubuntu-latest
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v5
      - uses: dtolnay/rust-toolchain@stable
      - run: rustup target add ${{ matrix.target }}
      - run: cargo build --release --target ${{ matrix.target }}
      - name: Package binary
        run: |
          cd target/${{ matrix.target }}/release
          tar czf ../../../{BINARY_NAME}-${{ matrix.target }}.tar.gz {BINARY_NAME}
      - uses: actions/upload-artifact@v5
        with:
          name: {BINARY_NAME}-${{ matrix.target }}
          path: {BINARY_NAME}-${{ matrix.target }}.tar.gz

  publish:
    needs: build
    runs-on: ubuntu-latest
    env:
      HOMEBREW_TAP_TOKEN: ${{ secrets.HOMEBREW_TAP_TOKEN }}
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
          fetch-tags: true
      - uses: actions/download-artifact@v5
        with:
          merge-multiple: true
      - name: Ensure annotated tag is available
        run: git fetch origin "refs/tags/${{ github.ref_name }}:refs/tags/${{ github.ref_name }}" --force
      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create ${{ github.ref_name }} \
            --title "${{ github.ref_name }}" \
            --notes-from-tag \
            {BINARY_NAME}-*.tar.gz

      # -- Homebrew formula update (see homebrew.md for details) --
      # Add the homebrew update steps from references/homebrew.md here
      # if homebrew distribution is desired.
```

---

## Zig CLI

Cross-compiles for macOS (arm64 + x86_64) and Linux (arm64 + x86_64, musl).
Zig's cross-compilation is built-in, so each target can build on any runner.

```yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  build:
    strategy:
      matrix:
        include:
          - target: aarch64-macos
            os: macos-latest
            zig_target: -Dtarget=aarch64-macos
          - target: x86_64-macos
            os: macos-latest
            zig_target: -Dtarget=x86_64-macos
          - target: aarch64-linux-musl
            os: ubuntu-latest
            zig_target: -Dtarget=aarch64-linux-musl
          - target: x86_64-linux-musl
            os: ubuntu-latest
            zig_target: -Dtarget=x86_64-linux-musl
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v5
      - uses: mlugg/setup-zig@v2
        with:
          version: {ZIG_VERSION}

      - name: Build
        run: zig build -Doptimize=ReleaseSmall ${{ matrix.zig_target }}

      - name: Package
        run: |
          cd zig-out/bin
          tar czf ../../{BINARY_NAME}-${{ matrix.target }}.tar.gz {BINARY_NAME}
          cd ../..

      - uses: actions/upload-artifact@v5
        with:
          name: {BINARY_NAME}-${{ matrix.target }}
          path: {BINARY_NAME}-${{ matrix.target }}.tar.gz

  publish:
    needs: build
    runs-on: ubuntu-latest
    env:
      HOMEBREW_TAP_TOKEN: ${{ secrets.HOMEBREW_TAP_TOKEN }}
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
          fetch-tags: true
      - uses: actions/download-artifact@v5
        with:
          merge-multiple: true
      - name: Ensure annotated tag is available
        run: git fetch origin "refs/tags/${{ github.ref_name }}:refs/tags/${{ github.ref_name }}" --force
      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create ${{ github.ref_name }} \
            --title "${{ github.ref_name }}" \
            --notes-from-tag \
            {BINARY_NAME}-*.tar.gz

      # -- Homebrew formula update (see homebrew.md for details) --
      # Add the homebrew update steps from references/homebrew.md here
      # if homebrew distribution is desired.
```

---

## Swift macOS App

Builds a DMG with optional Apple code signing and notarization. Uses a single
macOS runner. The signing flow is conditional -- it works without signing
secrets (ad-hoc signing), and adds full signing + notarization when secrets
are configured.

```yaml
name: Release

on:
  push:
    tags: ['[0-9]*']

permissions:
  contents: write

jobs:
  release:
    runs-on: macos-26
    env:
      APPLE_CERTIFICATE: ${{ secrets.APPLE_CERTIFICATE }}
      HOMEBREW_TAP_TOKEN: ${{ secrets.HOMEBREW_TAP_TOKEN }}
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
          fetch-tags: true
          submodules: recursive

      - uses: taiki-e/install-action@v2
        with:
          tool: just

      # -- Add framework cache steps here if needed (same as CI) --

      - name: Install SwiftLint and xcodegen
        run: brew install swiftlint xcodegen

      - name: Generate and check
        run: |
          just generate
          just check

      - name: Build Release
        run: |
          xcodebuild -project {REPO}.xcodeproj -scheme {REPO} \
            -configuration Release build SYMROOT=/tmp/{REPO}-build

      - name: Extract version
        id: version
        run: echo "version=${GITHUB_REF_NAME}" >> "$GITHUB_OUTPUT"

      # -- Conditional code signing --
      - name: Import certificate
        if: env.APPLE_CERTIFICATE != ''
        env:
          APPLE_CERTIFICATE_PASSWORD: ${{ secrets.APPLE_CERTIFICATE_PASSWORD }}
        run: |
          CERT_PATH="$RUNNER_TEMP/certificate.p12"
          KEYCHAIN_PATH="$RUNNER_TEMP/signing.keychain-db"
          KEYCHAIN_PASSWORD="$(openssl rand -hex 16)"

          echo "$APPLE_CERTIFICATE" | base64 --decode > "$CERT_PATH"

          security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
          security set-keychain-settings -lut 21600 "$KEYCHAIN_PATH"
          security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
          security import "$CERT_PATH" -P "$APPLE_CERTIFICATE_PASSWORD" \
            -A -t cert -f pkcs12 -k "$KEYCHAIN_PATH"
          security set-key-partition-list -S apple-tool:,apple: \
            -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
          security list-keychains -d user -s "$KEYCHAIN_PATH" login.keychain-db

      - name: Store notarization credentials
        if: env.APPLE_CERTIFICATE != ''
        env:
          APPLE_ID: ${{ secrets.APPLE_ID }}
          APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
          APPLE_APP_SPECIFIC_PASSWORD: ${{ secrets.APPLE_APP_SPECIFIC_PASSWORD }}
        run: |
          xcrun notarytool store-credentials "notary-profile" \
            --apple-id "$APPLE_ID" \
            --team-id "$APPLE_TEAM_ID" \
            --password "$APPLE_APP_SPECIFIC_PASSWORD"

      - name: Sign app
        if: env.APPLE_CERTIFICATE != ''
        run: |
          codesign --force --deep --sign "Developer ID Application" \
            --options runtime \
            --entitlements Resources/{REPO}.entitlements \
            --timestamp \
            /tmp/{REPO}-build/Release/{APP_NAME}.app

      - name: Ad-hoc sign (no certificate)
        if: env.APPLE_CERTIFICATE == ''
        run: |
          codesign --force --deep --sign - \
            /tmp/{REPO}-build/Release/{APP_NAME}.app

      # -- DMG creation --
      - name: Create DMG
        run: |
          VERSION="${{ steps.version.outputs.version }}"
          DMG_DIR="/tmp/{REPO}-dmg"
          mkdir -p "$DMG_DIR"
          cp -R /tmp/{REPO}-build/Release/{APP_NAME}.app "$DMG_DIR/"
          ln -s /Applications "$DMG_DIR/Applications"
          hdiutil create -volname "{APP_NAME}" -srcfolder "$DMG_DIR" \
            -ov -format UDZO "/tmp/{REPO}-build/{REPO}-${VERSION}.dmg"

      - name: Sign and notarize DMG
        if: env.APPLE_CERTIFICATE != ''
        run: |
          VERSION="${{ steps.version.outputs.version }}"
          codesign --force --sign "Developer ID Application" \
            --timestamp "/tmp/{REPO}-build/{REPO}-${VERSION}.dmg"
          xcrun notarytool submit "/tmp/{REPO}-build/{REPO}-${VERSION}.dmg" \
            --keychain-profile "notary-profile" --wait
          xcrun stapler staple "/tmp/{REPO}-build/{REPO}-${VERSION}.dmg"

      # -- GitHub Release --
      - name: Extract release notes
        run: |
          git fetch origin "refs/tags/${{ github.ref_name }}:refs/tags/${{ github.ref_name }}" --force
          git tag -l --format='%(contents)' "${{ github.ref_name }}" | tail -n +2 > /tmp/release-notes.md

      - name: Upload to GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          body_path: /tmp/release-notes.md
          files: /tmp/{REPO}-build/{REPO}-${{ steps.version.outputs.version }}.dmg

      # -- Homebrew cask update (see homebrew.md for details) --
      # Add the homebrew cask update steps from references/homebrew.md here
      # if homebrew distribution is desired.

      # -- Cleanup --
      - name: Cleanup keychain
        if: env.APPLE_CERTIFICATE != '' && always()
        run: security delete-keychain "$RUNNER_TEMP/signing.keychain-db" 2>/dev/null || true
```

**Notes:**
- Tag pattern `[0-9]*` matches bare version tags (e.g., `0.3.3`). Use `v*`
  if the project uses v-prefixed tags.
- The signing flow is fully conditional. Without `APPLE_CERTIFICATE` secret,
  the app is ad-hoc signed (works for development, not for distribution).
- `softprops/action-gh-release@v2` is used here because it handles the
  body_path nicely. For CLIs, `gh release create --notes-from-tag` is cleaner.

**Placeholders:**
| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{REPO}` | Project/scheme name | `montty` |
| `{APP_NAME}` | macOS app bundle name | `Montty` |

**Required secrets for full signing:**
| Secret | Description |
|--------|-------------|
| `APPLE_CERTIFICATE` | Base64-encoded .p12 developer certificate |
| `APPLE_CERTIFICATE_PASSWORD` | Password for the .p12 file |
| `APPLE_ID` | Apple ID email for notarization |
| `APPLE_TEAM_ID` | 10-character Apple Developer Team ID |
| `APPLE_APP_SPECIFIC_PASSWORD` | App-specific password for notarization |

---

## TypeScript/Bun

TypeScript release workflows vary significantly by project type (CLI, library,
Obsidian plugin, web app). Here's a generic CLI/library pattern:

```yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
          fetch-tags: true
      - uses: oven-sh/setup-bun@v2
      - uses: taiki-e/install-action@v2
        with:
          tool: just
      - run: just install
      - run: just check
      - run: just build
      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          git fetch origin "refs/tags/${{ github.ref_name }}:refs/tags/${{ github.ref_name }}" --force
          gh release create ${{ github.ref_name }} \
            --title "${{ github.ref_name }}" \
            --notes-from-tag
```

**Notes:**
- For TypeScript CLIs distributed via npm, add `npm publish` step
- For Obsidian plugins, upload specific build artifacts (main.js, manifest.json)
- For web apps, consider a separate deploy workflow (not release)
- Adapt build artifacts and upload steps to match the project's output

---

## Homebrew Integration

The homebrew update steps are kept in `references/homebrew.md` to avoid
duplication. When generating a release workflow with homebrew support:

1. Read `references/homebrew.md` for the formula or cask update steps
2. Add those steps after the GitHub Release creation step
3. Ensure the `HOMEBREW_TAP_TOKEN` env var is set at the job level
4. The steps are conditional on `env.HOMEBREW_TAP_TOKEN != ''` so the
   workflow works even before the secret is configured

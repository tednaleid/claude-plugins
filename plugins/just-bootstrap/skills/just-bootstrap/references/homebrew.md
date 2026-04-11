# Homebrew Distribution

Homebrew distribution for CLI tools (formula) and macOS apps (cask). Each
project gets a separate tap repository (e.g., `tednaleid/homebrew-veer`).
The release workflow pushes updated formula/cask files to the tap after
each release.

## Table of Contents

- [Formula Template (CLI)](#formula-template-cli)
- [Cask Template (macOS App)](#cask-template-macos-app)
- [Setup Script](#setup-script)
- [Release Workflow Integration: Formula](#release-workflow-integration-formula)
- [Release Workflow Integration: Cask](#release-workflow-integration-cask)

---

## Formula Template (CLI)

For CLI tools that distribute platform-specific binaries as tar.gz archives.
Supports macOS (arm64 + x86_64) and Linux (x86_64).

```ruby
class {FORMULA_CLASS} < Formula
  desc "{DESC}"
  homepage "https://github.com/{OWNER}/{REPO}"
  version "{VERSION}"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/{OWNER}/{REPO}/releases/download/{TAG_PREFIX}#{version}/{BINARY_NAME}-aarch64-apple-darwin.tar.gz"
      sha256 "{SHA256_MACOS_ARM}"
    end
    on_intel do
      url "https://github.com/{OWNER}/{REPO}/releases/download/{TAG_PREFIX}#{version}/{BINARY_NAME}-x86_64-apple-darwin.tar.gz"
      sha256 "{SHA256_MACOS_INTEL}"
    end
  end
  on_linux do
    on_intel do
      url "https://github.com/{OWNER}/{REPO}/releases/download/{TAG_PREFIX}#{version}/{BINARY_NAME}-x86_64-unknown-linux-gnu.tar.gz"
      sha256 "{SHA256_LINUX}"
    end
  end

  def install
    bin.install "{BINARY_NAME}"
  end

  test do
    system "#{bin}/{BINARY_NAME}", "--version"
  end
end
```

**Notes:**
- `{FORMULA_CLASS}` is the CamelCase version of the binary name (e.g., `Sumpig`, `Veer`)
- Zig projects use different target names in URLs (e.g., `aarch64-macos` instead
  of `aarch64-apple-darwin`). Adjust the URL pattern to match the release
  workflow's artifact names.
- The `{TAG_PREFIX}` in the URL must match the tag convention (usually `v`).
  Use `v#{version}` for v-prefixed tags or `#{version}` for bare tags.

### Zig target name variant

For Zig projects, the tar.gz names use Zig's target naming:

```ruby
  on_macos do
    on_arm do
      url "https://github.com/{OWNER}/{REPO}/releases/download/v#{version}/{BINARY_NAME}-aarch64-macos.tar.gz"
      sha256 "{SHA256_MACOS_ARM}"
    end
    on_intel do
      url "https://github.com/{OWNER}/{REPO}/releases/download/v#{version}/{BINARY_NAME}-x86_64-macos.tar.gz"
      sha256 "{SHA256_MACOS_INTEL}"
    end
  end
  on_linux do
    on_intel do
      url "https://github.com/{OWNER}/{REPO}/releases/download/v#{version}/{BINARY_NAME}-x86_64-linux-musl.tar.gz"
      sha256 "{SHA256_LINUX}"
    end
  end
```

---

## Cask Template (macOS App)

For macOS apps distributed as DMG files.

```ruby
cask "{REPO}" do
  version "{VERSION}"
  sha256 "{SHA256_DMG}"

  url "https://github.com/{OWNER}/{REPO}/releases/download/#{version}/{REPO}-#{version}.dmg"
  name "{APP_NAME}"
  desc "{DESC}"
  homepage "https://github.com/{OWNER}/{REPO}"

  depends_on macos: ">= :sonoma"

  app "{APP_NAME}.app"

  zap trash: [
    "~/Library/Application Support/{REPO}",
    "~/Library/Preferences/com.{REPO}.app.plist",
    "~/Library/Caches/com.{REPO}.app",
  ]
end
```

**Notes:**
- Cask name is lowercase (e.g., `montty`)
- The `depends_on macos` version should match the project's deployment target
- `zap trash` paths should list the app's data, preferences, and cache locations
- The DMG URL must match the release workflow's output filename
- Adjust `#{version}` to `v#{version}` if using v-prefixed tags

---

## Setup Script

A one-time script to create the Homebrew tap repository on GitHub, seed it
with the initial formula or cask, and print instructions for setting up the
PAT secret.

Save this as `scripts/setup-homebrew-tap.sh` in the project repo.

### Formula variant (CLI)

```bash
#!/usr/bin/env bash
# ABOUTME: Creates the {OWNER}/homebrew-{REPO} tap repo on GitHub and seeds it
# ABOUTME: with an initial formula from the latest release.
set -euo pipefail

OWNER="{OWNER}"
TAP_REPO="homebrew-{REPO}"
MAIN_REPO="{REPO}"
BINARY_NAME="{BINARY_NAME}"

# -- Preflight checks --

if ! command -v gh &>/dev/null; then
    echo "Error: gh CLI is required. Install with: brew install gh"
    exit 1
fi

if ! gh auth status &>/dev/null; then
    echo "Error: not authenticated with gh. Run: gh auth login"
    exit 1
fi

# -- Get latest release version and compute SHA-256 for each platform --

echo "Fetching latest release info..."
VERSION=$(gh release view --repo "${OWNER}/${MAIN_REPO}" --json tagName -q .tagName)
BARE_VERSION="${VERSION#v}"

TARGETS=("{TARGET_ARM_MACOS}" "{TARGET_INTEL_MACOS}" "{TARGET_LINUX}")
declare -A SHA256S

for target in "${TARGETS[@]}"; do
    url="https://github.com/${OWNER}/${MAIN_REPO}/releases/download/${VERSION}/${BINARY_NAME}-${target}.tar.gz"
    echo "Downloading ${BINARY_NAME}-${target}.tar.gz to compute SHA-256..."
    sha=$(curl -sL "$url" | shasum -a 256 | awk '{print $1}')
    SHA256S[$target]="$sha"
    echo "  ${target}: ${sha}"
done

# -- Create or clone the tap repo --

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
cd "$WORKDIR"

if gh repo view "${OWNER}/${TAP_REPO}" &>/dev/null; then
    echo "Repo ${OWNER}/${TAP_REPO} already exists, cloning."
    git clone "git@github.com:${OWNER}/${TAP_REPO}.git" .
else
    echo "Creating ${OWNER}/${TAP_REPO}..."
    gh repo create "${OWNER}/${TAP_REPO}" --public \
        --description "Homebrew tap for ${BINARY_NAME}" \
        --clone
    cd "${TAP_REPO}"
fi

# -- Populate and push --

mkdir -p Formula

# Generate formula (fill in the template with computed SHAs)
# NOTE: The actual formula content is generated inline here.
# Adapt the Ruby template from the Formula Template section above,
# replacing SHA256 placeholders with the computed values.

cat > README.md << 'README'
# homebrew-{REPO}

Homebrew tap for [{BINARY_NAME}](https://github.com/{OWNER}/{REPO}).

## Install

```bash
brew install {OWNER}/{REPO}/{BINARY_NAME}
```

Or:

```bash
brew tap {OWNER}/{REPO}
brew install {BINARY_NAME}
```

## Update

```bash
brew upgrade {BINARY_NAME}
```
README

git add Formula/ README.md
git commit -m "Initial formula for ${BINARY_NAME} ${VERSION}"
git push

echo ""
echo "Tap repo created and populated at: https://github.com/${OWNER}/${TAP_REPO}"
echo ""
echo "-- Next step: create a fine-grained Personal Access Token --"
echo ""
echo "1. Go to: https://github.com/settings/personal-access-tokens/new"
echo "2. Token name: ${MAIN_REPO}-homebrew-tap"
echo "3. Repository access: Only select repositories -> ${OWNER}/${TAP_REPO}"
echo "4. Permissions: Contents -> Read and write"
echo "5. Generate the token and copy it"
echo ""
echo "Then set it as a secret on the ${MAIN_REPO} repo:"
echo ""
echo "  gh secret set HOMEBREW_TAP_TOKEN --repo ${OWNER}/${MAIN_REPO}"
echo ""
echo "(Paste the token when prompted.)"
```

### Cask variant (macOS app)

Same structure as above, but replace the Formula section with Casks:

- Use `mkdir -p Casks` instead of `mkdir -p Formula`
- Write the cask template to `Casks/{REPO}.rb`
- Download the DMG instead of tar.gz files to compute SHA-256:
  ```bash
  url="https://github.com/${OWNER}/${MAIN_REPO}/releases/download/${VERSION}/${MAIN_REPO}-${BARE_VERSION}.dmg"
  sha=$(curl -sL "$url" | shasum -a 256 | awk '{print $1}')
  ```

**Placeholders for the setup script:**
| Placeholder | Rust Example | Zig Example |
|-------------|-------------|-------------|
| `{TARGET_ARM_MACOS}` | `aarch64-apple-darwin` | `aarch64-macos` |
| `{TARGET_INTEL_MACOS}` | `x86_64-apple-darwin` | `x86_64-macos` |
| `{TARGET_LINUX}` | `x86_64-unknown-linux-gnu` | `x86_64-linux-musl` |

---

## Release Workflow Integration: Formula

Add these steps to the release workflow's `publish` job (after creating the
GitHub release) to automatically update the Homebrew formula on each release.

```yaml
      # -- Update Homebrew formula --

      - name: Compute artifact SHA-256 values
        if: env.HOMEBREW_TAP_TOKEN != ''
        id: sha256
        run: |
          echo "macos_arm=$(shasum -a 256 {BINARY_NAME}-{TARGET_ARM_MACOS}.tar.gz | awk '{print $1}')" >> "$GITHUB_OUTPUT"
          echo "macos_intel=$(shasum -a 256 {BINARY_NAME}-{TARGET_INTEL_MACOS}.tar.gz | awk '{print $1}')" >> "$GITHUB_OUTPUT"
          echo "linux=$(shasum -a 256 {BINARY_NAME}-{TARGET_LINUX}.tar.gz | awk '{print $1}')" >> "$GITHUB_OUTPUT"

      - name: Update Homebrew formula
        if: env.HOMEBREW_TAP_TOKEN != ''
        run: |
          VERSION="${GITHUB_REF_NAME#v}"
          SHA256_MACOS_ARM="${{ steps.sha256.outputs.macos_arm }}"
          SHA256_MACOS_INTEL="${{ steps.sha256.outputs.macos_intel }}"
          SHA256_LINUX="${{ steps.sha256.outputs.linux }}"

          git clone "https://x-access-token:${HOMEBREW_TAP_TOKEN}@github.com/{OWNER}/homebrew-{REPO}.git" /tmp/homebrew-{REPO}
          cd /tmp/homebrew-{REPO}

          mkdir -p Formula
          cat > Formula/{BINARY_NAME}.rb << FORMULA
          class {FORMULA_CLASS} < Formula
            desc "{DESC}"
            homepage "https://github.com/{OWNER}/{REPO}"
            version "${VERSION}"
            license "MIT"

            on_macos do
              on_arm do
                url "https://github.com/{OWNER}/{REPO}/releases/download/{TAG_PREFIX}#{version}/{BINARY_NAME}-{TARGET_ARM_MACOS}.tar.gz"
                sha256 "${SHA256_MACOS_ARM}"
              end
              on_intel do
                url "https://github.com/{OWNER}/{REPO}/releases/download/{TAG_PREFIX}#{version}/{BINARY_NAME}-{TARGET_INTEL_MACOS}.tar.gz"
                sha256 "${SHA256_MACOS_INTEL}"
              end
            end
            on_linux do
              on_intel do
                url "https://github.com/{OWNER}/{REPO}/releases/download/{TAG_PREFIX}#{version}/{BINARY_NAME}-{TARGET_LINUX}.tar.gz"
                sha256 "${SHA256_LINUX}"
              end
            end

            def install
              bin.install "{BINARY_NAME}"
            end

            test do
              system "#{bin}/{BINARY_NAME}", "--version"
            end
          end
          FORMULA

          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add Formula/{BINARY_NAME}.rb
          git diff --cached --quiet && echo "No formula changes" && exit 0
          git commit -m "Update {BINARY_NAME} to ${VERSION}"
          git push
```

---

## Release Workflow Integration: Cask

Add these steps to the Swift macOS app release workflow (after uploading the
DMG to GitHub release) to update the Homebrew cask.

```yaml
      # -- Update Homebrew cask --

      - name: Update Homebrew cask
        if: env.HOMEBREW_TAP_TOKEN != ''
        run: |
          VERSION="${{ steps.version.outputs.version }}"
          DMG_PATH="/tmp/{REPO}-build/{REPO}-${VERSION}.dmg"
          SHA256=$(shasum -a 256 "$DMG_PATH" | awk '{print $1}')

          git clone "https://x-access-token:${HOMEBREW_TAP_TOKEN}@github.com/{OWNER}/homebrew-{REPO}.git" /tmp/homebrew-{REPO}
          cd /tmp/homebrew-{REPO}

          mkdir -p Casks
          cat > Casks/{REPO}.rb << CASK
          cask "{REPO}" do
            version "${VERSION}"
            sha256 "${SHA256}"

            url "https://github.com/{OWNER}/{REPO}/releases/download/#{version}/{REPO}-#{version}.dmg"
            name "{APP_NAME}"
            desc "{DESC}"
            homepage "https://github.com/{OWNER}/{REPO}"

            depends_on macos: ">= :sonoma"

            app "{APP_NAME}.app"

            zap trash: [
              "~/Library/Application Support/{REPO}",
              "~/Library/Preferences/com.{REPO}.app.plist",
              "~/Library/Caches/com.{REPO}.app",
            ]
          end
          CASK

          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add Casks/{REPO}.rb
          git diff --cached --quiet && echo "No cask changes" && exit 0
          git commit -m "Update {REPO} to ${VERSION}"
          git push
```

---

## All Placeholders

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{OWNER}` | GitHub username | `tednaleid` |
| `{REPO}` | Repository name | `veer` |
| `{BINARY_NAME}` | Executable name | `veer` |
| `{APP_NAME}` | macOS app display name | `Montty` |
| `{DESC}` | One-line description | `CLI tool for X` |
| `{FORMULA_CLASS}` | CamelCase class name | `Veer` |
| `{TAG_PREFIX}` | Tag prefix (`v` or empty) | `v` |
| `{VERSION}` | Current version | `0.1.0` |
| `{TARGET_ARM_MACOS}` | ARM macOS target name | `aarch64-apple-darwin` or `aarch64-macos` |
| `{TARGET_INTEL_MACOS}` | Intel macOS target name | `x86_64-apple-darwin` or `x86_64-macos` |
| `{TARGET_LINUX}` | Linux target name | `x86_64-unknown-linux-gnu` or `x86_64-linux-musl` |
| `{SHA256_*}` | Computed at release time | (dynamic) |

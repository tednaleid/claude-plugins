# Bump and Retag Recipes

Version bumping with Claude-generated release notes and annotation-preserving
retag. Both recipes always take a **bare version number** (e.g., `just bump 1.2.3`).
The recipe adds the tag prefix internally.

## Table of Contents

- [Bump Pattern (all languages)](#bump-pattern)
- [Retag Pattern (universal)](#retag-pattern)
- [Rust](#rust)
- [Zig](#zig)
- [Swift macOS App](#swift-macos-app)
- [TypeScript/Bun](#typescriptbun)

---

## Bump Pattern

All bump recipes follow the same structure:

1. Validate arguments and determine new version
2. Update version file(s)
3. Commit the version change
4. Generate release notes from commits since last tag
5. Create an annotated git tag with the release notes
6. Push commits and tags

Release notes are generated using `claude -p` if available, with a
fallback to formatting the git log as a bullet list. The notes are
embedded in the annotated tag, which GitHub reads for the release body
via `--notes-from-tag`.

## Retag Pattern

The retag recipe deletes and recreates a tag to re-trigger the release
workflow. It preserves the existing tag annotation (release notes) so
they are not lost. This is universal across all languages.

```just
# Delete a GitHub release and re-tag to re-trigger release workflow.
# Preserves the annotated tag message (release notes).
# Usage: just retag 1.2.3
retag version:
    #!/usr/bin/env bash
    set -euo pipefail
    tag="{TAG_PREFIX}{{version}}"
    # Save existing tag annotation before deleting
    notes=$(git tag -l --format='%(contents)' "$tag" 2>/dev/null || echo "$tag")
    notes_file=$(mktemp)
    trap 'rm -f "$notes_file"' EXIT
    echo "$notes" > "$notes_file"
    gh release delete "$tag" --yes || true
    git push origin ":refs/tags/$tag" || true
    git tag -d "$tag" || true
    git tag -a "$tag" -F "$notes_file"
    git push && git push --tags
```

Replace `{TAG_PREFIX}` with `v` or empty string based on the project's
existing convention.

---

## Rust

Version lives in `Cargo.toml`. The lock file must be regenerated after
updating the version.

```just
# Bump version, commit, tag with release notes, and push.
# Usage: just bump 1.2.3 (or just bump for patch increment)
bump version="":
    #!/usr/bin/env bash
    set -euo pipefail
    current=$(grep '^version' Cargo.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
    if [ -z "{{version}}" ]; then
        IFS='.' read -r major minor patch <<< "$current"
        new="$major.$minor.$((patch + 1))"
    else
        new="{{version}}"
    fi
    echo "Bumping $current -> $new"
    if [ "$current" != "$new" ]; then
        sed -i '' "s/^version = \"$current\"/version = \"$new\"/" Cargo.toml
        cargo generate-lockfile --quiet
        git add Cargo.toml Cargo.lock
        git commit -m "Bump version to $new"
    fi
    # Generate release notes from commits since last tag
    prev_tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    if [ -n "$prev_tag" ]; then
        log=$(git log "$prev_tag"..HEAD --oneline --no-merges)
    else
        log=$(git log --oneline --no-merges)
    fi
    notes_file=$(mktemp)
    trap 'rm -f "$notes_file"' EXIT
    if command -v claude >/dev/null 2>&1; then
        claude -p "Generate concise release notes for version $new. Commits:\n$log\n\nGuidelines: group related commits, focus on user-facing changes, skip version bumps and CI changes, one line per bullet, past tense, output only a bullet list." > "$notes_file" 2>/dev/null || echo "$log" | sed 's/^[0-9a-f]* /- /' > "$notes_file"
    else
        echo "$log" | sed 's/^[0-9a-f]* /- /' > "$notes_file"
    fi
    echo "Release notes:"
    cat "$notes_file"
    git tag -a "v$new" -F "$notes_file"
    rm -f "$notes_file"
    git push && git push --tags
    echo "v$new released!"
```

---

## Zig

Version lives in two files: `build.zig.zon` and `src/main.zig`. Both must
be updated together.

```just
# Bump version, commit, tag with release notes, and push.
# Usage: just bump 1.2.3 (or just bump for patch increment)
bump version="":
    #!/usr/bin/env bash
    set -euo pipefail
    current=$(grep 'version = "' build.zig.zon | head -1 | sed 's/.*"\(.*\)".*/\1/')
    if [ -z "{{version}}" ]; then
        IFS='.' read -r major minor patch <<< "$current"
        new="$major.$minor.$((patch + 1))"
    else
        new="{{version}}"
    fi
    echo "Bumping $current -> $new"
    if [ "$current" != "$new" ]; then
        sed -i '' "s/version = \"$current\"/version = \"$new\"/" build.zig.zon
        sed -i '' "s/const version = \"$current\"/const version = \"$new\"/" src/main.zig
        git add build.zig.zon src/main.zig
        git commit -m "Bump version to $new"
    fi
    # Generate release notes
    prev_tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    if [ -n "$prev_tag" ]; then
        log=$(git log "$prev_tag"..HEAD --oneline --no-merges)
    else
        log=$(git log --oneline --no-merges)
    fi
    notes_file=$(mktemp)
    trap 'rm -f "$notes_file"' EXIT
    if command -v claude >/dev/null 2>&1; then
        claude -p "Generate concise release notes for version $new. Commits:\n$log\n\nGuidelines: group related commits, focus on user-facing changes, skip version bumps and CI changes, one line per bullet, past tense, output only a bullet list." > "$notes_file" 2>/dev/null || echo "$log" | sed 's/^[0-9a-f]* /- /' > "$notes_file"
    else
        echo "$log" | sed 's/^[0-9a-f]* /- /' > "$notes_file"
    fi
    echo "Release notes:"
    cat "$notes_file"
    git tag -a "v$new" -F "$notes_file"
    rm -f "$notes_file"
    git push && git push --tags
    echo "v$new released!"
```

**Note:** If the Zig project stores the version in different files (check
`build.zig.zon` and `src/main.zig` for the actual pattern), adjust the sed
commands accordingly.

---

## Swift macOS App

Version lives in `Resources/Info.plist` under `CFBundleShortVersionString`.
Updated via `PlistBuddy`. Montty uses bare version tags (no `v` prefix).

```just
# Bump version in Info.plist, commit, tag with release notes, and push.
# Usage: just bump 1.2.3
bump version:
    #!/usr/bin/env bash
    set -euo pipefail
    test -n "{{version}}" || { echo "Usage: just bump 1.2.3"; exit 1; }

    # Update version in Info.plist
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString {{version}}" Resources/Info.plist
    git add Resources/Info.plist
    git commit -m "Bump version to {{version}}"

    # Generate release notes
    prev_tag=$(git describe --tags --abbrev=0 HEAD~1 2>/dev/null || echo "")
    if [ -n "$prev_tag" ]; then
        commit_log=$(git log "${prev_tag}..HEAD" --oneline --no-merges)
    else
        commit_log=$(git log --oneline --no-merges -20)
    fi

    notes_file=$(mktemp)
    trap 'rm -f "$notes_file"' EXIT

    if command -v claude &>/dev/null; then
        prompt="Generate concise release notes for version {{version}}.
    Commits since ${prev_tag:-the beginning}:

    ${commit_log}

    Guidelines:
    - Group related commits into a single bullet point
    - Focus on user-facing changes, not implementation details
    - Skip version bumps, CI changes, and purely internal refactors
    - Keep each bullet to one line, use past tense
    - Output only a bullet list (- item), nothing else"

        if claude -p "$prompt" > "$notes_file" 2>/dev/null; then
            echo "Release notes (generated by Claude):"
        else
            echo "$commit_log" | sed 's/^[0-9a-f]* /- /' > "$notes_file"
            echo "Release notes (from commit log):"
        fi
    else
        echo "$commit_log" | sed 's/^[0-9a-f]* /- /' > "$notes_file"
        echo "Release notes (from commit log):"
    fi
    cat "$notes_file"

    git tag -a "{{version}}" -F "$notes_file"
    git push && git push --tags
```

**Note:** Swift macOS apps often use bare version tags (no `v` prefix).
Check the project's existing tags. Also, if the project has a
`CURRENT_PROJECT_VERSION` (build number) in `project.yml`, you may want
to increment that too.

---

## TypeScript/Bun

Version may live in multiple `package.json` files (monorepo) or additional
manifest files. For simple projects, a single `package.json` update suffices.
For monorepos with many version files, consider an external bump script.

### Simple (single package.json)

```just
# Bump version, commit, tag with release notes, and push.
# Usage: just bump 1.2.3 (or just bump for patch increment)
bump version="":
    #!/usr/bin/env bash
    set -euo pipefail
    current=$(jq -r .version package.json)
    if [ -z "{{version}}" ]; then
        IFS='.' read -r major minor patch <<< "$current"
        new="$major.$minor.$((patch + 1))"
    else
        new="{{version}}"
    fi
    echo "Bumping $current -> $new"
    if [ "$current" != "$new" ]; then
        jq --arg v "$new" '.version = $v' package.json > package.json.tmp && mv package.json.tmp package.json
        git add package.json
        git commit -m "Bump version to $new"
    fi
    # Generate release notes
    prev_tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    if [ -n "$prev_tag" ]; then
        log=$(git log "$prev_tag"..HEAD --oneline --no-merges)
    else
        log=$(git log --oneline --no-merges)
    fi
    notes_file=$(mktemp)
    trap 'rm -f "$notes_file"' EXIT
    if command -v claude >/dev/null 2>&1; then
        claude -p "Generate concise release notes for version $new. Commits:\n$log\n\nGuidelines: group related commits, focus on user-facing changes, skip version bumps and CI changes, one line per bullet, past tense, output only a bullet list." > "$notes_file" 2>/dev/null || echo "$log" | sed 's/^[0-9a-f]* /- /' > "$notes_file"
    else
        echo "$log" | sed 's/^[0-9a-f]* /- /' > "$notes_file"
    fi
    echo "Release notes:"
    cat "$notes_file"
    git tag -a "v$new" -F "$notes_file"
    rm -f "$notes_file"
    git push && git push --tags
    echo "v$new released!"
```

### Monorepo (external bump script)

For projects with version in multiple files, create a `scripts/bump-version.ts`
(or `.sh`) that handles all the file updates. The justfile recipe calls it:

```just
bump version="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{version}}" ]; then
        bun run scripts/bump-version.ts
    else
        bun run scripts/bump-version.ts "{{version}}"
    fi
```

The bump script should follow the same pattern: update files, commit, generate
notes, tag, push. See `limn/scripts/bump-version.ts` for a working example
of a monorepo bump script.

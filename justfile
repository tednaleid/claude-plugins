# Install all plugins from this repo into Claude Code
install:
    #!/usr/bin/env bash
    set -euo pipefail
    claude plugin marketplace add tednaleid/claude-plugins 2>/dev/null || true
    claude plugin marketplace update tednaleid
    for dir in plugins/*/; do
        name=$(basename "$dir")
        echo "Installing $name..."
        claude plugin install "${name}@tednaleid"
        version=$(claude plugin list 2>&1 | grep -A1 "${name}@tednaleid" | grep "Version:" | awk '{print $2}')
        echo "  Installed ${name} v${version}"
    done

# Run marketplace sync and verify it's up to date
check: sync
    #!/usr/bin/env bash
    set -euo pipefail
    if ! git diff --quiet .claude-plugin/marketplace.json; then
        echo "FAIL: marketplace.json is out of date. Run: just sync"
        exit 1
    fi
    echo "All good."

# Sync marketplace.json from discovered plugins
sync:
    npx tsx scripts/sync-marketplace.ts

# Bump a plugin's version, commit, tag with release notes, and push.
# Usage: just bump just-bootstrap 0.2.0  (or: just bump just-bootstrap)
bump plugin version="":
    #!/usr/bin/env bash
    set -euo pipefail
    json="plugins/{{plugin}}/.claude-plugin/plugin.json"
    test -f "$json" || { echo "Error: $json not found"; exit 1; }

    current=$(jq -r .version "$json")
    if [ -z "{{version}}" ]; then
        IFS='.' read -r major minor patch <<< "$current"
        new="$major.$minor.$((patch + 1))"
    else
        new="{{version}}"
    fi
    echo "Bumping {{plugin}} $current -> $new"

    if [ "$current" != "$new" ]; then
        jq --arg v "$new" '.version = $v' "$json" > "$json.tmp" && mv "$json.tmp" "$json"
    fi

    # Always sync marketplace.json so it reflects current plugin state,
    # then commit anything that changed (version bump or other plugin.json edits).
    npx tsx scripts/sync-marketplace.ts
    if ! git diff --quiet "$json" .claude-plugin/marketplace.json; then
        git add "$json" .claude-plugin/marketplace.json
        if [ "$current" != "$new" ]; then
            git commit -m "Bump {{plugin}} to $new"
        else
            git commit -m "{{plugin}} Sync marketplace entry"
        fi
    fi

    # Generate release notes from commits since last tag for this plugin
    prev_tag=$(git tag -l "{{plugin}}/v*" --sort=-version:refname | head -1)
    if [ -n "$prev_tag" ]; then
        log=$(git log "$prev_tag"..HEAD --oneline --no-merges -- "plugins/{{plugin}}/")
    else
        log=$(git log --oneline --no-merges -- "plugins/{{plugin}}/")
    fi
    [ -z "$log" ] && log="Initial release"

    notes_file=$(mktemp)
    trap 'rm -f "$notes_file"' EXIT
    if command -v claude >/dev/null 2>&1; then
        claude -p "Generate concise release notes for {{plugin}} version $new. Commits:\n$log\n\nGuidelines: group related commits, focus on user-facing changes, skip version bumps and CI changes, one line per bullet, past tense, output only a bullet list." > "$notes_file" 2>/dev/null || echo "$log" | sed 's/^[0-9a-f]* /- /' > "$notes_file"
    else
        echo "$log" | sed 's/^[0-9a-f]* /- /' > "$notes_file"
    fi
    echo "Release notes:"
    cat "$notes_file"

    tag="{{plugin}}/v$new"
    git tag -a "$tag" -F "$notes_file"
    rm -f "$notes_file"
    git push && git push --tags
    echo "$tag released!"

# Delete a GitHub release and re-tag to re-trigger workflows.
# Preserves the annotated tag message (release notes).
# Usage: just retag just-bootstrap 0.2.0
retag plugin version:
    #!/usr/bin/env bash
    set -euo pipefail
    tag="{{plugin}}/v{{version}}"
    # Save existing tag annotation before deleting
    notes=$(git tag -l --format='%(contents)' "$tag" 2>/dev/null || echo "$tag")
    notes_file=$(mktemp)
    trap 'rm -f "$notes_file"' EXIT
    echo "$notes" > "$notes_file"
    gh release delete "$tag" --yes 2>/dev/null || true
    git push origin ":refs/tags/$tag" || true
    git tag -d "$tag" || true
    git tag -a "$tag" -F "$notes_file"
    git push && git push --tags

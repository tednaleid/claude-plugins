# Pre-commit Hook

A simple `install-hooks` recipe that creates a git pre-commit hook running
`just check`. This is language-agnostic -- the same recipe works for all
projects because the hook delegates to the Justfile.

## Recipe

Add this to the Justfile:

```just
# Install git pre-commit hook that runs all checks before each commit
install-hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    hook=".git/hooks/pre-commit"
    cat > "$hook" << 'HOOK'
#!/bin/sh
just check
HOOK
    chmod +x "$hook"
    echo "Installed pre-commit hook: $hook"
```

## How It Works

The hook runs `just check` before every commit. If `just check` fails (tests
fail, lint errors, type errors), the commit is rejected. This catches issues
before they reach CI.

The hook is not checked into git (`.git/hooks/` is not tracked). Each
developer runs `just install-hooks` once after cloning. This is intentional --
hooks should be opt-in, not forced on contributors.

## When to Suggest

Suggest adding this recipe if the project has a `check` recipe in the
Justfile but no `install-hooks` recipe. If the project already has a different
hook mechanism (e.g., husky for Node projects), do not replace it.

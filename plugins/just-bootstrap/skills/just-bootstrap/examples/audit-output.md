# Example: Audit Output for a Zig CLI Project

This is what an audit looks like for a project like `veer` -- a Zig CLI tool
that has most infrastructure but is missing homebrew and has partial bump/retag.

## Detection Results

```
Language:      Zig
Build system:  zig build
Project type:  CLI
Tag prefix:    v (from existing tags: v0.1.0)
Version:       0.1.0 (from build.zig.zon + src/main.zig)
GitHub:        tednaleid/veer
```

## Audit Checklist

```
## Infrastructure Audit: veer (Zig CLI)

[x] Justfile          -- present (check, test, lint, fmt, build, release, install, bump, retag, bench, fuzz)
[x] CI workflow        -- present (.github/workflows/ci.yml -- test + lint on ubuntu)
[x] Release workflow   -- present (.github/workflows/release.yml -- 4 targets, GitHub release)
[ ] Homebrew tap       -- MISSING (no setup script, no tap update in release workflow)
[~] Bump recipe        -- PARTIAL (creates lightweight tags, no Claude release notes, prints push instructions instead of pushing)
[~] Retag recipe       -- PARTIAL (uses git tag -f, does not preserve tag annotations)
[ ] Pre-commit hook    -- MISSING (no install-hooks recipe)
[x] CLAUDE.md          -- present (has build/test section)
```

## User Selection

The user is presented with AskUserQuestion listing the missing and partial items:

- "Set up all missing/partial items" (selected)
- "Homebrew tap -- create setup script + add release workflow integration"
- "Bump recipe -- upgrade to annotated tags with Claude release notes"
- "Retag recipe -- upgrade to annotation-preserving retag"
- "Pre-commit hook -- add install-hooks recipe"

## What Gets Generated

1. `scripts/setup-homebrew-tap.sh` -- one-time script to create `tednaleid/homebrew-veer`
2. Updated `.github/workflows/release.yml` -- adds SHA-256 computation and homebrew formula update
3. Updated `justfile` -- bump recipe upgraded to annotated tags + Claude notes + auto-push
4. Updated `justfile` -- retag recipe upgraded to preserve annotations
5. Updated `justfile` -- install-hooks recipe added

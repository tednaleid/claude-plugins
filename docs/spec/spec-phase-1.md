# Spec: Phase 1 -- Plugin Repo Scaffolding + SKILL.md

**Contract**: ./contract.md
**Estimated Effort**: M

## Technical Approach

Create the `tednaleid/claude-plugins` multi-plugin repo following the same
structure as `nicknisi/claude-plugins`. The repo needs minimal Node tooling
(just the sync script) since we have no MCP servers. The core deliverable is
SKILL.md, which encodes the audit-then-menu workflow that drives the skill.

SKILL.md must stay under 500 lines per skill-creator best practices. All
language-specific templates live in references/ and are loaded on demand. The
SKILL.md body contains detection logic, audit procedure, checklist format,
generation instructions (with pointers to references), and verification steps.

## New Files

| File | Purpose |
|------|---------|
| `README.md` | Repo docs: what this is, how to install plugins |
| `CLAUDE.md` | Claude context for working in this repo |
| `.gitignore` | node_modules, dist, .DS_Store |
| `package.json` | Workspace root with sync script |
| `pnpm-workspace.yaml` | Workspace config |
| `.claude-plugin/marketplace.json` | Marketplace index |
| `scripts/sync-marketplace.ts` | Auto-discover plugins and regenerate marketplace.json |
| `plugins/just-bootstrap/.claude-plugin/plugin.json` | Plugin metadata |
| `plugins/just-bootstrap/README.md` | Plugin usage docs |
| `plugins/just-bootstrap/skills/just-bootstrap/SKILL.md` | Core skill definition |
| `plugins/just-bootstrap/skills/just-bootstrap/examples/audit-output.md` | Example audit checklist |

## Implementation Details

### Repo Infrastructure

**Pattern to follow**: `nicknisi-claude-plugins` at `../nicknisi-claude-plugins/`

- `package.json`: minimal -- name "claude-plugins", private, scripts for sync only
- `pnpm-workspace.yaml`: point to `plugins/*/mcp-server` (for future use)
- `scripts/sync-marketplace.ts`: copy from nicknisi, update owner info
- `.claude-plugin/marketplace.json`: tednaleid owner, single plugin entry
- `.gitignore`: node_modules, dist, .DS_Store, *.tgz

### plugin.json

```json
{
  "name": "just-bootstrap",
  "version": "0.1.0",
  "description": "Audit and set up CI, release, Justfile, and Homebrew infrastructure",
  "author": {
    "name": "Ted Naleid"
  },
  "keywords": ["ci", "release", "homebrew", "justfile", "bump", "retag", "pre-commit"]
}
```

### SKILL.md Structure (must stay under 500 lines)

```
---
name: just-bootstrap
description: [~80 words, specific about when to trigger, slightly pushy]
---

# just-bootstrap

## Overview (5 lines)
## Step 1: Detection (30 lines)
  - Detection signals table
  - Version file locations per language
  - Tag prefix convention detection
  - GitHub owner/repo extraction
## Step 2: Audit (40 lines)
  - Checklist of what to check for each concern
  - How to determine present/missing/partial
## Step 3: Present Checklist (20 lines)
  - Use AskUserQuestion with multiSelect
  - Example checklist format
## Step 4: Generate (60 lines)
  - Generation order (dependencies)
  - Per-concern: which reference to read, what to adapt
  - CLAUDE.md updates section
## Step 5: Verify (15 lines)
  - Run just check
  - Suggest CI test
## Step 6: Suggest Optional Enhancements (20 lines)
  - Project-type-appropriate suggestions
## Bundled Resources (10 lines)
  - List all references/ and examples/ files
## Important Notes (10 lines)
  - Security: no secrets in repo
  - Bump/retag: always bare version numbers
```

Target: ~250-350 lines, well under the 500-line limit.

### Example Audit Output

A concrete example showing what the audit checklist looks like for a Zig CLI
project (veer-like), with some items present, some missing, some partial.

## Validation

1. Verify SKILL.md is under 500 lines: `wc -l SKILL.md`
2. Verify all reference file pointers in SKILL.md are correct paths
3. Verify plugin.json is valid JSON
4. Verify marketplace.json includes the plugin
5. Run `pnpm run sync` to confirm sync script works

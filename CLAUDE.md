# claude-plugins

Multi-plugin repository for Claude Code plugins.

## Structure

- `plugins/` -- each subdirectory is a plugin with `.claude-plugin/plugin.json`
- `scripts/sync-marketplace.ts` -- auto-discovers plugins, regenerates `.claude-plugin/marketplace.json`
- Skills live in `plugins/{name}/skills/{skill-name}/SKILL.md`
- Reference docs in `references/`, examples in `examples/`

## Adding a Plugin

1. Create `plugins/{name}/.claude-plugin/plugin.json` with metadata
2. Add skills under `plugins/{name}/skills/`
3. Run `pnpm run sync` to update marketplace.json

## Conventions

- SKILL.md under 500 lines; heavy content goes in references/
- Reference files organized by concern, with language-specific sections
- Explain reasoning in skill instructions, not rote rules

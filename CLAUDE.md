# claude-plugins

Multi-plugin repository for Claude Code plugins.

## Structure

- `plugins/` -- each subdirectory is a plugin with `.claude-plugin/plugin.json`
- `scripts/sync-marketplace.ts` -- auto-discovers plugins, regenerates `.claude-plugin/marketplace.json`
- Skills live in `plugins/{name}/skills/{skill-name}/SKILL.md`
- Reference docs in `references/`, examples in `examples/`

## Build and Test

- `just check` -- sync marketplace.json and verify it's up to date
- `just sync` -- regenerate marketplace.json from discovered plugins
- `just bump <plugin> [version]` -- bump plugin version, commit, tag, push
- `just retag <plugin> <version>` -- re-tag to re-trigger workflows

Tags use `{plugin}/v{version}` format (e.g., `just-bootstrap/v0.2.0`).
Bump and retag take bare version numbers (no `v` prefix).

## Adding a Plugin

1. Create `plugins/{name}/.claude-plugin/plugin.json` with metadata
2. Add skills under `plugins/{name}/skills/`
3. Run `just sync` to update marketplace.json

## Conventions

- SKILL.md under 500 lines; heavy content goes in references/
- Reference files organized by concern, with language-specific sections
- Explain reasoning in skill instructions, not rote rules

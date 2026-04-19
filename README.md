# claude-plugins

Claude Code plugins by Ted Naleid. This repo is a [marketplace](https://docs.anthropic.com/en/docs/claude-code/plugins); install the whole set or pick individual plugins.

## Quick start

Add the marketplace once, then install what you want:

```bash
claude plugin marketplace add tednaleid/claude-plugins
claude plugin install just-bootstrap@tednaleid     # or any plugin listed below
```

Or, if you've cloned this repo locally, install every plugin in one shot:

```bash
just install
```

`just install` adds the marketplace, refreshes the cache, and installs each plugin listed under `plugins/`. Re-run it any time to pick up new or updated plugins.

## Updating

Third-party marketplaces do not auto-update by default. To pull the latest:

```bash
claude plugin marketplace update tednaleid
claude plugin update <plugin-name>@tednaleid
```

Or enable auto-update via `/plugin` > Marketplaces tab > select `tednaleid` > Enable auto-update. With that on, the marketplace refreshes at session startup and plugins update automatically.

To pick up plugin changes mid-session without restarting, use `/reload-plugins`.

## Plugins

### just-bootstrap

Audit and set up CI, release, Justfile, and Homebrew infrastructure for a repo. Detects language (Rust, Zig, Swift, TypeScript/Bun) and project type (CLI vs. macOS app) automatically, then generates normalized build/release tooling matched to battle-tested patterns.

**Use when:** you're starting a new project and need CI + release wired up, or normalizing an existing project's build infrastructure.

**Trigger:** mention CI setup, release automation, homebrew tap, Justfile recipes, bump/retag commands, or pre-commit hooks.

```bash
claude plugin install just-bootstrap@tednaleid
claude plugin update just-bootstrap@tednaleid
```

### onboard-codebase

Survey an unfamiliar codebase and write a concise `ONBOARDING.md` (under 100 lines) covering language, frameworks, build/test/lint commands, architecture, entry points, and CI/CD. Lives beside `CLAUDE.md` and loads on demand, so orientation doesn't bloat every turn.

**Use when:** you land in a new repo and want a fresh Claude (or a human teammate) to get productive fast, or when existing onboarding docs have gone stale.

**Trigger:** ask to be onboarded to a repo, oriented to a new project, or to refresh onboarding docs.

```bash
claude plugin install onboard-codebase@tednaleid
claude plugin update onboard-codebase@tednaleid
```

### context-relay

Serialize a long Claude Code session's working state into a relay markdown doc, then iteratively refine it by consulting a fresh-context reviewer subagent until the baton is passable. Ends with a copy-paste resume prompt for a brand-new Claude instance; paste it into a fresh session and pick up without a Q&A round.

**Use when:** your context is getting full, you're about to `/clear`, or you want to checkpoint a session so someone (or future-you) can resume cleanly.

**Trigger:** mention context getting full, handing off a session, before compaction, passing the baton, checkpointing current work, or asking for a resume prompt.

```bash
claude plugin install context-relay@tednaleid
claude plugin update context-relay@tednaleid
```

## Repo layout

- `plugins/<name>/`: one directory per plugin, each with `.claude-plugin/plugin.json`, `skills/`, and (optionally) `agents/`
- `.claude-plugin/marketplace.json`: auto-generated index; do not edit by hand
- `scripts/sync-marketplace.ts`: regenerates `marketplace.json` by discovering `plugins/*/`
- `justfile`: dev recipes (see below)

## Development

Recipes in `justfile`:

| Command | What it does |
|---|---|
| `just install` | Add the marketplace, refresh, and install every plugin |
| `just bump <plugin> [version]` | Regenerate `marketplace.json`, commit any changes, tag `<plugin>/v<version>`, push |
| `just retag <plugin> <version>` | Delete the GitHub release and re-tag to re-trigger release workflows |
| `just check` | CI guard: regenerate `marketplace.json` and fail if it differs from HEAD |

Tags use `<plugin>/v<version>` format (e.g., `just-bootstrap/v0.2.0`). `bump` and `retag` take bare version numbers (no `v` prefix). `bump` is idempotent on the same version; it still regenerates `marketplace.json` and commits any drift before tagging.

### Adding a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with metadata.
2. Add skills under `plugins/<name>/skills/` and (optionally) agents under `plugins/<name>/agents/`.
3. Run `just bump <name> 0.1.0` to regenerate the marketplace, commit, tag, and publish.

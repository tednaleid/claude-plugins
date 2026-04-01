# claude-plugins

Claude Code plugins by Ted Naleid.

## Installation

Add the marketplace (one time):

```bash
claude plugin marketplace add tednaleid/claude-plugins
```

Install a plugin:

```bash
claude plugin install just-bootstrap@tednaleid
```

## Updating

Third-party marketplaces do not auto-update by default. To get the latest,
refresh the marketplace (pulls from GitHub), then update the plugin:

```bash
claude plugin marketplace update tednaleid
claude plugin update just-bootstrap@tednaleid
```

Or enable auto-update via `/plugin` > Marketplaces tab > select `tednaleid` >
Enable auto-update. With auto-update enabled, the marketplace refreshes at
session startup and plugins update automatically.

To pick up plugin changes mid-session without restarting, use `/reload-plugins`.

## Plugins

- **just-bootstrap** -- Audit and set up CI, release, Justfile, and Homebrew infrastructure for any repo. Detects language (Rust, Zig, Swift, TypeScript/Bun) automatically and generates normalized build/release tooling. Run `/just-bootstrap` in any project.

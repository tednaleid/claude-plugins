# claude-plugins

Claude Code plugins by Ted Naleid.

## Installation

Add the marketplace (one time):

```bash
/plugin marketplace add tednaleid/claude-plugins
```

Install a plugin:

```bash
/plugin install just-bootstrap@tednaleid
```

## Updating

Third-party marketplaces do not auto-update by default. To get the latest:

```bash
claude plugin update just-bootstrap@tednaleid
```

Or enable auto-update for this marketplace: `/plugin` > Marketplaces tab >
select `tednaleid` > Enable auto-update. With auto-update enabled, plugins
refresh at session startup.

To pick up changes mid-session without restarting:

```
/reload-plugins
```

## Plugins

- **just-bootstrap** -- Audit and set up CI, release, Justfile, and Homebrew infrastructure for any repo. Detects language (Rust, Zig, Swift, TypeScript/Bun) automatically and generates normalized build/release tooling. Run `/just-bootstrap` in any project.

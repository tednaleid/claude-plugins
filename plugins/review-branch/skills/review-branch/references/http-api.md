# Review daemon HTTP API

One daemon serves every review. Binds 127.0.0.1 only; default port 43117,
override with `REVIEW_BRANCH_PORT`. No auth: localhost trust is the threat
model. Routes are the filesystem: `/<repo-id>/<slug>/round-N/` maps to the
same path under the data root. There is no registry; the daemon serves what
exists on disk.

## Lifecycle

- `review-branch url <round-dir>` starts the server if needed (detached via
  `review-branch serve`, survives the launching session), restarts it when
  the CLI is newer than the running server, and prints the review URL.
  Idempotent.
- `review-branch open <round-dir>` does all of that and launches the URL in
  the browser.
- Both take the target as optional. It may be a round directory, an MR/PR
  number, a branch, or a slug; with none it is the branch checked out in the
  cwd. Anything that resolves to no round falls back to the index page rather
  than failing, with the candidates printed to stderr.
- `review-branch list [--all]` prints those candidates as `slug/round  branch`,
  newest first, for this repo or every repo.
- `review-branch serve` runs the server in the foreground, printing a
  startup line with the clickable index URL before it blocks.
- `review-branch stop` stops it via the pidfile in
  `${XDG_STATE_HOME:-~/.local/state}/review-branch/`. Log: `daemon.log` there.
- The daemon stays up until stopped or reboot.

## Endpoints

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/health` | `{"app": "review-branch", "version", "data_root"}` |
| GET | `/` | index of all reviews, newest activity first |
| GET | `/<rid>/<slug>/round-N/` | review page rendered in memory (served mode) |
| GET | `/<rid>/<slug>/round-N` | 301 to the trailing-slash form |
| GET | `.../api/state` | current state.json (`{"findings": {}}` if absent) |
| GET | `.../api/version` | `{"token": <changes when toml/state/assets change>}` |
| POST | `.../api/state` | validate `{"findings": {...}}`, stamp updated_at, write state.json, refresh review.html snapshot, git commit, return `{"ok": true, "token"}` |
| POST | `.../api/preview` | render `{"markdown": "..."}` to `{"html": "..."}`; writes nothing, holds no lock |
| POST | `/api/shutdown` | stop the daemon (used by the version handshake) |

Unknown routes and paths outside the data root return 404 JSON. Invalid JSON
bodies, a state payload that isn't `{"findings": {...}}`, or a preview
payload without a string `markdown` field return 400. Every POST also checks
the Host header (must be `127.0.0.1` or `localhost`) and, when an Origin
header is present, that it matches `http://127.0.0.1:<port>` or
`http://localhost:<port>` for the running server's port; either check
failing returns 403 and the request is not processed. The page saves
whole-document state (debounced); disposition is a boolean post toggle
("post" or null), off by default. Comment edits render in place through the
preview endpoint (no full-page reload); the page separately polls
`api/version` and reloads when clean and idle, holds unsaved changes with a
banner and retry when the server is unreachable, and is read-only when
opened via `file://`.

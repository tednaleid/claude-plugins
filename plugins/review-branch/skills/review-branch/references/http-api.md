# Review daemon HTTP API

One daemon serves every review. Binds 127.0.0.1 only; default port 43117,
override with `REVIEW_BRANCH_PORT`. No auth: localhost trust is the threat
model. Routes are the filesystem: `/<repo-id>/<slug>/round-N/` maps to the
same path under the data root. There is no registry; the daemon serves what
exists on disk.

## Lifecycle

- `review-branch open <round-dir>` starts the daemon if needed (detached,
  survives the launching session), restarts it when the CLI is newer than the
  running daemon, and prints the review URL. Idempotent.
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
| POST | `/api/shutdown` | stop the daemon (used by the version handshake) |

Unknown routes and paths outside the data root return 404 JSON. Invalid JSON
bodies return 400. The page saves whole-document state (debounced);
disposition is a boolean post toggle ("post" or null), off by default. The
page polls `api/version` and reloads when clean, holds unsaved changes with a
banner and retry when the daemon is unreachable, and is read-only when opened
via `file://`.

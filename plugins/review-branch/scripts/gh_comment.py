#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///

# ABOUTME: posts line-anchored review comments to a GitHub pull request via gh
# ABOUTME: prepends the From Claude marker, validates diff anchors, blocks duplicates

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
FILE_RE = re.compile(r"^\+\+\+ b/(.*)$")

MARKER = "> **From Claude:**"
MARKER_PROBE = "**From Claude:**"


def split_files(diff_text):
    """Map each new-file path to its unified-diff hunk text.

    `gh pr diff` emits one combined diff; file sections start at `diff --git`.
    Key on the `+++ b/<path>` header and keep the text from the first `@@`.
    A `+++ /dev/null` (deleted file) yields no path and is skipped.
    """
    files = {}
    path = None
    hunk_lines = []
    in_hunks = False

    def flush():
        if path and hunk_lines:
            files[path] = "\n".join(hunk_lines)

    for raw in diff_text.splitlines():
        if raw.startswith("diff --git"):
            flush()
            path, hunk_lines, in_hunks = None, [], False
        elif raw.startswith("+++ "):
            m = FILE_RE.match(raw)
            path = m.group(1) if m else None
        elif raw.startswith("@@"):
            in_hunks = True
            hunk_lines.append(raw)
        elif in_hunks:
            hunk_lines.append(raw)
    flush()
    return files


def parse_diff_lines(hunk_text):
    """One entry per hunk-body line, numbered on the new (RIGHT) side."""
    lines = []
    new_line = 0
    for raw in hunk_text.splitlines():
        header = HUNK_RE.match(raw)
        if header:
            new_line = int(header.group(1))
            continue
        if raw.startswith("+"):
            lines.append({"kind": "added", "new_line": new_line})
            new_line += 1
        elif raw.startswith("-"):
            lines.append({"kind": "removed", "new_line": None})
        elif raw.startswith(" "):
            lines.append({"kind": "context", "new_line": new_line})
            new_line += 1
    return lines


def find_anchor(diff_lines, line):
    """The line number if it is an added or context line in the diff, else None.

    GitHub comments anchor to a single new-side line with side RIGHT; a removed
    line has no new-side number and cannot be targeted.
    """
    for entry in diff_lines:
        if entry["new_line"] == line and entry["kind"] in ("added", "context"):
            return line
    return None


def nearest_addressable(diff_lines, line, count=3):
    """Addressable new-side lines closest to a rejected target, nearest first."""
    candidates = {
        e["new_line"]
        for e in diff_lines
        if e["new_line"] is not None and e["kind"] in ("added", "context")
    } - {line}
    return sorted(candidates, key=lambda n: (abs(n - line), n))[:count]


def ensure_marker(body):
    """Return the body with exactly one attribution marker at the top."""
    if MARKER_PROBE in body:
        return body.strip("\n")
    return f"{MARKER}\n\n{body.strip()}"


def find_duplicates(comments, path, line):
    """Ids of Claude-authored review comments already at path:line."""
    hits = []
    for c in comments:
        if MARKER_PROBE not in c.get("body", ""):
            continue
        c_line = c.get("line")
        if c_line is None:
            c_line = c.get("original_line")
        if c.get("path") == path and c_line == line:
            hits.append(c.get("id"))
    return hits


def gh(args, check=True):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if check and out.returncode != 0:
        raise SystemExit(f"gh {' '.join(args)} failed:\n{out.stderr.strip()}")
    return out


def owner_repo():
    out = gh(["repo", "view", "--json", "owner,name",
              "--jq", '"\\(.owner.login)/\\(.name)"'])
    return out.stdout.strip()


def resolve_pr(explicit):
    if explicit:
        return explicit
    out = gh(["pr", "view", "--json", "number", "--jq", ".number"], check=False)
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit("no PR for this branch; pass --pr")
    return int(out.stdout.strip())


def head_sha(n):
    out = gh(["pr", "view", str(n), "--json", "headRefOid", "--jq", ".headRefOid"])
    return out.stdout.strip()


def diff_index(n):
    out = gh(["pr", "diff", str(n)])
    return {path: parse_diff_lines(text) for path, text in split_files(out.stdout).items()}


def existing_comments(repo, n):
    """gh --paginate merges array pages into one array, so json.loads is enough."""
    out = gh(["api", f"repos/{repo}/pulls/{n}/comments", "--paginate"])
    return json.loads(out.stdout or "[]")


def read_body(source):
    if source in (None, "-"):
        return sys.stdin.read()
    return Path(source).read_text()


def load_items(args):
    """Normalise the input shapes into one list of comments to post."""
    if args.manifest:
        raw = json.loads(Path(args.manifest).read_text())
        return [
            {
                "path": item["file"],
                "line": item["line"],
                "body": item.get("body") or Path(item["body_file"]).read_text(),
            }
            for item in raw
        ]
    if args.general:
        return [{"path": None, "line": None, "body": read_body(args.body_file)}]
    path, _, line = args.target.rpartition(":")
    return [{"path": path, "line": int(line), "body": read_body(args.body_file)}]


def check_items(items, index, comments, allow_duplicate):
    """Resolve every anchor before anything is posted. Returns (ready, problems)."""
    ready, problems = [], []
    for item in items:
        if item["path"] is None:
            ready.append({**item, "anchor": None})
            continue
        diff_lines = index.get(item["path"])
        if diff_lines is None:
            problems.append(f"{item['path']}: not in this PR's diff")
            continue
        anchor = find_anchor(diff_lines, item["line"])
        if anchor is None:
            near = nearest_addressable(diff_lines, item["line"])
            near_text = ", ".join(str(n) for n in near) or "none in this file"
            problems.append(
                f"{item['path']}:{item['line']} is not in the diff; "
                f"addressable lines nearby: {near_text}"
            )
            continue
        dupes = find_duplicates(comments, item["path"], item["line"])
        if dupes and not allow_duplicate:
            problems.append(
                f"{item['path']}:{item['line']} already has a From Claude comment "
                f"({dupes[0]}); pass --allow-duplicate to post anyway"
            )
            continue
        ready.append({**item, "anchor": anchor})
    return ready, problems


def post_one(repo, n, item, sha):
    if item["anchor"] is None:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
            handle.write(ensure_marker(item["body"]))
            body_path = handle.name
        out = gh(["pr", "comment", str(n), "--body-file", body_path], check=False)
        return {"ok": out.returncode == 0, "landed": "general note",
                "detail": out.stdout.strip() or out.stderr.strip()}
    payload = {
        "body": ensure_marker(item["body"]),
        "commit_id": sha,
        "path": item["path"],
        "line": item["anchor"],
        "side": "RIGHT",
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(payload, handle)
        payload_path = handle.name
    out = gh(["api", f"repos/{repo}/pulls/{n}/comments", "-X", "POST",
              "--input", payload_path], check=False)
    landed = f"{item['path']}:{item['line']}"
    if out.returncode != 0:
        return {"ok": False, "landed": landed, "detail": out.stderr.strip()}
    resp = json.loads(out.stdout or "{}")
    return {"ok": bool(resp.get("id")), "landed": landed, "id": resp.get("id")}


def describe(item):
    return "general note" if item["path"] is None else f"{item['path']}:{item['line']}"


def main():
    parser = argparse.ArgumentParser(
        description="Post line-anchored review comments to a GitHub PR."
    )
    parser.add_argument("target", nargs="?", help="FILE:LINE anchor in the new file")
    parser.add_argument("--pr", type=int, help="PR number; inferred from the branch when omitted")
    parser.add_argument("--body-file", help="markdown body, or - for stdin")
    parser.add_argument("--manifest", help="JSON array of {file, line, body|body_file}")
    parser.add_argument("--general", action="store_true", help="post an unpositioned PR comment")
    parser.add_argument("--dry-run", action="store_true", help="print payloads only")
    parser.add_argument("--allow-duplicate", action="store_true",
                        help="post even when a From Claude comment already sits on that line")
    args = parser.parse_args()

    if not (args.manifest or args.general or args.target):
        parser.error("give a FILE:LINE target, --manifest, or --general")

    repo = owner_repo()
    n = resolve_pr(args.pr)
    items = load_items(args)
    sha = head_sha(n)
    index = diff_index(n)
    comments = existing_comments(repo, n)

    ready, problems = check_items(items, index, comments, args.allow_duplicate)
    for problem in problems:
        print(f"BLOCKED  {problem}", file=sys.stderr)
    if problems:
        raise SystemExit(f"{len(problems)} of {len(items)} anchors unusable; nothing posted")

    print(f"Posting {len(ready)} comment(s) to PR #{n}, each labeled From Claude:",
          file=sys.stderr)
    for item in ready:
        print(f"  {describe(item)}", file=sys.stderr)

    if args.dry_run:
        for item in ready:
            print(f"\n--- {describe(item)} ---\n{ensure_marker(item['body'])}")
        return 0

    failures = 0
    for item in ready:
        result = post_one(repo, n, item, sha)
        if result["ok"]:
            suffix = f"  id={result['id']}" if result.get("id") else ""
            print(f"OK       {result['landed']}{suffix}")
        else:
            failures += 1
            print(f"FAILED   {describe(item)}  {result.get('detail', '')}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

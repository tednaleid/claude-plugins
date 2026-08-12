#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["markdown-it-py"]
# ///

# ABOUTME: review-branch tool: renders review.toml to a collaborative HTML tracker,
# ABOUTME: runs the review daemon, merges browser state, emits posting manifests

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from markdown_it import MarkdownIt

__version__ = "0.3.0"  # SYNC_PLUGIN_VERSION kept in step with plugin.json by scripts/sync-marketplace.ts
APP_NAME = "review-branch"
DEFAULT_PORT = 43117

SUBCOMMANDS = ("init", "render", "open", "status", "manifest", "install", "serve", "stop")


def data_root() -> Path:
    override = os.environ.get("REVIEW_BRANCH_HOME")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME", "~/.local/share")
    return Path(xdg).expanduser() / APP_NAME


def state_root() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME", "~/.local/state")
    return Path(xdg).expanduser() / APP_NAME


def git(cwd, *args, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_ok(cwd, *args) -> str | None:
    try:
        return git(cwd, *args)
    except RuntimeError:
        return None


def main_worktree(repo_dir: Path) -> Path:
    common = git(repo_dir, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common).parent


def repo_id(repo_dir: Path) -> str:
    root = main_worktree(repo_dir)
    seed = git_ok(repo_dir, "remote", "get-url", "origin") or str(root)
    digest = hashlib.sha256(seed.encode()).hexdigest()[:4]
    return f"{root.name}-{digest}"


def ensure_data_repo() -> Path:
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").is_dir():
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        git(root, "config", "user.name", APP_NAME)
        git(root, "config", "user.email", f"{APP_NAME}@localhost")
    return root


def data_commit(message: str) -> None:
    root = ensure_data_repo()
    git(root, "add", "-A")
    if git(root, "status", "--porcelain"):
        git(root, "commit", "-q", "-m", message)


def cmd_init(slug: str, repo_dir: Path) -> Path:
    if not slug or slug in (".", "..") or "/" in slug or "\\" in slug or slug.startswith((".", "-")):
        raise SystemExit(f"invalid slug {slug!r}: must be a single path segment")
    ensure_data_repo()
    base = data_root() / repo_id(repo_dir) / slug
    existing = []
    for p in base.glob("round-*"):
        tail = p.name.removeprefix("round-")
        if p.is_dir() and tail.isdigit():
            existing.append(int(tail))
    round_dir = base / f"round-{max(existing, default=0) + 1}"
    round_dir.mkdir(parents=True)
    return round_dir.resolve()


def load_review(round_dir: Path) -> dict:
    path = round_dir / "review.toml"
    try:
        return tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise SystemExit(f"{path}: {e}")


def load_state(round_dir: Path) -> dict:
    path = round_dir / "state.json"
    if not path.exists():
        return {"findings": {}}
    return json.loads(path.read_text())


def merged_findings(review: dict, state: dict) -> list[dict]:
    out = []
    entries = state.get("findings", {})
    for f in review.get("findings", []):
        s = entries.get(f["id"], {})
        crev = f.get("comment_rev", 1)
        edited = s.get("edited_comment")
        edited_current = edited is not None and s.get("edited_comment_rev") == crev
        note = s.get("note")
        merged = dict(f)
        merged.update(
            disposition=s.get("disposition"),
            note=note,
            note_stale=note is not None and s.get("note_rev", 0) < crev,
            edited_comment=edited,
            edited_stale=edited is not None and not edited_current,
            postable_body=edited if edited_current else f.get("comment"),
            posted=bool(f.get("posted_url")),
        )
        out.append(merged)
    return out


def parse_anchor(finding: dict) -> tuple[str, int | None]:
    anchor = finding.get("anchor")
    if anchor and ":" in anchor:
        path, _, line = anchor.rpartition(":")
        if line.isdigit():
            return path, int(line)
    nums = re.findall(r"\d+", str(finding.get("lines", "")))
    return finding["file"], int(nums[-1]) if nums else None


def cmd_status(round_dir: Path) -> dict:
    review = load_review(round_dir)
    return {
        "review": review.get("review", {}),
        "findings": merged_findings(review, load_state(round_dir)),
    }


def cmd_manifest(round_dir: Path, exclude: set[str]) -> list[dict]:
    entries = []
    for f in merged_findings(load_review(round_dir), load_state(round_dir)):
        if f["disposition"] != "post" or f["posted"] or f["id"] in exclude:
            continue
        if f.get("commentable", True) is False:
            continue
        path, line = parse_anchor(f)
        body = f["postable_body"]
        if line is None or not body:
            raise SystemExit(
                f"{f['id']}: cannot build manifest entry (line={line}, body empty={not body})"
            )
        entries.append({"file": path, "line": line, "body": body})
    return entries


_MD = MarkdownIt("commonmark", {"html": False}).enable("table")


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def md_html(text: str) -> str:
    return _MD.render(text or "")


def diff_link(meta: dict, path: str, line: int | None) -> str | None:
    url = meta.get("url")
    if not url or safe_href(url) == "#":
        return None
    if meta.get("vcs") == "glab":
        return f"{url}/diffs#diff-content-{hashlib.sha1(path.encode()).hexdigest()}"
    if meta.get("vcs") == "gh":
        frag = f"diff-{hashlib.sha256(path.encode()).hexdigest()}"
        if line:
            frag += f"R{line}"
        return f"{url}/files#{frag}"
    return None


def version_token(round_dir: Path) -> str:
    digest = hashlib.sha1()
    names = ["review.toml", "state.json"]
    review_path = round_dir / "review.toml"
    if review_path.exists():
        names += [a.get("path", "") for a in load_review(round_dir).get("assets", [])]
    for name in names:
        p = round_dir / name
        if name and p.exists():
            st = p.stat()
            digest.update(f"{name}:{st.st_mtime_ns}:{st.st_size};".encode())
    return digest.hexdigest()[:16]


def route_for(round_dir: Path) -> str:
    root = data_root().resolve()
    try:
        rel = round_dir.resolve().relative_to(root)
    except ValueError:
        raise SystemExit(f"{round_dir} is not under the data root {root}")
    if len(rel.parts) != 3:
        raise SystemExit(f"{round_dir}: expected <repo-id>/<slug>/round-N under the data root")
    return "/".join(rel.parts)


def meta_row(meta: dict) -> str:
    spans = []
    label = {"glab": "MR", "gh": "PR"}.get(meta.get("vcs"))
    if label and meta.get("url") and meta.get("number"):
        mark = "!" if label == "MR" else "#"
        spans.append(
            f'<span><strong>{label}:</strong> <a href="{safe_href(meta["url"])}">{mark}{meta["number"]}</a></span>'
        )
    if meta.get("source_branch"):
        arrow = f'{esc(meta["source_branch"])} -&gt; {esc(meta.get("target_branch", ""))}'
        spans.append(f"<span><strong>Branch:</strong> {arrow}</span>")
    for key, name in (("commits", "Commits"), ("files", "Files"), ("spec", "Spec")):
        if meta.get(key):
            spans.append(f"<span><strong>{name}:</strong> {esc(meta[key])}</span>")
    return "\n".join(spans)


def summary_cards(findings: list[dict], minor_count: int = 0) -> str:
    counts: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1
    cards = []
    for sev, name in (("high", "High"), ("med", "Medium")):
        cards.append(
            f'<div class="card"><div class="num {sev}">{counts.get(sev, 0)}</div>'
            f'<div class="label">{name}</div></div>'
        )
    cards.append(
        f'<div class="card"><div class="num low">{minor_count}</div>'
        f'<div class="label">Minor notes</div></div>'
    )
    return "\n".join(cards)


def minor_html(minor: list[dict]) -> str:
    if not minor:
        return ""
    rows = []
    for m in minor:
        loc = f'{m.get("file", "")}:{m["line"]}' if m.get("line") else m.get("file", "")
        rows.append(
            "<tr>"
            f'<td>{esc(m.get("lens", ""))}</td>'
            f"<td><code>{esc(loc)}</code></td>"
            f"<td>{md_html(m.get('note', ''))}</td>"
            "</tr>"
        )
    head = "<tr><th>Lens</th><th>Location</th><th>Note</th></tr>"
    body = "\n".join(rows)
    return (
        f'<details class="minor"><summary>Minor notes ({len(minor)})</summary>\n'
        f"<table>\n{head}\n{body}\n</table>\n</details>"
    )


def assets_html(round_dir: Path, review: dict) -> str:
    parts = []
    for a in review.get("assets", []):
        p = round_dir / a["path"]
        if not p.resolve().is_relative_to(round_dir.resolve()):
            raise SystemExit(f"asset {a['path']}: escapes the round directory")
        try:
            content = p.read_text()
        except OSError as e:
            raise SystemExit(f"asset {p}: {e}")
        if a.get("type") == "svg":
            content = re.sub(r"^\s*<\?xml[^>]*\?>", "", content)
        cap = f"<figcaption>{esc(a['caption'])}</figcaption>" if a.get("caption") else ""
        parts.append(f'<figure class="asset">{content}{cap}</figure>')
    return "\n".join(parts)


def table_html(title: str, headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<h2>{esc(title)}</h2>\n<table>\n<tr>{head}</tr>\n{body}\n</table>"


def _dash(value) -> str:
    return esc(value) if value else "&mdash;"


def safe_href(url) -> str:
    url = str(url or "")
    if re.match(r"^https?://", url, re.IGNORECASE):
        return url
    return "#"


def finding_card(f: dict, meta: dict) -> str:
    sev = f.get("severity", "info")
    sev_class = sev if sev in ("high", "med", "low", "info") else "info"
    fid = f["id"]
    _, line = parse_anchor(f)
    fileref = f'{f["file"]}:{f["lines"]}' if f.get("lines") else f["file"]
    link = diff_link(meta, f["file"], line)
    file_html = f'<a href="{esc(link)}">{esc(fileref)}</a>' if link else esc(fileref)
    also = f.get("also") or []
    also_html = (
        f'<div class="also">also: '
        + ", ".join(f"<code>{esc(a)}</code>" for a in also)
        + "</div>"
    ) if also else ""
    head = [
        f'<span class="num">{esc(fid)}</span>',
        f'<span class="title">{esc(f.get("title", ""))}</span>',
        f'<span class="badge {sev_class}">{esc(sev)}</span>',
    ]
    head += [f'<span class="tag">{esc(lens)}</span>' for lens in f.get("lenses", [])]
    if f["posted"]:
        head.append(f'<a class="badge posted" href="{safe_href(f.get("posted_url", ""))}">posted</a>')

    commentable = f.get("commentable", True) and not f["posted"]
    control = [
        '<div class="control-row">',
        '<button class="fold-toggle" type="button" aria-expanded="true" '
        'title="Fold (Enter: fold + next, z: in place)"></button>',
    ]
    if commentable:
        post_checked = " checked" if f["disposition"] == "post" else ""
        control.append(
            f'<label class="post-toggle" title="Toggle Post (space)"><input type="checkbox" '
            f'class="post-chk"{post_checked}> Post to MR</label>'
        )
    control.append("</div>")

    body_parts = [md_html(f.get("body", ""))]
    if f.get("snippet"):
        body_parts.append(f"<pre><code>{esc(f['snippet'])}</code></pre>")
    if f.get("fix"):
        body_parts.append(f"<p><strong>Suggested fix:</strong> {esc(f['fix'])}</p>")
    if f["posted"]:
        body_parts.append(f"<pre><code>{esc(f.get('posted_body', ''))}</code></pre>")
    elif commentable:
        area = ['<div class="comment-area">']
        if f["note_stale"]:
            area.append(f'<div class="applied">applied: {esc(f["note"])}</div>')
        body = f["postable_body"] or ""
        view_html = md_html(body) if body else '<em class="placeholder">No draft. Click to add one.</em>'
        area.append('<label class="small">Comment draft (click to edit)</label>')
        area.append(f'<div class="comment-view" tabindex="0">{view_html}</div>')
        area.append(f'<textarea class="comment" hidden>{esc(body)}</textarea>')
        area.append('<label class="small">Note to Claude</label>')
        note_now = "" if f["note_stale"] else (f.get("note") or "")
        area.append(
            f'<textarea class="note" placeholder="tell Claude how to adjust this">{esc(note_now)}</textarea>'
        )
        area.append("</div>")
        body_parts.append("\n".join(area))

    parts = [
        f'<div class="finding {sev_class}" data-fid="{esc(fid)}" data-rev="{esc(f.get("comment_rev", 1))}">',
        f'<div class="head">{" ".join(head)}</div>',
        f'<div class="file">{file_html}</div>',
        also_html,
        "\n".join(control),
        '<div class="collapse-body">',
        "\n".join(body_parts),
        "</div>",
        "</div>",
    ]
    return "\n".join(p for p in parts if p)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title><!--TITLE--></title>
<style>
  :root {
    --bg: #0f1115; --panel: #161922; --panel2: #1c2030; --border: #2a3042;
    --text: #e6e8ee; --muted: #9aa3b2; --accent: #7aa2f7;
    --red: #f7768e; --amber: #e0af68; --green: #9ece6a; --blue: #7dcfff;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 32px 24px 80px; }
  h1 { margin: 0 0 4px; font-size: 22px; }
  h2 { margin: 32px 0 10px; font-size: 17px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
  .sub { color: var(--muted); font-size: 13px; margin-bottom: 24px; }
  .meta { display: flex; gap: 16px; flex-wrap: wrap; color: var(--muted); font-size: 12px; margin: 6px 0 22px; }
  .meta strong { color: var(--text); font-weight: 500; }
  a { color: var(--accent); }
  code, pre { font-family: var(--mono); font-size: 12.5px; }
  pre { background: var(--panel2); border: 1px solid var(--border); border-radius: 6px;
        padding: 12px; overflow-x: auto; margin: 8px 0; }
  code { background: var(--panel2); padding: 1px 5px; border-radius: 3px; }
  pre code { background: transparent; padding: 0; }
  figure.asset { margin: 20px 0; background: var(--panel); border: 1px solid var(--border);
                 border-radius: 6px; padding: 16px; overflow-x: auto; }
  figure.asset figcaption { color: var(--muted); font-size: 12px; margin-top: 8px; }
  .finding { background: var(--panel); border: 1px solid var(--border);
             border-left: 4px solid var(--muted); border-radius: 6px; padding: 14px 16px; margin: 14px 0; }
  .finding.high { border-left-color: var(--red); }
  .finding.med  { border-left-color: var(--amber); }
  .finding.low  { border-left-color: var(--blue); }
  .finding.info { border-left-color: var(--green); }
  .finding.active { border-left-width: 6px; box-shadow: inset 0 0 0 1px var(--accent); }
  .finding.collapsed .collapse-body { display: none; }
  .finding .head { display: flex; gap: 10px; align-items: baseline; margin-bottom: 4px; flex-wrap: wrap; }
  .finding .num { color: var(--muted); font-family: var(--mono); font-size: 12px; min-width: 28px; }
  .finding .title { font-weight: 600; font-size: 14.5px; }
  .badge { font-family: var(--mono); font-size: 10.5px; padding: 1px 7px; border-radius: 10px;
           text-transform: uppercase; letter-spacing: .04em; }
  .badge.high { background: rgba(247,118,142,.15); color: var(--red); }
  .badge.med  { background: rgba(224,175,104,.15); color: var(--amber); }
  .badge.low  { background: rgba(125,207,255,.15); color: var(--blue); }
  .badge.info { background: rgba(158,206,106,.15); color: var(--green); }
  .badge.posted { background: rgba(158,206,106,.15); color: var(--green); text-decoration: none; }
  .file { color: var(--muted); font-family: var(--mono); font-size: 12px; }
  .control-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
  .fold-toggle { appearance: none; -webkit-appearance: none; background: none; border: 1px solid transparent;
                 color: var(--muted); cursor: pointer; width: 24px; height: 24px; border-radius: 4px;
                 display: inline-flex; align-items: center; justify-content: center; padding: 0; }
  .fold-toggle::before { content: "\\25be"; font-size: 16px; line-height: 1; }
  .finding.collapsed .fold-toggle::before { content: "\\25b8"; }
  .fold-toggle:hover { color: var(--text); border-color: var(--border); background: var(--panel2); }
  .collapse-body { margin-top: 8px; }
  .small { color: var(--muted); font-size: 12.5px; display: block; margin-top: 10px; }
  .tag { display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 4px;
         background: var(--panel2); border: 1px solid var(--border); color: var(--muted); }
  table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; }
  th, td { text-align: left; border-bottom: 1px solid var(--border); padding: 8px 10px;
           vertical-align: top; font-size: 13px; }
  th { color: var(--muted); font-weight: 500; }
  .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                  gap: 10px; margin: 12px 0 20px; }
  .summary-grid .card { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 12px; }
  .summary-grid .num { font-size: 22px; font-weight: 600; }
  .summary-grid .label { color: var(--muted); font-size: 12px; }
  .num.high { color: var(--red); } .num.med { color: var(--amber); }
  .num.low { color: var(--blue); } .num.info { color: var(--green); }
  .comment-area { margin-top: 12px; border-top: 1px solid var(--border); padding-top: 4px; }
  .comment-view { cursor: text; margin-top: 4px; padding: 8px 10px; background: var(--panel2);
                  color: var(--text); border: 1px solid var(--border); border-radius: 6px;
                  font-size: 12.5px; }
  .comment-view:hover { border-color: var(--accent); }
  .comment-view .placeholder { color: var(--muted); }
  textarea { width: 100%; min-height: 72px; margin-top: 4px; background: var(--panel2);
             color: var(--text); border: 1px solid var(--border); border-radius: 6px;
             padding: 8px; font: 12.5px/1.5 var(--mono); resize: vertical; }
  textarea.comment { min-height: 140px; }
  textarea.note { min-height: 40px; font-family: inherit; }
  textarea:disabled, input:disabled { opacity: .5; }
  .applied { color: var(--muted); font-size: 12px; font-style: italic; margin-top: 8px; }
  .post-toggle { display: inline-flex; align-items: center; gap: 8px;
                 padding: 4px 10px 4px 4px; border: 1px solid var(--border); border-radius: 999px;
                 background: var(--panel2); color: var(--muted); font-size: 12.5px; cursor: pointer;
                 width: fit-content; }
  .post-toggle input[type="checkbox"] { appearance: none; -webkit-appearance: none; width: 30px;
                 height: 18px; margin: 0; border-radius: 999px; background: var(--border);
                 position: relative; cursor: pointer; transition: background .15s; }
  .post-toggle input[type="checkbox"]::after { content: ""; position: absolute; top: 2px; left: 2px;
                 width: 14px; height: 14px; border-radius: 50%; background: var(--muted); transition: left .15s; }
  .post-toggle input[type="checkbox"]:checked { background: var(--green); }
  .post-toggle input[type="checkbox"]:checked::after { left: 14px; background: var(--panel); }
  .post-toggle:has(input:checked) { background: rgba(158,206,106,.15); border-color: var(--green); color: var(--green); }
  .controls { display: flex; gap: 10px; align-items: center; margin: 8px 0 18px;
              font-size: 12px; color: var(--muted); }
  .progress { font-family: var(--mono); }
  .save-status { font-family: var(--mono); font-size: 11.5px; }
  .save-status::before { content: "\\25cf"; margin-right: 5px; }
  .save-status.saved { color: var(--muted); }
  .save-status.saving { color: var(--accent); }
  .save-status.error { color: var(--red); }
  .kbd-hint { margin-left: auto; cursor: pointer; color: var(--muted); font-size: 11.5px;
              border: 1px solid var(--border); border-radius: 999px; padding: 2px 9px;
              background: var(--panel2); }
  .kbd-hint:hover { color: var(--text); border-color: var(--accent); }
  .kbd-help { position: fixed; inset: 0; background: rgba(0,0,0,.55); display: flex;
              align-items: center; justify-content: center; z-index: 50; }
  .kbd-help[hidden] { display: none; }
  .kbd-help-panel { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
                     padding: 20px 24px; max-width: 420px; width: 90%; }
  .kbd-help-panel h2 { margin: 0 0 12px; font-size: 15px; }
  .kbd-help-panel table { margin: 0; }
  .kbd-help-panel kbd { font-family: var(--mono); background: var(--panel2); border: 1px solid var(--border);
                         border-radius: 4px; padding: 1px 6px; font-size: 11.5px; }
  .topnav { font-size: 12px; color: var(--muted); margin: 0 0 14px; }
  #banner { display: none; position: sticky; top: 0; background: rgba(224,175,104,.12);
            border: 1px solid var(--amber); color: var(--amber); border-radius: 6px;
            padding: 8px 12px; margin: 0 0 16px; font-size: 12.5px; }
  #banner.show { display: block; }
  #banner a { color: var(--amber); margin-left: 10px; }
</style>
</head>
<body>
<div class="wrap">
<div id="banner"><span id="banner-msg"></span><a href="#" id="banner-copy" hidden>copy unsaved state</a></div>
<div class="topnav"><a href="/" id="index-link">&larr; All reviews</a></div>
<h1><!--TITLE--></h1>
<div class="sub"><!--SUBTITLE--></div>
<div class="meta"><!--META--></div>
<div class="summary-grid"><!--SUMMARY--></div>
<div class="controls"><span class="progress" id="progress"></span><span class="save-status" id="save-status"></span><span class="kbd-hint" id="kbd-hint">? shortcuts</span></div>
<!--CONTENT-->
<div id="kbd-help" class="kbd-help" hidden>
<div class="kbd-help-panel">
<h2>Keyboard shortcuts</h2>
<table>
<tr><td><kbd>j</kbd> / <kbd>k</kbd> or <kbd>&uarr;</kbd> / <kbd>&darr;</kbd></td><td>move selection</td></tr>
<tr><td><kbd>space</kbd></td><td>toggle Post on the active finding</td></tr>
<tr><td><kbd>Enter</kbd></td><td>fold the active finding and move to next</td></tr>
<tr><td><kbd>z</kbd></td><td>fold the active finding in place</td></tr>
<tr><td><kbd>n</kbd></td><td>edit note on the active finding</td></tr>
<tr><td><kbd>Escape</kbd></td><td>exit the comment/note editor (or close this help)</td></tr>
<tr><td><kbd>?</kbd></td><td>toggle this help</td></tr>
</table>
</div>
</div>
</div>
<script>window.BAKED = <!--BAKED-->;</script>
<script>
(function () {
  var baked = window.BAKED;
  var state = (baked.state && baked.state.findings) ? baked.state : { findings: {} };
  var touched = {};
  var token = baked.token;
  var served = baked.served && location.protocol !== "file:";
  var dirty = 0;
  var saveTimer = null;
  var banner = document.getElementById("banner");
  var bannerMsg = document.getElementById("banner-msg");
  var bannerCopy = document.getElementById("banner-copy");
  var progress = document.getElementById("progress");
  var saveStatus = document.getElementById("save-status");
  var indexLink = document.getElementById("index-link");
  var kbdHint = document.getElementById("kbd-hint");
  var kbdHelp = document.getElementById("kbd-help");
  var cards = Array.prototype.slice.call(document.querySelectorAll(".finding[data-fid]"));

  var collapseKey = "review-branch:collapsed:" + baked.route;
  var activeKey = "review-branch:active:" + baked.route;

  function loadCollapsedFids() {
    try {
      return JSON.parse(sessionStorage.getItem(collapseKey) || "[]");
    } catch (e) {
      return [];
    }
  }

  function persistCollapsedFids() {
    var collapsed = cards.filter(function (card) { return card.classList.contains("collapsed"); })
                          .map(function (card) { return card.dataset.fid; });
    sessionStorage.setItem(collapseKey, JSON.stringify(collapsed));
  }

  function setFolded(card, folded) {
    card.classList.toggle("collapsed", folded);
    var btn = card.querySelector(".fold-toggle");
    if (btn) btn.setAttribute("aria-expanded", folded ? "false" : "true");
  }

  function toggleFold(card) {
    setFolded(card, !card.classList.contains("collapsed"));
    persistCollapsedFids();
  }

  function expandCard(card) {
    if (card.classList.contains("collapsed")) {
      setFolded(card, false);
      persistCollapsedFids();
    }
  }

  var collapsedFids = {};
  loadCollapsedFids().forEach(function (fid) { collapsedFids[fid] = true; });
  cards.forEach(function (card) {
    if (collapsedFids[card.dataset.fid]) setFolded(card, true);
    var btn = card.querySelector(".fold-toggle");
    if (btn) {
      btn.addEventListener("click", function () { toggleFold(card); });
    }
  });

  // Active-card highlight and keyboard nav (works read-only too; only editing is gated on `served`).
  var activeIndex = -1;

  function setActive(index, opts) {
    opts = opts || {};
    if (!cards.length) return;
    if (index < 0) index = 0;
    if (index >= cards.length) index = cards.length - 1;
    cards.forEach(function (card) { card.classList.remove("active"); });
    activeIndex = index;
    var card = cards[activeIndex];
    card.classList.add("active");
    sessionStorage.setItem(activeKey, card.dataset.fid);
    if (opts.scroll !== false) card.scrollIntoView({ block: "nearest" });
  }

  if (cards.length) {
    var initialIndex = 0;
    var storedActiveFid = sessionStorage.getItem(activeKey);
    if (storedActiveFid) {
      var foundIndex = cards.findIndex(function (c) { return c.dataset.fid === storedActiveFid; });
      if (foundIndex >= 0) initialIndex = foundIndex;
    }
    setActive(initialIndex, { scroll: false });
  }

  cards.forEach(function (card, i) {
    card.addEventListener("click", function (e) {
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
      setActive(i, { scroll: false });
    });
  });

  function isTyping(el) {
    if (!el) return false;
    var tag = el.tagName;
    return tag === "TEXTAREA" || tag === "INPUT" || el.isContentEditable;
  }

  function closeHelp() { if (kbdHelp) kbdHelp.hidden = true; }
  function toggleHelp() { if (kbdHelp) kbdHelp.hidden = !kbdHelp.hidden; }

  if (kbdHint) kbdHint.addEventListener("click", toggleHelp);
  if (kbdHelp) {
    kbdHelp.addEventListener("click", function (e) {
      if (e.target === kbdHelp) closeHelp();
    });
  }

  document.addEventListener("keydown", function (e) {
    var typing = isTyping(e.target);
    if (e.key === "Escape") {
      if (kbdHelp && !kbdHelp.hidden) { closeHelp(); return; }
      if (typing) {
        var editorCard = e.target.closest(".finding[data-fid]");
        e.target.blur();
        if (editorCard) {
          var editorIndex = cards.indexOf(editorCard);
          if (editorIndex >= 0) setActive(editorIndex, { scroll: false });
        }
      }
      return;
    }
    if (typing) return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === "?") {
      e.preventDefault();
      toggleHelp();
      return;
    }
    if (kbdHelp && !kbdHelp.hidden) return;
    if (e.key === "j" || e.key === "ArrowDown") {
      e.preventDefault();
      setActive(activeIndex + 1);
    } else if (e.key === "k" || e.key === "ArrowUp") {
      e.preventDefault();
      setActive(activeIndex - 1);
    } else if (e.key === " ") {
      e.preventDefault();
      var chkCard = cards[activeIndex];
      var chk = chkCard && chkCard.querySelector(".post-chk");
      if (chk && !chk.disabled) {
        chk.checked = !chk.checked;
        chk.dispatchEvent(new Event("change", { bubbles: true }));
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      var enterCard = cards[activeIndex];
      if (enterCard) toggleFold(enterCard);
      setActive(activeIndex + 1);
    } else if (e.key === "z") {
      e.preventDefault();
      var zCard = cards[activeIndex];
      if (zCard) toggleFold(zCard);
    } else if (e.key === "n") {
      e.preventDefault();
      var noteCard = cards[activeIndex];
      var noteArea = noteCard && noteCard.querySelector("textarea.note");
      if (noteArea) {
        expandCard(noteCard);
        noteArea.scrollIntoView({ block: "nearest" });
        noteArea.focus();
        var noteLen = noteArea.value.length;
        noteArea.setSelectionRange(noteLen, noteLen);
      }
    }
  });

  function setSaveStatus(s) {
    if (s === "saving") {
      saveStatus.textContent = "Saving...";
      saveStatus.className = "save-status saving";
    } else if (s === "error") {
      saveStatus.textContent = "Save failed - retrying";
      saveStatus.className = "save-status error";
    } else {
      saveStatus.textContent = "All changes saved";
      saveStatus.className = "save-status saved";
    }
  }

  function showBanner(msg, withCopy) {
    bannerMsg.textContent = msg;
    bannerCopy.hidden = !withCopy;
    banner.classList.add("show");
  }
  function hideBanner() { banner.classList.remove("show"); }

  function updateProgress() {
    var total = 0, marked = 0;
    cards.forEach(function (card) {
      var postChk = card.querySelector(".post-chk");
      if (!postChk) return;
      total += 1;
      if (postChk.checked) marked += 1;
    });
    progress.textContent = marked + " of " + total + " marked to post";
  }

  function collect() {
    cards.forEach(function (card) {
      var postChk = card.querySelector(".post-chk");
      if (!postChk) return;
      var fid = card.dataset.fid;
      var crev = parseInt(card.dataset.rev, 10) || 1;
      var entry = state.findings[fid] || (state.findings[fid] = {});
      entry.disposition = postChk.checked ? "post" : null;
      var comment = card.querySelector("textarea.comment");
      if (touched[fid + ":comment"]) {
        if (comment.value !== comment.defaultValue) {
          entry.edited_comment = comment.value;
          entry.edited_comment_rev = crev;
        } else {
          delete entry.edited_comment;
          delete entry.edited_comment_rev;
        }
      }
      var note = card.querySelector("textarea.note");
      if (touched[fid + ":note"]) {
        if (note.value) {
          entry.note = note.value;
          entry.note_rev = crev;
        } else {
          delete entry.note;
          delete entry.note_rev;
        }
      }
    });
    return state;
  }

  function save() {
    saveTimer = null;
    setSaveStatus("saving");
    fetch("api/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collect())
    }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (resp) {
      dirty = 0;
      token = resp.token;
      hideBanner();
      setSaveStatus("saved");
    }).catch(function () {
      setSaveStatus("error");
      showBanner("save failed (server error or unreachable) - " + dirty + " unsaved change(s) held in this tab. check daemon.log or restart with: review-branch open <review-dir>", true);
      saveTimer = setTimeout(save, 5000);
    });
  }

  function schedule() {
    dirty += 1;
    setSaveStatus("saving");
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 2000);
    updateProgress();
  }

  updateProgress();
  setSaveStatus("saved");

  if (!served) {
    document.querySelectorAll("textarea, input").forEach(function (el) { el.disabled = true; });
    showBanner("read-only snapshot - run: review-branch open <review-dir> to edit", false);
    saveStatus.textContent = "Read-only snapshot";
    saveStatus.className = "save-status saved";
    if (indexLink) indexLink.hidden = true;
    return;
  }

  cards.forEach(function (card) {
    var fid = card.dataset.fid;
    card.querySelectorAll(".post-chk").forEach(function (el) { el.addEventListener("change", schedule); });
    var view = card.querySelector(".comment-view");
    var commentArea = card.querySelector("textarea.comment");
    if (view && commentArea) {
      view.addEventListener("focus", function () {
        view.hidden = true;
        commentArea.hidden = false;
        commentArea.focus();
        var len = commentArea.value.length;
        commentArea.setSelectionRange(len, len);
      });
      commentArea.addEventListener("blur", function () {
        commentArea.hidden = true;
        view.hidden = false;
        if (commentArea.value !== commentArea.defaultValue) {
          touched[fid + ":comment"] = true;
          schedule();
          var raw = commentArea.value;
          if (raw) {
            view.textContent = raw;
          } else {
            view.innerHTML = '<em class="placeholder">No draft. Click to add one.</em>';
          }
          fetch("api/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ markdown: raw })
          }).then(function (r) {
            if (!r.ok) throw new Error(r.status);
            return r.json();
          }).then(function (resp) {
            if (raw) view.innerHTML = resp.html;
          }).catch(function () {
            // preview endpoint unreachable - the raw fallback set above stays in place
          });
        }
      });
    }
    card.querySelectorAll("textarea").forEach(function (el) {
      el.addEventListener("input", function () {
        if (el.classList.contains("comment")) touched[fid + ":comment"] = true;
        if (el.classList.contains("note")) touched[fid + ":note"] = true;
        schedule();
      });
    });
  });

  setInterval(function () {
    fetch("api/version").then(function (r) { return r.json(); }).then(function (resp) {
      if (resp.token !== token && !dirty && !saveTimer) location.reload();
    }).catch(function () {});
  }, 2000);

  window.addEventListener("beforeunload", function (e) {
    if (dirty || saveTimer) { e.preventDefault(); e.returnValue = ""; }
  });

  bannerCopy.addEventListener("click", function (e) {
    e.preventDefault();
    navigator.clipboard.writeText(JSON.stringify(collect()));
  });
})();
</script>
</body>
</html>
"""


def compose(review: dict, state: dict, assets_html: str, route: str, token: str, served: bool) -> str:
    meta = review.get("review", {})
    findings = merged_findings(review, state)
    minor = review.get("minor", [])
    content = [assets_html]
    if review.get("overall", {}).get("body"):
        content.append("<h2>Overall</h2>\n" + md_html(review["overall"]["body"]))
    content.append("<h2>Findings</h2>")
    content += [finding_card(f, meta) for f in findings]
    content.append(
        table_html(
            "Hexagonal architecture compliance",
            ["Boundary", "Change", "Status"],
            [[esc(r.get("boundary", "")), esc(r.get("change", "")), esc(r.get("status", ""))] for r in review.get("hex", [])],
        )
    )
    content.append(
        table_html(
            "What the tests do and don't cover",
            ["Surface", "Covered", "Gap"],
            [[esc(r.get("surface", "")), _dash(r.get("covered")), _dash(r.get("gap"))] for r in review.get("coverage", [])],
        )
    )
    content.append(
        table_html(
            "Files touched",
            ["File", "+/-", "Notes"],
            [[f"<code>{esc(r.get('path', ''))}</code>", esc(r.get("delta", "")), esc(r.get("notes", ""))] for r in review.get("files_touched", [])],
        )
    )
    content.append(minor_html(minor))
    baked = json.dumps({"served": served, "route": route, "token": token, "state": state}).replace("</", "<\\/")
    subtitle = "Collaborative review tracker. Toggle findings to post, edit drafts, leave notes for Claude."
    return (
        TEMPLATE
        .replace("<!--TITLE-->", esc(meta.get("title", "review")))
        .replace("<!--SUBTITLE-->", subtitle)
        .replace("<!--META-->", meta_row(meta))
        .replace("<!--SUMMARY-->", summary_cards(findings, len(minor)))
        .replace("<!--CONTENT-->", "\n".join(part for part in content if part))
        .replace("<!--BAKED-->", baked)
    )


def render_html(round_dir: Path, served: bool) -> str:
    review = load_review(round_dir)
    state = load_state(round_dir)
    assets = assets_html(round_dir, review)
    route = route_for(round_dir)
    token = version_token(round_dir)
    return compose(review, state, assets, route, token, served)


def cmd_render(round_dir: Path) -> Path:
    out = round_dir / "review.html"
    out.write_text(render_html(round_dir, served=False))
    rid, slug, rnd = route_for(round_dir).split("/")
    data_commit(f"{rid} {slug} {rnd}: render")
    return out


INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>review-branch</title>
<style>
  body { margin: 0; background: #0f1115; color: #e6e8ee;
         font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 32px 24px; }
  a { color: #7aa2f7; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; border-bottom: 1px solid #2a3042; padding: 8px 10px; font-size: 13px; }
  th { color: #9aa3b2; font-weight: 500; }
</style>
</head>
<body><div class="wrap">
<h1>Reviews</h1>
<table><tr><th>Review</th><th>Repo</th><th>Findings</th><th>Progress</th></tr>
<!--ROWS-->
</table>
</div></body></html>
"""


_STATE_WRITE_LOCK = threading.Lock()


def index_html(root: Path) -> str:
    rows = []

    def activity(p: Path) -> float:
        state = p.parent / "state.json"
        times = [p.stat().st_mtime]
        if state.exists():
            times.append(state.stat().st_mtime)
        return max(times)

    tomls = sorted(root.glob("*/*/round-*/review.toml"), key=activity, reverse=True)
    for toml_path in tomls:
        d = toml_path.parent
        try:
            review = tomllib.loads(toml_path.read_text())
            state = load_state(d)
        except (tomllib.TOMLDecodeError, OSError, json.JSONDecodeError):
            continue
        findings = merged_findings(review, state)
        counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "info")
            counts[sev] = counts.get(sev, 0) + 1
        sev_text = " ".join(f"{k}:{counts[k]}" for k in ("high", "med", "low", "info") if k in counts)
        decided = sum(1 for f in findings if f["disposition"])
        posted = sum(1 for f in findings if f["posted"])
        route = "/".join(d.relative_to(root).parts)
        title = review.get("review", {}).get("title", route)
        rows.append(
            f'<tr><td><a href="/{route}/">{esc(title)}</a></td><td>{esc(d.relative_to(root).parts[0])}</td>'
            f"<td>{esc(sev_text)}</td><td>{decided} decided, {posted} posted</td></tr>"
        )
    return INDEX_TEMPLATE.replace("<!--ROWS-->", "\n".join(rows) or '<tr><td colspan="4">no reviews yet</td></tr>')


class ReviewHandler(BaseHTTPRequestHandler):
    root: Path

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8"):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj), "application/json")

    def _round_dir(self, parts: list[str]) -> Path | None:
        if len(parts) != 3:
            return None
        d = (self.root / parts[0] / parts[1] / parts[2]).resolve()
        if not d.is_relative_to(self.root.resolve()):
            return None
        return d if (d / "review.toml").exists() else None

    def do_GET(self):
        try:
            self._handle_get()
        except (Exception, SystemExit) as e:
            try:
                self._json(500, {"error": str(e)})
            except Exception:
                pass

    def _handle_get(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self._json(200, {"app": APP_NAME, "version": __version__, "data_root": str(self.root)})
        if path == "/":
            return self._send(200, index_html(self.root))
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[-2] == "api":
            d = self._round_dir(parts[:-2])
            if d is None:
                return self._json(404, {"error": "unknown review route"})
            if parts[-1] == "state":
                return self._json(200, load_state(d))
            if parts[-1] == "version":
                return self._json(200, {"token": version_token(d)})
            return self._json(404, {"error": "unknown api endpoint"})
        d = self._round_dir(parts)
        if d is None:
            return self._json(404, {"error": "unknown review route"})
        if not path.endswith("/"):
            self.send_response(301)
            self.send_header("Location", path + "/")
            self.end_headers()
            return
        return self._send(200, render_html(d, served=True))

    def do_POST(self):
        try:
            self._handle_post()
        except (Exception, SystemExit) as e:
            try:
                self._json(500, {"error": str(e)})
            except Exception:
                pass

    def _handle_post(self):
        path = urlparse(self.path).path
        host = self.headers.get("Host")
        if host and host.split(":")[0] not in ("127.0.0.1", "localhost"):
            return self._json(403, {"error": "bad host"})
        origin = self.headers.get("Origin")
        if origin:
            port = current_port()
            allowed_origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
            if origin not in allowed_origins:
                return self._json(403, {"error": "bad origin"})
        if path == "/api/shutdown":
            threading.Thread(target=self.server.shutdown).start()
            return self._json(200, {"ok": True})
        parts = [p for p in path.split("/") if p]
        if len(parts) != 5 or parts[3] != "api" or parts[4] not in ("state", "preview"):
            return self._json(404, {"error": "unknown endpoint"})
        d = self._round_dir(parts[:3])
        if d is None:
            return self._json(404, {"error": "unknown review route"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})
        if parts[4] == "preview":
            if not isinstance(payload, dict) or not isinstance(payload.get("markdown"), str):
                return self._json(400, {"error": 'expected {"markdown": "..."}'})
            return self._json(200, {"html": md_html(payload["markdown"])})
        if not isinstance(payload, dict) or not isinstance(payload.get("findings"), dict):
            return self._json(400, {"error": 'expected {"findings": {...}}'})
        if not all(isinstance(v, dict) for v in payload["findings"].values()):
            return self._json(400, {"error": "each finding entry must be an object"})
        try:
            with _STATE_WRITE_LOCK:
                payload["updated_at"] = datetime.now(UTC).isoformat()
                (d / "state.json").write_text(json.dumps(payload, indent=2) + "\n")
                (d / "review.html").write_text(render_html(d, served=False))
                data_commit(f"{parts[0]} {parts[1]} {parts[2]}: state update")
                token = version_token(d)
            return self._json(200, {"ok": True, "token": token})
        except (Exception, SystemExit) as e:
            return self._json(500, {"error": str(e)})


def make_server(port: int, root: Path | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (ReviewHandler,), {"root": root or data_root()})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def current_port() -> int:
    return int(os.environ.get("REVIEW_BRANCH_PORT", DEFAULT_PORT))


def pidfile() -> Path:
    return state_root() / "daemon.pid"


def health_check(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _vtuple(version: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", version)) or (0,)


def daemon_action(health: dict | None) -> str:
    if health is None:
        return "start"
    if health.get("app") != APP_NAME:
        return "squatter"
    if _vtuple(str(health.get("version", "0"))) < _vtuple(__version__):
        return "restart"
    return "use"


def spawn_daemon(port: int) -> None:
    state_root().mkdir(parents=True, exist_ok=True)
    log = (state_root() / "daemon.log").open("a")
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "serve"],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "REVIEW_BRANCH_PORT": str(port)},
    )


def _wait(predicate, tries: int = 50, delay: float = 0.1) -> bool:
    for _ in range(tries):
        if predicate():
            return True
        time.sleep(delay)
    return False


def cmd_open(round_dir: Path) -> str:
    if not (round_dir / "review.toml").exists():
        raise SystemExit(f"{round_dir}: no review.toml")
    route = route_for(round_dir)
    port = current_port()
    action = daemon_action(health_check(port))
    if action == "squatter":
        raise SystemExit(f"port {port} is in use by another application; set REVIEW_BRANCH_PORT")
    if action == "restart":
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", method="POST", data=b"")
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass
        _wait(lambda: health_check(port) is None)
        action = "start"
    if action == "start":
        spawn_daemon(port)
        if not _wait(lambda: health_check(port) is not None):
            raise SystemExit(f"daemon failed to start; see {state_root() / 'daemon.log'}")
    return f"http://127.0.0.1:{port}/{route}/"


def cmd_serve() -> int:
    port = current_port()
    server = make_server(port)
    state_root().mkdir(parents=True, exist_ok=True)
    pidfile().write_text(str(os.getpid()))
    print(
        f"review-branch serving all reviews at http://127.0.0.1:{port}/  (Ctrl-C to stop)",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    finally:
        pidfile().unlink(missing_ok=True)
    return 0


def cmd_stop() -> int:
    pf = pidfile()
    if not pf.exists():
        print("daemon not running (no pidfile)")
        return 0
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        print("removed stale pidfile (not a valid pid)")
        pf.unlink(missing_ok=True)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"stopped daemon (pid {pid})")
    except (ProcessLookupError, PermissionError):
        print(f"removed stale pidfile (pid {pid} not running)")
    pf.unlink(missing_ok=True)
    return 0


INSTALL_MAP = {
    "review_tool.py": "review-branch",
    "glab_comment.py": "glab-comment",
    "gh_comment.py": "gh-comment",
}


def bin_dir() -> Path:
    return Path(os.environ.get("REVIEW_BRANCH_BIN", "~/.local/bin")).expanduser()


def install_scripts(src_dir: Path, dest_dir: Path) -> list[str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    installed = []
    for src_name, dest_name in INSTALL_MAP.items():
        src = src_dir / src_name
        if not src.exists():
            continue
        dest = dest_dir / dest_name
        shutil.copy2(src, dest)
        dest.chmod(0o755)
        installed.append(dest_name)
    return installed


def cmd_install() -> int:
    dest = bin_dir()
    installed = install_scripts(Path(__file__).resolve().parent, dest)
    for name in installed:
        print(f"installed {dest / name}")
    for name in sorted(set(INSTALL_MAP.values()) - set(installed)):
        print(f"skipped {name} (source not present)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review-branch", description="review-branch tool")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    p_init = sub.add_parser("init", help="create the next round directory for a review")
    p_init.add_argument("--slug", required=True)
    for name in ("render", "open", "status", "manifest"):
        p = sub.add_parser(name)
        p.add_argument("review_dir")
    p_manifest = sub._name_parser_map["manifest"]
    p_manifest.add_argument("--exclude", default="")
    sub.add_parser("install", help="copy scripts to the bin dir")
    sub.add_parser("serve", help="run the server in the foreground")
    sub.add_parser("stop", help="stop the daemon via pidfile")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2
    if args.command == "init":
        print(cmd_init(args.slug, Path.cwd()))
        return 0
    if args.command == "render":
        print(cmd_render(Path(args.review_dir)))
        return 0
    if args.command == "status":
        print(json.dumps(cmd_status(Path(args.review_dir)), indent=2))
        return 0
    if args.command == "manifest":
        exclude = {x for x in args.exclude.split(",") if x}
        print(json.dumps(cmd_manifest(Path(args.review_dir), exclude), indent=2))
        return 0
    if args.command == "open":
        print(cmd_open(Path(args.review_dir)))
        return 0
    if args.command == "install":
        return cmd_install()
    if args.command == "serve":
        return cmd_serve()
    if args.command == "stop":
        return cmd_stop()
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

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
import subprocess
import sys
import threading
import tomllib
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from markdown_it import MarkdownIt

__version__ = "0.2.0"
APP_NAME = "review-branch"
DEFAULT_PORT = 43117

SUBCOMMANDS = ("init", "render", "open", "status", "manifest", "install", "daemon", "stop")


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


_MD = MarkdownIt("commonmark").enable("table")


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def md_html(text: str) -> str:
    return _MD.render(text or "")


def diff_link(meta: dict, path: str, line: int | None) -> str | None:
    url = meta.get("url")
    if not url:
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
            f'<span><strong>{label}:</strong> <a href="{esc(meta["url"])}">{mark}{meta["number"]}</a></span>'
        )
    if meta.get("source_branch"):
        arrow = f'{esc(meta["source_branch"])} -&gt; {esc(meta.get("target_branch", ""))}'
        spans.append(f"<span><strong>Branch:</strong> {arrow}</span>")
    for key, name in (("commits", "Commits"), ("files", "Files"), ("spec", "Spec")):
        if meta.get(key):
            spans.append(f"<span><strong>{name}:</strong> {esc(meta[key])}</span>")
    return "\n".join(spans)


def summary_cards(findings: list[dict]) -> str:
    counts = {"high": 0, "med": 0, "low": 0, "info": 0}
    for f in findings:
        counts[f.get("severity", "info")] += 1
    cards = []
    for sev, name in (("high", "High"), ("med", "Medium"), ("low", "Low / nits"), ("info", "Out-of-scope flags")):
        if counts[sev] or sev in ("high", "med"):
            cards.append(
                f'<div class="card"><div class="num {sev}">{counts[sev]}</div><div class="label">{name}</div></div>'
            )
    return "\n".join(cards)


def assets_html(round_dir: Path, review: dict) -> str:
    parts = []
    for a in review.get("assets", []):
        p = round_dir / a["path"]
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


def finding_card(f: dict, meta: dict) -> str:
    sev = f.get("severity", "info")
    fid = f["id"]
    _, line = parse_anchor(f)
    fileref = f'{f["file"]}:{f["lines"]}' if f.get("lines") else f["file"]
    link = diff_link(meta, f["file"], line)
    file_html = f'<a href="{esc(link)}">{esc(fileref)}</a>' if link else esc(fileref)
    head = [
        f'<span class="num">{esc(fid)}</span>',
        f'<span class="title">{esc(f.get("title", ""))}</span>',
        f'<span class="badge {sev}">{sev}</span>',
    ]
    head += [f'<span class="tag">{esc(lens)}</span>' for lens in f.get("lenses", [])]
    if f["posted"]:
        head.append(f'<a class="badge posted" href="{esc(f.get("posted_url", ""))}">posted</a>')
    parts = [
        f'<div class="finding {sev}" data-fid="{esc(fid)}" data-rev="{f.get("comment_rev", 1)}">',
        f'<div class="head">{" ".join(head)}</div>',
        f'<div class="file">{file_html}</div>',
        md_html(f.get("body", "")),
    ]
    if f.get("snippet"):
        parts.append(f"<pre><code>{esc(f['snippet'])}</code></pre>")
    if f.get("fix"):
        parts.append(f"<p><strong>Suggested fix:</strong> {esc(f['fix'])}</p>")
    if f["posted"]:
        parts.append(f"<pre><code>{esc(f.get('posted_body', ''))}</code></pre>")
    elif f.get("commentable", True):
        area = ['<div class="comment-area">']
        if f["note_stale"]:
            area.append(f'<div class="applied">applied: {esc(f["note"])}</div>')
        area.append('<label class="small">Comment draft</label>')
        area.append(f'<textarea class="comment">{esc(f["postable_body"] or "")}</textarea>')
        area.append('<label class="small">Note to Claude</label>')
        note_now = "" if f["note_stale"] else (f.get("note") or "")
        area.append(
            f'<textarea class="note" placeholder="tell Claude how to adjust this">{esc(note_now)}</textarea>'
        )
        dispo = f["disposition"] or ""
        area.append('<div class="dispo">')
        for value, name in (("post", "Post"), ("skip", "Skip"), ("", "Undecided")):
            checked = " checked" if dispo == value else ""
            area.append(
                f'<label><input type="radio" name="dispo-{esc(fid)}" value="{value}"{checked}> {name}</label>'
            )
        area.append("</div></div>")
        parts.append("\n".join(area))
    parts.append("</div>")
    return "\n".join(parts)


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
  textarea { width: 100%; min-height: 72px; margin-top: 4px; background: var(--panel2);
             color: var(--text); border: 1px solid var(--border); border-radius: 6px;
             padding: 8px; font: 12.5px/1.5 var(--mono); resize: vertical; }
  textarea.note { min-height: 40px; font-family: inherit; }
  textarea:disabled, input:disabled { opacity: .5; }
  .applied { color: var(--muted); font-size: 12px; font-style: italic; margin-top: 8px; }
  .dispo { display: flex; gap: 16px; margin-top: 8px; color: var(--muted); font-size: 13px; }
  .dispo label { cursor: pointer; }
  .controls { display: flex; gap: 10px; align-items: center; margin: 8px 0 18px;
              font-size: 12px; color: var(--muted); }
  .progress { font-family: var(--mono); }
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
<h1><!--TITLE--></h1>
<div class="sub"><!--SUBTITLE--></div>
<div class="meta"><!--META--></div>
<div class="summary-grid"><!--SUMMARY--></div>
<div class="controls"><span class="progress" id="progress"></span></div>
<!--CONTENT-->
</div>
<script>window.BAKED = <!--BAKED-->;</script>
<script>
(function () {
  var baked = window.BAKED;
  var state = (baked.state && baked.state.findings) ? baked.state : { findings: {} };
  var token = baked.token;
  var served = baked.served && location.protocol !== "file:";
  var dirty = 0;
  var saveTimer = null;
  var banner = document.getElementById("banner");
  var bannerMsg = document.getElementById("banner-msg");
  var bannerCopy = document.getElementById("banner-copy");
  var progress = document.getElementById("progress");
  var cards = Array.prototype.slice.call(document.querySelectorAll(".finding[data-fid]"));

  function showBanner(msg, withCopy) {
    bannerMsg.textContent = msg;
    bannerCopy.hidden = !withCopy;
    banner.classList.add("show");
  }
  function hideBanner() { banner.classList.remove("show"); }

  function updateProgress() {
    var counts = { post: 0, skip: 0, undecided: 0 };
    cards.forEach(function (card) {
      if (!card.querySelector(".dispo")) return;
      var checked = card.querySelector("input[type=radio]:checked");
      counts[checked && checked.value ? checked.value : "undecided"] += 1;
    });
    progress.textContent = counts.post + " post, " + counts.skip + " skip, " + counts.undecided + " undecided";
  }

  function collect() {
    cards.forEach(function (card) {
      if (!card.querySelector(".dispo")) return;
      var fid = card.dataset.fid;
      var crev = parseInt(card.dataset.rev, 10) || 1;
      var entry = state.findings[fid] || (state.findings[fid] = {});
      var checked = card.querySelector("input[type=radio]:checked");
      entry.disposition = checked && checked.value ? checked.value : null;
      var comment = card.querySelector("textarea.comment");
      if (comment.value !== comment.defaultValue) {
        entry.edited_comment = comment.value;
        entry.edited_comment_rev = crev;
      }
      var note = card.querySelector("textarea.note");
      if (note.value && note.value !== note.defaultValue) {
        entry.note = note.value;
        entry.note_rev = crev;
      } else if (!note.value && note.defaultValue) {
        delete entry.note;
        delete entry.note_rev;
      }
    });
    return state;
  }

  function save() {
    saveTimer = null;
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
    }).catch(function () {
      showBanner("server unreachable - " + dirty + " unsaved change(s) held in this tab. restart with: review-branch open <review-dir>", true);
      saveTimer = setTimeout(save, 5000);
    });
  }

  function schedule() {
    dirty += 1;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 2000);
    updateProgress();
  }

  updateProgress();

  if (!served) {
    document.querySelectorAll("textarea, input").forEach(function (el) { el.disabled = true; });
    showBanner("read-only snapshot - run: review-branch open <review-dir> to edit", false);
    return;
  }

  cards.forEach(function (card) {
    card.querySelectorAll("input[type=radio]").forEach(function (el) { el.addEventListener("change", schedule); });
    card.querySelectorAll("textarea").forEach(function (el) { el.addEventListener("input", schedule); });
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


def render_html(round_dir: Path, served: bool) -> str:
    review = load_review(round_dir)
    state = load_state(round_dir)
    meta = review.get("review", {})
    findings = merged_findings(review, state)
    content = [assets_html(round_dir, review)]
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
    baked = json.dumps(
        {"served": served, "route": route_for(round_dir), "token": version_token(round_dir), "state": state}
    ).replace("</", "<\\/")
    subtitle = "Collaborative review tracker. Mark dispositions, edit drafts, leave notes for Claude."
    return (
        TEMPLATE
        .replace("<!--TITLE-->", esc(meta.get("title", "review")))
        .replace("<!--SUBTITLE-->", subtitle)
        .replace("<!--META-->", meta_row(meta))
        .replace("<!--SUMMARY-->", summary_cards(findings))
        .replace("<!--CONTENT-->", "\n".join(part for part in content if part))
        .replace("<!--BAKED-->", baked)
    )


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
    tomls = sorted(
        root.glob("*/*/round-*/review.toml"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for toml_path in tomls:
        d = toml_path.parent
        try:
            review = tomllib.loads(toml_path.read_text())
        except tomllib.TOMLDecodeError:
            continue
        findings = merged_findings(review, load_state(d))
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
        path = urlparse(self.path).path
        if path == "/api/shutdown":
            threading.Thread(target=self.server.shutdown).start()
            return self._json(200, {"ok": True})
        parts = [p for p in path.split("/") if p]
        if len(parts) != 5 or parts[3:] != ["api", "state"]:
            return self._json(404, {"error": "unknown endpoint"})
        d = self._round_dir(parts[:3])
        if d is None:
            return self._json(404, {"error": "unknown review route"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})
        if not isinstance(payload, dict) or not isinstance(payload.get("findings"), dict):
            return self._json(400, {"error": 'expected {"findings": {...}}'})
        try:
            with _STATE_WRITE_LOCK:
                payload["updated_at"] = datetime.now(UTC).isoformat()
                (d / "state.json").write_text(json.dumps(payload, indent=2) + "\n")
                (d / "review.html").write_text(render_html(d, served=False))
                data_commit(f"{parts[0]} {parts[1]} {parts[2]}: state update")
                token = version_token(d)
            return self._json(200, {"ok": True, "token": token})
        except Exception as e:
            return self._json(500, {"error": str(e)})


def make_server(port: int, root: Path | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (ReviewHandler,), {"root": root or data_root()})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


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
    sub.add_parser("daemon", help="run the server in the foreground")
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
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

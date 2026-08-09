# ABOUTME: pytest-playwright harness for review-branch UI specs
# ABOUTME: isolates REVIEW_BRANCH_HOME per test, runs a real serve daemon on an ephemeral port

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "review-branch" / "scripts"),
)

import review_tool  # noqa: E402

REVIEW_TOML = """
[review]
title = "UI test review"
vcs = "glab"
number = 9
url = "https://gitlab.example.com/g/p/-/merge_requests/9"

[[findings]]
id = "f1"
severity = "high"
title = "Commentable finding"
file = "a.py"
lines = "1"
body = "Body one."
comment = "Draft with **markdown**."

[[findings]]
id = "f2"
severity = "med"
title = "Posted finding"
file = "b.py"
lines = "5"
body = "Body two."
comment = "Was posted."
posted_url = "https://gitlab.example.com/note/1"
posted_at = "2026-08-08T00:00:00Z"
posted_body = "Final posted text."

[[findings]]
id = "f3"
severity = "low"
title = "Non-commentable finding"
file = "c.py"
body = "Context only."
commentable = false
"""


@pytest.fixture(scope="session", autouse=True)
def _require_browser():
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
    except Exception as e:
        pytest.skip(f"chromium browser not available: {e}", allow_module_level=True)


@pytest.fixture
def review_env(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_BRANCH_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("REVIEW_BRANCH_BIN", str(tmp_path / "bin"))
    monkeypatch.delenv("REVIEW_BRANCH_PORT", raising=False)
    d = review_tool.data_root() / "proj-abcd" / "mr-9" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(REVIEW_TOML)
    return d


@pytest.fixture
def live_server(review_env, monkeypatch):
    srv = review_tool.make_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    port = srv.server_address[1]
    # The browser's fetch() sends an Origin header even for same-origin POSTs;
    # REVIEW_BRANCH_PORT must agree with the bound port for current_port() to
    # accept it (same coupling test_daemon.py's origin tests exercise).
    monkeypatch.setenv("REVIEW_BRANCH_PORT", str(port))
    url = f"http://127.0.0.1:{port}/proj-abcd/mr-9/round-1/"
    yield srv, url, review_env
    try:
        srv.shutdown()
        srv.server_close()
    except Exception:
        pass


@pytest.fixture
def review_page(live_server, page):
    srv, url, round_dir = live_server
    page.goto(url)
    return page

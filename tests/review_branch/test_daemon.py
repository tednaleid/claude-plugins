# ABOUTME: daemon smoke tests over a real ThreadingHTTPServer on an ephemeral port
# ABOUTME: covers health, index, page serving, state round-trip, version token, 404s

import concurrent.futures
import http.client
import json
import os
import threading

import pytest

import review_tool

REVIEW_TOML = """
[review]
title = "MR 7 review"
vcs = "glab"
number = 7
url = "https://gitlab.example.com/g/p/-/merge_requests/7"

[[findings]]
id = "f1"
severity = "med"
title = "T"
file = "a.py"
lines = "3"
body = "x"
comment = "Draft."
"""


@pytest.fixture
def served(env):
    d = review_tool.data_root() / "proj-abcd" / "mr-7" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(REVIEW_TOML)
    srv = review_tool.make_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv.server_address[1], d
    srv.shutdown()


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/json"} if body else {}
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    return resp.status, data


def test_health(served):
    port, _ = served
    status, data = request(port, "GET", "/api/health")
    assert status == 200
    payload = json.loads(data)
    assert payload["app"] == "review-branch"
    assert payload["version"] == review_tool.__version__


def test_index_lists_review(served):
    port, _ = served
    status, data = request(port, "GET", "/")
    assert status == 200
    assert "MR 7 review" in data
    assert "/proj-abcd/mr-7/round-1/" in data


def test_review_page_served_true(served):
    port, _ = served
    status, data = request(port, "GET", "/proj-abcd/mr-7/round-1/")
    assert status == 200
    assert '"served": true' in data


def test_no_trailing_slash_redirects(served):
    port, _ = served
    status, _ = request(port, "GET", "/proj-abcd/mr-7/round-1")
    assert status == 301


def test_unknown_route_404(served):
    port, _ = served
    status, _ = request(port, "GET", "/nope/mr-1/round-1/")
    assert status == 404


def test_state_roundtrip_writes_commits_and_tokens(served):
    port, d = served
    _, before = request(port, "GET", "/proj-abcd/mr-7/round-1/api/version")
    body = json.dumps({"findings": {"f1": {"disposition": "post"}}})
    status, data = request(port, "POST", "/proj-abcd/mr-7/round-1/api/state", body)
    assert status == 200
    resp = json.loads(data)
    assert resp["ok"] is True
    saved = json.loads((d / "state.json").read_text())
    assert saved["findings"]["f1"]["disposition"] == "post"
    assert "updated_at" in saved
    assert (d / "review.html").exists()
    log = review_tool.git(review_tool.data_root(), "log", "--oneline")
    assert "proj-abcd mr-7 round-1: state update" in log
    _, after = request(port, "GET", "/proj-abcd/mr-7/round-1/api/version")
    assert json.loads(after)["token"] != json.loads(before)["token"]


def test_bad_json_400(served):
    port, _ = served
    status, _ = request(port, "POST", "/proj-abcd/mr-7/round-1/api/state", "{nope")
    assert status == 400


def test_non_dict_finding_entry_400_and_does_not_write(served):
    port, d = served
    state_path = d / "state.json"
    before = state_path.read_text() if state_path.exists() else None
    body = json.dumps({"findings": {"f1": "x"}})
    status, data = request(port, "POST", "/proj-abcd/mr-7/round-1/api/state", body)
    assert status == 400
    after = state_path.read_text() if state_path.exists() else None
    assert after == before


def test_bad_origin_403_and_does_not_write(served):
    port, d = served
    state_path = d / "state.json"
    before = state_path.read_text() if state_path.exists() else None
    body = json.dumps({"findings": {"f1": {"disposition": "post"}}})
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(
        "POST",
        "/proj-abcd/mr-7/round-1/api/state",
        body=body,
        headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
    )
    resp = conn.getresponse()
    status = resp.status
    resp.read()
    conn.close()
    assert status == 403
    after = state_path.read_text() if state_path.exists() else None
    assert after == before


def test_matching_origin_post_succeeds(env, monkeypatch):
    # Uses its own server (rather than the shared `served` fixture) because it
    # needs REVIEW_BRANCH_PORT to agree with the actual bound port so that
    # current_port() matches the Origin the client sends - the same
    # coupling that makes production's REVIEW_BRANCH_PORT-threaded daemon
    # (spawn_daemon -> cmd_daemon) accept its own page's same-origin POSTs.
    d = review_tool.data_root() / "proj-abcd" / "mr-7" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(REVIEW_TOML)
    srv = review_tool.make_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        port = srv.server_address[1]
        monkeypatch.setenv("REVIEW_BRANCH_PORT", str(port))
        body = json.dumps({"findings": {"f1": {"disposition": "post"}}})
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST",
            "/proj-abcd/mr-7/round-1/api/state",
            body=body,
            headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"},
        )
        resp = conn.getresponse()
        status = resp.status
        resp.read()
        conn.close()
        assert status == 200
        saved = json.loads((d / "state.json").read_text())
        assert saved["findings"]["f1"]["disposition"] == "post"
    finally:
        srv.shutdown()


def test_concurrent_posts_all_succeed(served):
    port, d = served

    def post(i):
        body = json.dumps(
            {"findings": {"f1": {"disposition": "post", "note": f"n{i}", "note_rev": 1}}}
        )
        return request(port, "POST", "/proj-abcd/mr-7/round-1/api/state", body)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(post, range(8)))

    assert all(status == 200 for status, _ in results)
    saved = json.loads((d / "state.json").read_text())
    assert saved["findings"]["f1"]["note"].startswith("n")


def test_malformed_toml_returns_500_not_dropped(served):
    port, d = served
    (d / "review.toml").write_text("[review\n")
    status, data = request(port, "GET", "/proj-abcd/mr-7/round-1/")
    assert status == 500
    assert "error" in json.loads(data)


def test_index_skips_review_that_vanishes_mid_scan(env):
    root = review_tool.data_root()
    d = root / "proj-abcd" / "mr-3" / "round-1"
    d.mkdir(parents=True)
    # matches the review.toml glob pattern by name but isn't a readable file,
    # simulating a round directory that vanished/changed shape mid-scan
    (d / "review.toml").mkdir()
    page = review_tool.index_html(root)
    assert "no reviews yet" in page


def test_index_skips_review_with_corrupt_state_json(env):
    root = review_tool.data_root()
    good = root / "proj-abcd" / "mr-1" / "round-1"
    bad = root / "proj-abcd" / "mr-2" / "round-1"
    for d, title in ((good, "Good Review"), (bad, "Bad Review")):
        d.mkdir(parents=True)
        (d / "review.toml").write_text(f'[review]\ntitle = "{title}"\n')
    (bad / "state.json").write_text("{bad")
    page = review_tool.index_html(root)
    assert "Good Review" in page
    assert "Bad Review" not in page


def test_index_sorts_by_latest_activity(env):
    root = review_tool.data_root()
    a = root / "proj-abcd" / "mr-1" / "round-1"
    b = root / "proj-abcd" / "mr-2" / "round-1"
    for d, title in ((a, "Review A"), (b, "Review B")):
        d.mkdir(parents=True)
        (d / "review.toml").write_text(f'[review]\ntitle = "{title}"\n')
    os.utime(a / "review.toml", (1000, 1000))
    os.utime(b / "review.toml", (2000, 2000))
    page = review_tool.index_html(root)
    assert page.index("Review B") < page.index("Review A")
    (a / "state.json").write_text('{"findings": {}}')
    os.utime(a / "state.json", (3000, 3000))
    page = review_tool.index_html(root)
    assert page.index("Review A") < page.index("Review B")

# ABOUTME: daemon smoke tests over a real ThreadingHTTPServer on an ephemeral port
# ABOUTME: covers health, index, page serving, state round-trip, version token, 404s

import concurrent.futures
import http.client
import json
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

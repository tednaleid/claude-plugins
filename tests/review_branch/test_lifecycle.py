# ABOUTME: tests for daemon lifecycle: action decisions, open against a live server, stop
# ABOUTME: uses an in-thread server for open and a throwaway child process for stop

import socket
import subprocess
import sys
import threading
import urllib.request

import pytest

import review_tool

REVIEW_TOML = '[review]\ntitle = "t"\nvcs = "local"\n'


def test_daemon_action_decisions():
    assert review_tool.daemon_action(None) == "start"
    assert review_tool.daemon_action({"app": "something-else"}) == "squatter"
    assert review_tool.daemon_action({"app": "review-branch", "version": "0.0.1"}) == "restart"
    assert review_tool.daemon_action({"app": "review-branch", "version": review_tool.__version__}) == "use"
    assert review_tool.daemon_action({"app": "review-branch", "version": "99.0.0"}) == "use"


def test_open_uses_running_daemon(env, monkeypatch, capsys):
    d = review_tool.data_root() / "proj-abcd" / "mr-3" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(REVIEW_TOML)
    srv = review_tool.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    monkeypatch.setenv("REVIEW_BRANCH_PORT", str(port))
    try:
        assert review_tool.main(["url", str(d)]) == 0
        out = capsys.readouterr().out.strip()
        assert out == f"http://127.0.0.1:{port}/proj-abcd/mr-3/round-1/"
    finally:
        srv.shutdown()


def test_stop_kills_pidfile_process(env):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    review_tool.state_root().mkdir(parents=True, exist_ok=True)
    review_tool.pidfile().write_text(str(proc.pid))
    assert review_tool.cmd_stop() == 0
    assert proc.wait(timeout=10) != 0
    assert not review_tool.pidfile().exists()


def test_stop_tolerates_stale_pidfile(env):
    review_tool.state_root().mkdir(parents=True, exist_ok=True)
    review_tool.pidfile().write_text("999999")
    assert review_tool.cmd_stop() == 0
    assert not review_tool.pidfile().exists()


def test_stop_tolerates_garbage_pidfile(env):
    review_tool.state_root().mkdir(parents=True, exist_ok=True)
    review_tool.pidfile().write_text("garbage")
    assert review_tool.cmd_stop() == 0
    assert not review_tool.pidfile().exists()


def test_serve_is_registered_subcommand_not_daemon(capsys):
    with pytest.raises(SystemExit) as exc:
        review_tool.main(["bogus"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    # The choices braces in the usage line, not the "invalid choice" sentence,
    # which quotes each choice differently across Python versions.
    choices = err.split("{", 1)[1].split("}", 1)[0].split(",")
    assert "serve" in choices
    assert "daemon" not in choices


def test_spawn_daemon_invokes_serve(env, monkeypatch):
    captured = {}

    class FakeProc:
        pid = 12345

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    review_tool.spawn_daemon(43117)
    assert captured["argv"][-1] == "serve"
    assert "daemon" not in captured["argv"]


def test_cmd_serve_prints_startup_url_and_manages_pidfile(env, monkeypatch, capsys):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("REVIEW_BRANCH_PORT", str(port))
    t = threading.Thread(target=review_tool.cmd_serve, daemon=True)
    t.start()
    try:
        assert review_tool._wait(lambda: review_tool.health_check(port) is not None)
        assert review_tool.pidfile().exists()
        err = capsys.readouterr().err
        assert f"http://127.0.0.1:{port}/" in err
        assert "Ctrl-C to stop" in err
    finally:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", method="POST", data=b"")
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass
        t.join(timeout=5)
        assert not review_tool.pidfile().exists()


def test_open_spawns_daemon_on_dead_port(env, monkeypatch, capsys):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("REVIEW_BRANCH_PORT", str(port))
    d = review_tool.data_root() / "proj-abcd" / "mr-4" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(REVIEW_TOML)
    try:
        assert review_tool.main(["url", str(d)]) == 0
        url = capsys.readouterr().out.strip()
        assert url == f"http://127.0.0.1:{port}/proj-abcd/mr-4/round-1/"
        health = review_tool.health_check(port)
        assert health is not None
        assert health["app"] == "review-branch"
    finally:
        review_tool.cmd_stop()
        assert review_tool._wait(lambda: review_tool.health_check(port) is None)

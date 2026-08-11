# ABOUTME: tests for the init subcommand round-directory creation
# ABOUTME: covers first round, round increment, and CLI stdout contract

import subprocess

import pytest

import review_tool
from conftest import make_repo


def test_init_creates_round_one(env):
    repo = make_repo(env / "proj", origin="https://gitlab.example.com/g/proj.git")
    d = review_tool.cmd_init("mr-124", repo)
    assert d.name == "round-1"
    assert d.parent.name == "mr-124"
    assert d.is_dir()
    assert d.parent.parent.parent == review_tool.data_root()


def test_init_increments_rounds(env):
    repo = make_repo(env / "proj", origin="https://gitlab.example.com/g/proj.git")
    review_tool.cmd_init("mr-124", repo)
    d2 = review_tool.cmd_init("mr-124", repo)
    assert d2.name == "round-2"


def test_init_rejects_slug_that_escapes_a_path_segment(env):
    repo = make_repo(env / "proj", origin="https://gitlab.example.com/g/proj.git")
    with pytest.raises(SystemExit):
        review_tool.cmd_init("../evil", repo)


def test_init_cli_prints_path(env, capsys, monkeypatch):
    repo = make_repo(env / "proj", origin="https://gitlab.example.com/g/proj.git")
    monkeypatch.chdir(repo)
    assert review_tool.main(["init", "--slug", "mr-9"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("mr-9/round-1")


def test_init_from_worktree_matches_main_repo(env, tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        subprocess.run(["git", "-C", str(repo), "config", k, v], check=True)
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    wt = repo / ".claude" / "worktrees" / "feature-x"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "-b",
                    "feature/x", str(wt)], check=True)

    from review_tool import repo_id, cmd_init
    assert repo_id(wt) == repo_id(repo)
    round_from_wt = cmd_init("myslug", wt)
    assert round_from_wt.name == "round-1"
    assert repo_id(repo) in str(round_from_wt)

# ABOUTME: tests for data/state root resolution and repo identity hashing
# ABOUTME: covers env overrides, XDG fallbacks, remote vs path seeds, worktree resolution

from pathlib import Path

import review_tool
from conftest import make_repo, run_git


def test_data_root_honors_review_branch_home(env):
    assert review_tool.data_root() == env / "data"


def test_data_root_falls_back_to_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("REVIEW_BRANCH_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert review_tool.data_root() == tmp_path / "xdg" / "review-branch"


def test_state_root_uses_xdg_state_home(env):
    assert review_tool.state_root() == env / "state" / "review-branch"


def test_repo_id_uses_origin_url_and_repo_name(env):
    repo = make_repo(env / "myproj", origin="git@gitlab.example.com:g/myproj.git")
    rid = review_tool.repo_id(repo)
    assert rid.startswith("myproj-")
    assert len(rid) == len("myproj-") + 4


def test_repo_id_stable_across_worktrees(env):
    repo = make_repo(env / "myproj", origin="git@gitlab.example.com:g/myproj.git")
    run_git(repo, "worktree", "add", str(env / "wt"), "-b", "feature")
    assert review_tool.repo_id(env / "wt") == review_tool.repo_id(repo)


def test_repo_id_without_remote_uses_path(env):
    a = make_repo(env / "same")
    b = make_repo(env / "other")
    assert review_tool.repo_id(a) != review_tool.repo_id(b)

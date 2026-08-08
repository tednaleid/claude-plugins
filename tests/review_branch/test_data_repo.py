# ABOUTME: tests for the auto-committing git repo at the data root
# ABOUTME: covers creation, idempotency, commit messages, and empty-commit no-ops

import review_tool


def test_ensure_data_repo_creates_git_repo(env):
    root = review_tool.ensure_data_repo()
    assert (root / ".git").is_dir()


def test_ensure_data_repo_is_idempotent(env):
    review_tool.ensure_data_repo()
    review_tool.ensure_data_repo()  # must not raise or re-init


def test_data_commit_records_message(env):
    root = review_tool.ensure_data_repo()
    (root / "f.txt").write_text("hello\n")
    review_tool.data_commit("proj-abcd mr-1 round-1: state update")
    log = review_tool.git(root, "log", "--oneline")
    assert "proj-abcd mr-1 round-1: state update" in log


def test_data_commit_with_no_changes_is_noop(env):
    review_tool.ensure_data_repo()
    review_tool.data_commit("nothing changed")  # must not raise

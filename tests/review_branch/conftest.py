# ABOUTME: pytest path setup and shared fixtures for review-branch script tests
# ABOUTME: makes plugins/review-branch/scripts importable and provides temp env/repos

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "review-branch" / "scripts"),
)


def run_git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def make_repo(path, origin=None):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    (path / "README.md").write_text("x\n")
    run_git(path, "add", "-A")
    run_git(path, "commit", "-q", "-m", "init")
    if origin:
        run_git(path, "remote", "add", "origin", origin)
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_BRANCH_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("REVIEW_BRANCH_BIN", str(tmp_path / "bin"))
    monkeypatch.delenv("REVIEW_BRANCH_PORT", raising=False)
    return tmp_path

# ABOUTME: tests for the init subcommand round-directory creation
# ABOUTME: covers first round, round increment, and CLI stdout contract

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

# ABOUTME: tests for resolving the round to open from the branch checked out in the cwd
# ABOUTME: covers source_branch matching, round precedence, worktrees, and the failure listing

import pytest

import review_tool
from conftest import make_repo, run_git


def seed(repo, slug, round_n, source_branch, mtime=None):
    d = review_tool.data_root() / review_tool.repo_id(repo) / slug / f"round-{round_n}"
    d.mkdir(parents=True)
    toml = d / "review.toml"
    toml.write_text(f'[review]\ntitle = "{slug}"\nsource_branch = "{source_branch}"\n')
    if mtime is not None:
        import os

        os.utime(toml, (mtime, mtime))
    return d


@pytest.fixture
def repo(env, tmp_path):
    r = make_repo(tmp_path / "proj", origin="git@example.com:o/proj.git")
    run_git(r, "checkout", "-q", "-b", "FORGE-365-assign-level")
    return r


def test_resolves_mr_slug_from_the_branch_it_reviewed(repo):
    # the slug says mr-317, nothing in it names the branch; source_branch is the link
    target = seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    seed(repo, "mr-313", 1, "FORGE-365-store-access-level")
    assert review_tool.resolve_round(repo) == target


def test_latest_round_wins_for_the_same_branch(repo):
    seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    r2 = seed(repo, "mr-317", 2, "FORGE-365-assign-level")
    assert review_tool.resolve_round(repo) == r2


def test_round_10_beats_round_9_despite_lexical_order(repo):
    seed(repo, "mr-317", 9, "FORGE-365-assign-level")
    r10 = seed(repo, "mr-317", 10, "FORGE-365-assign-level")
    assert review_tool.resolve_round(repo) == r10


def test_resolves_from_inside_a_worktree(repo, tmp_path):
    target = seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    wt = tmp_path / "wt"
    # git refuses a second worktree on a branch already checked out, so park the main one
    run_git(repo, "checkout", "-q", "-b", "parking")
    run_git(repo, "worktree", "add", "-q", str(wt), "FORGE-365-assign-level")
    # repo_id must hash the main worktree, not the linked one, or the round is unreachable
    assert review_tool.resolve_round(wt) == target


def test_other_repos_rounds_are_not_candidates(repo, env, tmp_path):
    other = make_repo(tmp_path / "other", origin="git@example.com:o/other.git")
    seed(other, "mr-1", 1, "FORGE-365-assign-level")
    with pytest.raises(SystemExit) as e:
        review_tool.resolve_round(repo)
    assert "no reviews recorded for" in str(e.value)


def test_unmatched_branch_lists_recent_rounds_newest_first(repo):
    seed(repo, "mr-300", 1, "old-branch", mtime=1_000_000)
    seed(repo, "mr-301", 1, "newer-branch", mtime=2_000_000)
    run_git(repo, "checkout", "-q", "-b", "unreviewed")
    with pytest.raises(SystemExit) as e:
        review_tool.resolve_round(repo)
    msg = str(e.value)
    assert "no review for branch unreviewed" in msg
    assert msg.index("mr-301/round-1") < msg.index("mr-300/round-1")
    assert "newer-branch" in msg and "old-branch" in msg


def test_malformed_review_toml_is_skipped_not_fatal(repo):
    bad = review_tool.data_root() / review_tool.repo_id(repo) / "mr-999" / "round-1"
    bad.mkdir(parents=True)
    (bad / "review.toml").write_text("[review\nbroken = ")
    target = seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    assert review_tool.resolve_round(repo) == target


def test_non_git_directory_is_a_clean_error(env, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(SystemExit) as e:
        review_tool.resolve_round(plain)
    assert "not a git repository" in str(e.value)


@pytest.fixture
def spy(monkeypatch):
    """Stand in for the daemon: record the round asked for and any browser launch."""
    calls = {"round": [], "launched": []}
    monkeypatch.setattr(
        review_tool, "cmd_url", lambda d: calls["round"].append(d) or "http://x/round-1/"
    )
    monkeypatch.setattr(
        review_tool.webbrowser, "open", lambda u: calls["launched"].append(u)
    )
    return calls


def test_url_resolves_the_branch_and_never_launches_a_browser(repo, monkeypatch, spy, capsys):
    target = seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    monkeypatch.chdir(repo)
    assert review_tool.main(["url"]) == 0
    assert spy["round"] == [target]
    assert spy["launched"] == []
    assert capsys.readouterr().out.strip() == "http://x/round-1/"


def test_open_resolves_the_branch_and_launches_what_it_printed(repo, monkeypatch, spy, capsys):
    target = seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    monkeypatch.chdir(repo)
    assert review_tool.main(["open"]) == 0
    assert spy["round"] == [target]
    assert spy["launched"] == ["http://x/round-1/"]
    assert capsys.readouterr().out.strip() == "http://x/round-1/"


@pytest.mark.parametrize("command", ["url", "open"])
def test_explicit_review_dir_wins_over_inference(repo, monkeypatch, spy, command):
    seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    explicit = seed(repo, "mr-313", 1, "some-other-branch")
    monkeypatch.chdir(repo)
    assert review_tool.main([command, str(explicit)]) == 0
    assert spy["round"] == [explicit]


def test_subcommands_constant_matches_the_parser(capsys):
    with pytest.raises(SystemExit):
        review_tool.main(["--help"])
    help_text = capsys.readouterr().out
    for name in review_tool.SUBCOMMANDS:
        assert f"    {name} " in help_text, f"{name} missing a help= string"

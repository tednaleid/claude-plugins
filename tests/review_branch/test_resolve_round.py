# ABOUTME: tests for picking which round url/open act on, and for the list subcommand
# ABOUTME: covers branch and MR-number targets, round precedence, worktrees, index fallback

import re

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


def resolve(repo, target=None):
    return review_tool.resolve_target(repo, target)[0]


def test_resolves_mr_slug_from_the_branch_it_reviewed(repo):
    # the slug says mr-317, nothing in it names the branch; source_branch is the link
    target = seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    seed(repo, "mr-313", 1, "FORGE-365-store-access-level")
    assert resolve(repo) == target


def test_latest_round_wins_for_the_same_branch(repo):
    seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    r2 = seed(repo, "mr-317", 2, "FORGE-365-assign-level")
    assert resolve(repo) == r2


def test_round_10_beats_round_9_despite_lexical_order(repo):
    seed(repo, "mr-317", 9, "FORGE-365-assign-level")
    r10 = seed(repo, "mr-317", 10, "FORGE-365-assign-level")
    assert resolve(repo) == r10


def test_resolves_from_inside_a_worktree(repo, tmp_path):
    target = seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    wt = tmp_path / "wt"
    # git refuses a second worktree on a branch already checked out, so park the main one
    run_git(repo, "checkout", "-q", "-b", "parking")
    run_git(repo, "worktree", "add", "-q", str(wt), "FORGE-365-assign-level")
    # repo_id must hash the main worktree, not the linked one, or the round is unreachable
    assert resolve(wt) == target


def test_other_repos_rounds_are_not_candidates(repo, env, tmp_path):
    other = make_repo(tmp_path / "other", origin="git@example.com:o/other.git")
    seed(other, "mr-1", 1, "FORGE-365-assign-level")
    assert resolve(repo) is None


def test_malformed_review_toml_is_skipped_not_fatal(repo):
    bad = review_tool.data_root() / review_tool.repo_id(repo) / "mr-999" / "round-1"
    bad.mkdir(parents=True)
    (bad / "review.toml").write_text("[review\nbroken = ")
    target = seed(repo, "mr-317", 1, "FORGE-365-assign-level")
    assert resolve(repo) == target


def test_non_git_directory_is_a_clean_error(env, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(SystemExit) as e:
        resolve(plain)
    assert "not a git repository" in str(e.value)


# --- targets other than the current branch ---


def test_bare_number_resolves_an_mr_slug(repo):
    target = seed(repo, "mr-336", 1, "some-branch")
    seed(repo, "mr-313", 1, "another-branch")
    assert resolve(repo, "336") == target


def test_bare_number_resolves_a_pr_slug_too(repo):
    target = seed(repo, "pr-42", 1, "some-branch")
    assert resolve(repo, "42") == target


def test_number_takes_the_latest_round(repo):
    seed(repo, "mr-254", 1, "FORGE-310")
    r2 = seed(repo, "mr-254", 2, "FORGE-310")
    assert resolve(repo, "254") == r2


def test_target_matches_a_branch_name(repo):
    target = seed(repo, "mr-336", 1, "FORGE-308-viability")
    assert resolve(repo, "FORGE-308-viability") == target


def test_target_matches_a_slug(repo):
    target = seed(repo, "mr-336", 1, "FORGE-308-viability")
    assert resolve(repo, "mr-336") == target


def test_explicit_round_directory_needs_no_git_repo(env, tmp_path):
    d = tmp_path / "somewhere" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text('[review]\ntitle = "t"\n')
    assert resolve(tmp_path / "not-a-repo", str(d)) == d


def test_unknown_target_resolves_to_nothing(repo):
    seed(repo, "mr-336", 1, "some-branch")
    assert resolve(repo, "999") is None
    assert resolve(repo, "no-such-branch") is None


# --- list ---


def test_list_shows_this_repos_rounds_newest_first(repo, capsys):
    seed(repo, "mr-300", 1, "old-branch", mtime=1_000_000)
    seed(repo, "mr-301", 1, "newer-branch", mtime=2_000_000)
    assert review_tool.cmd_list(repo, everywhere=False) == 0
    out = capsys.readouterr().out
    assert out.index("mr-301/round-1") < out.index("mr-300/round-1")
    assert "newer-branch" in out and "old-branch" in out


def test_list_excludes_other_repos_until_all(repo, env, tmp_path, capsys):
    seed(repo, "mr-300", 1, "mine")
    other = make_repo(tmp_path / "other", origin="git@example.com:o/other.git")
    seed(other, "mr-1", 1, "theirs")
    review_tool.cmd_list(repo, everywhere=False)
    assert "theirs" not in capsys.readouterr().out
    review_tool.cmd_list(repo, everywhere=True)
    out = capsys.readouterr().out
    assert "theirs" in out and "mine" in out
    assert "other-" in out  # --all prefixes the repo id


def test_list_with_no_reviews_is_a_nonzero_exit(repo, capsys):
    assert review_tool.cmd_list(repo, everywhere=False) == 1
    assert "no reviews recorded" in capsys.readouterr().err


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


def test_index_fallback_when_nothing_matches(repo, monkeypatch, spy, capsys):
    seed(repo, "mr-336", 1, "some-other-branch")
    monkeypatch.setattr(review_tool, "index_url", lambda: "http://x/")
    monkeypatch.chdir(repo)
    assert review_tool.main(["open"]) == 0
    captured = capsys.readouterr()
    assert spy["round"] == []  # never asked for a specific round
    assert spy["launched"] == ["http://x/"]
    assert captured.out.strip() == "http://x/"
    assert "no review for branch FORGE-365-assign-level" in captured.err
    assert "mr-336/round-1" in captured.err and "some-other-branch" in captured.err


def test_every_subcommand_in_the_usage_line_is_described(capsys):
    with pytest.raises(SystemExit):
        review_tool.main(["--help"])
    help_text = capsys.readouterr().out
    choices = re.search(r"\{([a-z,]+)\}", help_text).group(1).split(",")
    assert len(choices) > 5
    for name in choices:
        assert f"    {name} " in help_text, f"{name} is listed but has no help= string"

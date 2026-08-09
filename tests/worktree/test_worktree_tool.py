# ABOUTME: tests for worktree_tool helpers (slug, env-file filter, hook parsing,
# ABOUTME: verb resolution, worktree parsing) plus git-backed list/remove/install
import subprocess

import pytest

import worktree_tool as wt

MISSING_BINARY = "definitely-not-a-real-worktree-tool-binary"


def git_repo(path):
    """A git repo at `path` with one commit; returns its resolved top-level."""
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for key, val in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        subprocess.run(["git", "-C", str(path), "config", key, val], check=True)
    (path / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_slug_dir_replaces_slashes():
    assert wt.slug_dir("feature/auth-fix") == "feature-auth-fix"
    assert wt.slug_dir("main") == "main"


def test_env_files_to_copy_keeps_only_env_and_envrc():
    given = [".env", ".env.local", ".envrc", ".venv/x", "node_modules/y",
             ".DS_Store", "build/z", "notes.txt"]
    assert wt.env_files_to_copy(given) == [".env", ".env.local", ".envrc"]


def test_load_hooks_absent_file_yields_empty(tmp_path):
    hooks = wt.load_hooks(tmp_path)
    assert hooks == {"copy": [], "symlink": [], "command": []}


def test_load_hooks_parses_worktree_toml(tmp_path):
    (tmp_path / ".worktree.toml").write_text(
        '[[copy]]\nfrom = ".env"\nto = ".env"\n\n'
        '[[symlink]]\nfrom = ".bin"\nto = ".bin"\n\n'
        '[[command]]\nrun = "uv sync"\n'
    )
    hooks = wt.load_hooks(tmp_path)
    assert hooks["copy"] == [{"from": ".env", "to": ".env"}]
    assert hooks["symlink"] == [{"from": ".bin", "to": ".bin"}]
    assert hooks["command"] == [{"run": "uv sync"}]


def test_run_missing_executable_check_false_returns_synthetic_failure(tmp_path):
    result = wt.run(tmp_path, MISSING_BINARY, check=False)
    assert result.returncode == 127
    assert MISSING_BINARY in result.stderr


def test_run_missing_executable_check_true_raises_system_exit(tmp_path):
    with pytest.raises(SystemExit):
        wt.run(tmp_path, MISSING_BINARY)


@pytest.mark.parametrize("argv, expected", [
    ([], ("list", [])),
    (["cr", "foo"], ("create", ["foo"])),
    (["c"], ("create", [])),
    (["l"], ("list", [])),
    (["re", "x"], ("remove", ["x"])),          # "re" is a unique prefix of remove
    (["i"], ("install", [])),
    (["feature/x"], ("list", ["feature/x"])),  # unmatched -> list filter
    (["--", "create"], ("list", ["create"])),  # -- forces literal filter
    (["-x"], ("list", ["-x"])),                # leading option -> list
])
def test_resolve_maps_argv_to_verb(argv, expected):
    assert wt.resolve(argv) == expected


def test_resolve_ambiguous_prefix_lists_candidates(monkeypatch):
    monkeypatch.setattr(wt, "VERBS", ("copy", "count"))
    with pytest.raises(SystemExit) as exc:
        wt.resolve(["co"])
    assert "copy" in str(exc.value) and "count" in str(exc.value)


PORCELAIN = (
    "worktree /repo\n"
    "HEAD 1111111122222222\n"
    "branch refs/heads/main\n"
    "\n"
    "worktree /repo/.claude/worktrees/feature-x\n"
    "HEAD 3333333344444444\n"
    "branch refs/heads/feature/x\n"
    "\n"
    "worktree /repo/.claude/worktrees/loose\n"
    "HEAD 5555555566666666\n"
    "detached\n"
)


def test_parse_worktrees_extracts_path_head_branch():
    entries = wt.parse_worktrees(PORCELAIN)
    assert [e["branch"] for e in entries] == ["main", "feature/x", "(detached)"]
    assert entries[0] == {"path": "/repo", "head": "11111111", "branch": "main"}
    assert entries[2]["path"] == "/repo/.claude/worktrees/loose"


def test_match_worktrees_requires_all_terms():
    entries = wt.parse_worktrees(PORCELAIN)
    assert [e["branch"] for e in wt.match_worktrees(entries, ["feature"])] == ["feature/x"]
    assert wt.match_worktrees(entries, ["feature", "loose"]) == []
    assert len(wt.match_worktrees(entries, [])) == 3


def test_cmd_install_copies_script_as_wt(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKTREE_BIN", str(tmp_path / "bin"))
    assert wt.cmd_install() == 0
    installed = tmp_path / "bin" / "wt"
    assert installed.exists()
    assert installed.stat().st_mode & 0o111        # executable
    assert installed.read_bytes()[:2] == b"#!"     # copied the shebang script


def test_cmd_list_and_remove_against_real_git(tmp_path, capsys):
    root = git_repo(tmp_path / "repo")
    dest = wt.Path(root) / ".claude" / "worktrees" / "feature-x"
    wt.create_worktree(root, "feature/x", dest)

    assert wt.cmd_list([], root) == 0
    listed = capsys.readouterr().out
    assert "feature/x" in listed
    assert str(dest) in listed

    assert wt.cmd_remove(["feature"], root) == 0
    assert not dest.exists()


def test_cmd_remove_refuses_ambiguous(tmp_path):
    root = git_repo(tmp_path / "repo")
    for branch in ("feature/a", "feature/b"):
        wt.create_worktree(root, branch, wt.Path(root) / ".claude" / "worktrees" / wt.slug_dir(branch))
    with pytest.raises(SystemExit) as exc:
        wt.cmd_remove(["feature"], root)
    assert "ambiguous" in str(exc.value)


def test_cmd_remove_never_matches_main_worktree(tmp_path):
    root = git_repo(tmp_path / "repo")
    with pytest.raises(SystemExit) as exc:
        wt.cmd_remove([], root)  # only the main worktree exists
    assert "no worktree matches" in str(exc.value)

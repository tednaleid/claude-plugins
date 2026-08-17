# ABOUTME: tests for worktree_tool helpers (slug, env-file filter, hook parsing,
# ABOUTME: verb resolution, worktree parsing) plus git-backed list/remove/install
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import worktree_tool as wt

PLUGIN_JSON = (
    Path(__file__).resolve().parents[2]
    / "plugins" / "worktree" / ".claude-plugin" / "plugin.json"
)

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


def test_run_streaming_sends_child_stdout_to_stderr(tmp_path, capfd):
    """stdout belongs to the worktree path alone, so a streamed child must not write there."""
    wt.run(tmp_path, "sh", "-c", "echo child-noise", capture=False)
    captured = capfd.readouterr()
    assert "child-noise" not in captured.out
    assert "child-noise" in captured.err


@pytest.mark.parametrize("argv, expected", [
    ([], ("list", [])),
    (["cr", "foo"], ("create", ["foo"])),
    (["c"], ("create", [])),
    (["l"], ("list", [])),
    (["re", "x"], ("remove", ["x"])),          # "re" is a unique prefix of remove
    (["i"], ("install", [])),
    (["v"], ("version", [])),
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


class _FakeStderr:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty

    def write(self, *_):
        pass

    def flush(self):
        pass


def test_stream_level_flags_override():
    assert wt.stream_level(["-q"]) == 0
    assert wt.stream_level(["--quiet"]) == 0
    assert wt.stream_level(["-v"]) == 2
    assert wt.stream_level(["--verbose"]) == 2


def test_stream_level_auto_detects_tty(monkeypatch):
    monkeypatch.setattr(wt.sys, "stderr", _FakeStderr(True))
    assert wt.stream_level([]) == 2
    monkeypatch.setattr(wt.sys, "stderr", _FakeStderr(False))
    assert wt.stream_level([]) == 1


def test_phase_silent_at_quiet_level(capsys):
    wt.phase(0, "hidden")
    wt.phase(1, "shown")
    err = capsys.readouterr().err
    assert "hidden" not in err
    assert "shown" in err


def test_bootstrap_success_announces_and_returns_label(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    monkeypatch.setattr(
        wt, "run",
        lambda cwd, *a, **k: subprocess.CompletedProcess(list(a), 0, "", ""),
    )
    assert wt.bootstrap(tmp_path, tmp_path, 1) == "uv sync"
    assert "bootstrap: uv sync" in capsys.readouterr().err


def test_bootstrap_surfaces_failure(tmp_path, monkeypatch, capsys):
    (tmp_path / "package-lock.json").write_text("{}")
    monkeypatch.setattr(
        wt, "run",
        lambda cwd, *a, **k: subprocess.CompletedProcess(list(a), 1, "", "boom"),
    )
    assert wt.bootstrap(tmp_path, tmp_path, 1) == "npm install (failed)"
    err = capsys.readouterr().err
    assert "boom" in err
    assert "bootstrap failed" in err


def test_bootstrap_none_when_no_lockfile(tmp_path):
    assert wt.bootstrap(tmp_path, tmp_path, 1) == "no bootstrap"


def test_cmd_create_rejects_unknown_flag(tmp_path):
    with pytest.raises(SystemExit) as exc:
        wt.cmd_create(["--frce"], str(tmp_path))
    assert "unknown option" in str(exc.value)


def worktree_dest(root, branch):
    return wt.Path(root) / ".claude" / "worktrees" / wt.slug_dir(branch)


def test_cmd_create_reuses_an_existing_worktree(tmp_path, capsys):
    root = git_repo(tmp_path / "repo")
    dest = worktree_dest(root, "feature/x")
    wt.create_worktree(root, "feature/x", dest)

    assert wt.cmd_create(["feature/x"], root) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == str(dest)
    assert "reused" in captured.err


def test_cmd_create_rejects_a_path_that_is_not_a_worktree(tmp_path):
    root = git_repo(tmp_path / "repo")
    worktree_dest(root, "feature/x").mkdir(parents=True)

    with pytest.raises(SystemExit) as exc:
        wt.cmd_create(["feature/x"], root)
    assert "not a git worktree" in str(exc.value)


def test_cmd_create_rejects_a_gutted_worktree_directory(tmp_path):
    """A `rm -rf`'d worktree leaves git's registration behind; the path is not usable."""
    root = git_repo(tmp_path / "repo")
    dest = worktree_dest(root, "feature/x")
    wt.create_worktree(root, "feature/x", dest)
    shutil.rmtree(dest)
    dest.mkdir()

    with pytest.raises(SystemExit) as exc:
        wt.cmd_create(["feature/x"], root)
    assert "not a git worktree" in str(exc.value)


def test_cmd_create_recreates_after_the_worktree_directory_is_deleted(tmp_path):
    root = git_repo(tmp_path / "repo")
    dest = worktree_dest(root, "feature/x")
    wt.create_worktree(root, "feature/x", dest)
    shutil.rmtree(dest)

    assert wt.cmd_create(["feature/x"], root) == 0
    assert (dest / "f.txt").exists()


def test_cmd_create_reuse_recopies_env_files_over_local_edits(tmp_path):
    root = git_repo(tmp_path / "repo")
    (wt.Path(root) / ".gitignore").write_text(".env\n")
    (wt.Path(root) / ".env").write_text("MAIN=1\n")
    dest = worktree_dest(root, "feature/x")
    wt.create_worktree(root, "feature/x", dest)
    (dest / ".env").write_text("LOCAL=1\n")

    assert wt.cmd_create(["feature/x"], root) == 0
    assert (dest / ".env").read_text() == "MAIN=1\n"


def test_cmd_create_reuse_reruns_command_hooks(tmp_path):
    root = git_repo(tmp_path / "repo")
    (wt.Path(root) / ".worktree.toml").write_text(
        '[[command]]\nrun = "echo ran >> marker.txt"\n'
    )
    dest = worktree_dest(root, "feature/x")

    assert wt.cmd_create(["feature/x"], root) == 0
    assert wt.cmd_create(["feature/x"], root) == 0
    assert (dest / "marker.txt").read_text().count("ran") == 2


def test_cmd_create_reuse_reruns_bootstrap(tmp_path, monkeypatch):
    root = git_repo(tmp_path / "repo")
    dest = worktree_dest(root, "feature/x")
    wt.create_worktree(root, "feature/x", dest)
    calls = []
    monkeypatch.setattr(wt, "bootstrap",
                        lambda repo_root, d, level: calls.append(d) or "uv sync")

    assert wt.cmd_create(["feature/x"], root) == 0
    assert calls == [dest]


def test_cmd_create_streaming_prints_only_the_path_on_stdout(tmp_path, capfd):
    """`wt_path=$(wt create ...)` at a terminal: level 2 streams, stdout stays one line."""
    root = git_repo(tmp_path / "repo")
    (wt.Path(root) / ".worktree.toml").write_text(
        '[[command]]\nrun = "echo hook-noise"\n'
    )
    dest = worktree_dest(root, "feature/x")

    assert wt.cmd_create(["-v", "feature/x"], root) == 0
    captured = capfd.readouterr()
    assert captured.out.splitlines() == [str(dest)]
    assert "hook-noise" in captured.err


def test_main_verb_help_does_not_create(capsys):
    assert wt.main(["create", "--help"]) == 0
    out = capsys.readouterr().out
    assert "wt create" in out
    assert "bootstrap" in out


def test_main_help_topic(capsys):
    assert wt.main(["help", "re"]) == 0        # prefix resolves to remove
    assert "wt remove" in capsys.readouterr().out


def test_main_bare_help_prints_usage(capsys):
    assert wt.main(["--help"]) == 0
    assert "manage git worktrees" in capsys.readouterr().out


def test_version_matches_plugin_json():
    declared = json.loads(PLUGIN_JSON.read_text())["version"]
    assert wt.VERSION == declared, (
        f"wt.VERSION {wt.VERSION} != plugin.json {declared}; run `just sync`"
    )


def test_cmd_version_prints_wt_version(capsys):
    assert wt.cmd_version() == 0
    assert capsys.readouterr().out.strip() == f"wt {wt.VERSION}"


def test_main_version_flag(capsys):
    assert wt.main(["--version"]) == 0
    assert wt.VERSION in capsys.readouterr().out


def test_main_version_verb(capsys):
    assert wt.main(["version"]) == 0
    assert wt.VERSION in capsys.readouterr().out

# ABOUTME: tests for worktree_tool pure helpers (slug, env-file filter, hook parsing)
# ABOUTME: no git side effects; only the pure functions are exercised

import worktree_tool as wt


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

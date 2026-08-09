# ABOUTME: tests for the install subcommand copying scripts to the bin dir
# ABOUTME: covers copy, executable bit, missing-source skip, and env override

import os

import review_tool


def test_install_scripts_copies_and_chmods(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "review_tool.py").write_text("#!/usr/bin/env python3\n")
    (src / "glab_comment.py").write_text("#!/usr/bin/env python3\n")
    dest = tmp_path / "bin"
    installed = review_tool.install_scripts(src, dest)
    assert installed == ["review-branch", "glab-comment"]
    assert (dest / "review-branch").exists()
    assert os.access(dest / "review-branch", os.X_OK)
    assert not (dest / "gh-comment").exists()


def test_cmd_install_uses_env_bin(env, capsys):
    assert review_tool.main(["install"]) == 0
    out = capsys.readouterr().out
    assert str(env / "bin" / "review-branch") in out
    assert (env / "bin" / "review-branch").exists()
    assert "glab-comment" in out and "gh-comment" in out

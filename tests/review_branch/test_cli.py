# ABOUTME: tests for the review_tool CLI entry point
# ABOUTME: covers --version output and unknown-command handling

import pytest

import review_tool


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exc:
        review_tool.main(["--version"])
    assert exc.value.code == 0
    assert review_tool.__version__ in capsys.readouterr().out


def test_no_args_prints_usage_and_fails(capsys):
    assert review_tool.main([]) == 2
    assert "usage" in capsys.readouterr().err.lower()

"""CLI entry point: argument parsing, exit codes, JSON output."""

import io
import json
import sys
from pathlib import Path

from claude_config_auditor.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_runs_on_good_fixture(capsys):
    rc = main([str(FIXTURES / "good"), "--no-color"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Session-start fixed cost" in out
    assert "read-only" in out


def test_cli_json_output_is_valid(capsys):
    rc = main([str(FIXTURES / "good"), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["session_start_total_tokens"] > 0
    assert data["tokenizer"]["estimate"] is True
    assert "files" in data
    assert "findings" in data


def test_cli_does_not_crash_on_missing_dir(capsys):
    rc = main([str(FIXTURES / "definitely-not-here"), "--no-color"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "does not exist" in err


def test_cli_does_not_crash_on_broken_fixture(capsys):
    rc = main([str(FIXTURES / "broken"), "--no-color"])
    out = capsys.readouterr().out
    assert rc == 0  # default --fail-on=never
    assert "error" in out.lower() or "warning" in out.lower()


def test_cli_fail_on_error_returns_nonzero(capsys):
    rc = main([str(FIXTURES / "broken"), "--no-color", "--fail-on", "error"])
    assert rc == 1


def test_cli_html_output_is_self_contained(tmp_path, capsys):
    out_file = tmp_path / "report.html"
    rc = main([str(FIXTURES / "good"), "--html", str(out_file)])
    capsys.readouterr()
    assert rc == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    # Must be a real HTML document.
    assert content.startswith("<!doctype html>")
    # Critical pieces from the report.
    assert "Session-start cost" in content
    assert "Window utilization" in content
    assert "<svg" in content
    assert "claude-config-auditor" in content
    # Theme support
    assert "prefers-color-scheme: dark" in content
    assert "theme-toggle" in content
    # No external network deps — the file should open offline.
    assert "http://" not in content
    assert "https://" not in content


def test_cli_html_refuses_path_inside_target(tmp_path, capsys):
    # Try to write the report inside the target dir.
    target = FIXTURES / "good"
    out_file = target / "report.html"
    rc = main([str(target), "--html", str(out_file)])
    capsys.readouterr()
    assert rc == 2
    assert not out_file.exists()

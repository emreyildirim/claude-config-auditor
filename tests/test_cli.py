"""CLI entry point: argument parsing, exit codes, JSON output."""

import io
import json
import sys
from pathlib import Path

from claude_config_auditor.cli import _should_use_color, build_parser, main

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_runs_on_good_fixture(capsys):
    rc = main([str(FIXTURES / "good"), "--no-color"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Always-loaded session footprint" in out
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
    assert "Always loaded" in content
    assert "Window utilization" in content
    assert "<svg" in content
    assert "claude-config-auditor" in content
    # Theme support
    assert "prefers-color-scheme: dark" in content
    assert "theme-toggle" in content
    # Info tooltips: 4 KPI cards + 4 panel headers = 8 ⓘ buttons.
    assert content.count('class="info"') == 8
    # Each tooltip carries its plain-language explanation, not jargon.
    assert "context window" in content.lower()
    # The eager/on-demand split must be visible in the Categories table.
    assert "On-demand" in content
    assert "Eager" in content
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


# --- color resolution (--no-color flag + NO_COLOR env) ---------------------

def _ns(*argv):
    """Parse argv to an argparse.Namespace, including the target positional."""
    return build_parser().parse_args([".", *argv])


def test_color_on_by_default():
    assert _should_use_color(_ns(), {}) is True


def test_no_color_flag_disables_color():
    assert _should_use_color(_ns("--no-color"), {}) is False


def test_no_color_env_disables_color():
    assert _should_use_color(_ns(), {"NO_COLOR": "1"}) is False
    # Per the no-color.org convention, the value does not matter — any
    # non-empty string disables color.
    assert _should_use_color(_ns(), {"NO_COLOR": "yes"}) is False
    assert _should_use_color(_ns(), {"NO_COLOR": "anything"}) is False


def test_empty_no_color_does_not_disable_color():
    # An empty NO_COLOR is treated as unset.
    assert _should_use_color(_ns(), {"NO_COLOR": ""}) is True


def test_no_color_env_works_through_full_cli(monkeypatch, capsys):
    """End-to-end: NO_COLOR in os.environ should suppress ANSI codes
    in terminal output even without the --no-color flag."""
    monkeypatch.setenv("NO_COLOR", "1")
    rc = main([str(FIXTURES / "good")])
    out = capsys.readouterr().out
    assert rc == 0
    # ANSI CSI escape sequences should not appear in output.
    assert "\x1b[" not in out

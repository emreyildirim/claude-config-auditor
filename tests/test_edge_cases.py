"""Edge-case coverage: things a real user might hit that the happy-path
tests don't exercise."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_config_auditor.checks import agents as agents_check
from claude_config_auditor.checks import budget as budget_check
from claude_config_auditor.checks import health as health_check
from claude_config_auditor.cli import main
from claude_config_auditor.scanner import scan
from claude_config_auditor.tokens import Estimator, get_estimator


# --- Unicode / multi-byte content -------------------------------------------

def test_scanner_handles_unicode_content(tmp_path: Path):
    """Turkish, emoji, and CJK characters must not crash the scanner."""
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    agent = tmp_path / ".claude" / "agents" / "tr-agent.md"
    agent.write_text(
        '---\n'
        'name: tr-agent\n'
        'description: |\n'
        '  Türkçe karakter testi: çığlık ışık öğüt şüphe. '
        'Emoji: 🚀🔥. CJK: 测试中文.\n'
        '---\n\n'
        'Body içinde de unicode olabilir: ñ é ü.\n',
        encoding="utf-8",
    )

    result = scan(tmp_path)
    assert len(result.agents) == 1
    rec = result.agents[0]
    assert rec.frontmatter_ok, rec.parse_warning
    assert "Türkçe" in rec.frontmatter.get("description", "")


def test_tokenizer_does_not_crash_on_unicode():
    est = get_estimator()
    # Should return a positive token count, not raise.
    n = est.count("Çığlık ışık öğüt 🚀 测试 ñé")
    assert n > 0


def test_heuristic_uses_char_count_not_byte_count():
    """A 100-char Turkish string and a 100-char ASCII string should
    estimate to similar token counts under the heuristic — multi-byte
    UTF-8 must not inflate the count."""
    est = Estimator(method="char-heuristic", note="test")
    ascii_text = "a" * 100
    turkish = "ç" * 100  # each "ç" is 2 bytes in UTF-8
    assert est.count(ascii_text) == est.count(turkish)


# --- --budget flag --------------------------------------------------------

def test_budget_flag_lowers_the_claude_md_threshold(tmp_path: Path, capsys):
    """A 500-token CLAUDE.md should pass the default 5000 budget but
    fail when --budget is dropped to 200."""
    # ~500 tokens of generic-prose text.
    content = "lorem ipsum dolor sit amet " * 100
    (tmp_path / "CLAUDE.md").write_text(content, encoding="utf-8")

    # Default budget: no HLT001.
    rc = main([str(tmp_path), "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    codes = {f["code"] for f in data["findings"]}
    assert rc == 0
    assert "HLT001" not in codes

    # Tight budget: HLT001 fires.
    rc = main([str(tmp_path), "--json", "--budget", "200"])
    out = capsys.readouterr().out
    data = json.loads(out)
    codes = {f["code"] for f in data["findings"]}
    assert rc == 0
    assert "HLT001" in codes


# --- Empty .claude/ directory ----------------------------------------------

def test_empty_claude_dir_is_handled_gracefully(tmp_path: Path):
    """Directory exists but contains no agents / skills / rules."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "agents").mkdir()  # empty subdirs
    (claude_dir / "skills").mkdir()
    (claude_dir / "rules").mkdir()

    result = scan(tmp_path)
    assert result.has_claude_dir is True
    assert result.agents == []
    assert result.skills == []
    assert result.rules == []

    est = get_estimator()
    budget = budget_check.compute(result, est)
    assert budget.session_start_total == 0


# --- Symlinks ---------------------------------------------------------------

@pytest.mark.skipif(
    not hasattr(Path, "symlink_to"),
    reason="symlinks not supported on this platform",
)
def test_scanner_follows_symlinked_agent(tmp_path: Path):
    """A .md file symlinked into .claude/agents/ should still be picked up."""
    real = tmp_path / "real-agents"
    real.mkdir()
    real_agent = real / "real.md"
    real_agent.write_text(
        '---\nname: real\ndescription: A real agent linked into agents/.\n---\nBody.\n',
        encoding="utf-8",
    )

    target = tmp_path / "project"
    (target / ".claude" / "agents").mkdir(parents=True)
    link = target / ".claude" / "agents" / "via-link.md"
    try:
        link.symlink_to(real_agent)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem refused to create the symlink")

    result = scan(target)
    names = {Path(a.relpath).name for a in result.agents}
    assert "via-link.md" in names


# --- Heuristic estimator (forced fallback) ---------------------------------

def test_heuristic_estimator_runs_when_tiktoken_is_unavailable(tmp_path: Path):
    """Simulate a machine where tiktoken is not installed. The auditor
    must still produce a sane report and label its estimate as a
    character heuristic."""
    (tmp_path / "CLAUDE.md").write_text(
        "Some guidance content that should be counted.", encoding="utf-8"
    )

    import builtins

    real_import = builtins.__import__

    def deny_tiktoken(name, *args, **kwargs):
        if name == "tiktoken":
            raise ImportError("simulated: tiktoken not installed")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=deny_tiktoken):
        # Must re-import get_estimator with the patched import in place.
        from claude_config_auditor import tokens as tokens_mod
        est = tokens_mod.get_estimator()
        assert est.method == "char-heuristic"
        assert est.count("hello world") > 0
        assert "heuristic" in est.note.lower()


# --- --html + --json combination -------------------------------------------

def test_html_and_json_together(tmp_path: Path, capsys):
    """Passing both flags: JSON goes to stdout, HTML to its file path."""
    out_file = tmp_path / "report.html"
    fixtures = Path(__file__).parent / "fixtures" / "good"
    rc = main([str(fixtures), "--html", str(out_file), "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    # JSON on stdout
    data = json.loads(captured.out)
    assert "session_start_total_tokens" in data
    # HTML file written too
    assert out_file.exists()
    assert out_file.read_text().startswith("<!doctype html>")


# --- Permission denied ------------------------------------------------------

def test_unreadable_file_is_reported_not_raised(tmp_path: Path):
    """A file whose bytes can't be decoded as UTF-8 should be captured
    as a parse warning on its FileRecord, not raise during the scan."""
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    bad = tmp_path / ".claude" / "agents" / "binary.md"
    bad.write_bytes(b"\xff\xfe\x00\x01invalid-utf-8\xff")

    # scan() must not raise.
    result = scan(tmp_path)
    # The file is included but flagged.
    assert any(
        rec.relpath.endswith("binary.md") and not rec.frontmatter_ok
        for rec in result.agents
    )

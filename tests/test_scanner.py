"""Scanner discovers files and parses frontmatter (loosely)."""

from pathlib import Path

from claude_config_auditor.scanner import scan

FIXTURES = Path(__file__).parent / "fixtures"


def test_scan_good_fixture_finds_everything():
    result = scan(FIXTURES / "good")
    assert result.has_claude_dir
    assert result.has_claude_md
    assert len(result.claude_md_files) == 1
    assert len(result.agents) == 2
    assert len(result.skills) == 1
    assert all(rec.frontmatter_ok for rec in result.agents)
    assert all(rec.frontmatter_ok for rec in result.skills)


def test_scan_broken_fixture_does_not_crash_on_bad_yaml():
    result = scan(FIXTURES / "broken")
    assert result.has_claude_dir
    by_name = {rec.relpath.split("/")[-1]: rec for rec in result.agents}
    # bad-yaml.md should have parse_warning set, not raise
    assert not by_name["bad-yaml.md"].frontmatter_ok
    assert by_name["bad-yaml.md"].parse_warning


def test_scan_broken_fixture_handles_missing_skill_frontmatter():
    result = scan(FIXTURES / "broken")
    assert len(result.skills) == 1
    skill = result.skills[0]
    assert not skill.frontmatter_ok


def test_scan_empty_directory_is_graceful():
    result = scan(FIXTURES / "empty")
    assert not result.has_claude_dir
    assert not result.has_claude_md
    assert result.agents == []
    assert result.skills == []


def test_scan_nonexistent_subdir_does_not_explode(tmp_path: Path):
    # Brand-new empty directory: no .claude, no CLAUDE.md.
    result = scan(tmp_path)
    assert not result.has_claude_dir
    assert not result.has_claude_md

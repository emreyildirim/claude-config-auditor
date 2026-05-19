"""Tests for the CLAUDE.md archive proposer.

The archiver is the most delicate Phase 2 fix because it moves
content between files. Coverage focuses on three classes of contract:

  1. Selection is conservative and explainable. Protected headings
     (Rules, Conventions, Workflow, etc.) are never archived even when
     long. Candidates appear with human-readable reasons.
  2. Move is reversible. Apply through the fix flow, then revert; the
     source returns to byte-identical content and the archive file is
     deleted (since the proposal created it).
  3. The source's structural shape is preserved. After the move, the
     source still parses as Markdown with the same heading outline —
     the archived headings are replaced by same-level pointers, not
     deleted outright.
"""

from __future__ import annotations

import io
from pathlib import Path

from claude_config_auditor.fixes import run_fix_flow
from claude_config_auditor.fixes.claude_md_archive import (
    LONG_SECTION_LINES,
    propose_claude_md_archive_fixes,
)
from claude_config_auditor.backup import revert_session
from claude_config_auditor.scanner import scan


def _claude_md(target: Path, content: str) -> Path:
    target.mkdir(exist_ok=True, parents=True)
    p = target / "CLAUDE.md"
    p.write_text(content, encoding="utf-8")
    return p


# --- Selection: nothing to do --------------------------------------------

def test_short_clean_claude_md_yields_no_proposals(tmp_path: Path):
    _claude_md(tmp_path / "p", (
        "# Project\n\n"
        "## Rules\n\n- Use type hints.\n- Run tests before pushing.\n"
    ))
    result = scan(tmp_path / "p")
    assert propose_claude_md_archive_fixes(result.claude_md_files) == []


def test_protected_headings_never_archive_even_when_long(tmp_path: Path):
    """A long `## Rules` section must NOT be selected — those are the
    load-bearing parts of CLAUDE.md by definition."""
    body = "\n".join(f"- rule {i}" for i in range(LONG_SECTION_LINES + 20))
    _claude_md(tmp_path / "p", f"# Project\n\n## Rules\n\n{body}\n")
    result = scan(tmp_path / "p")
    assert propose_claude_md_archive_fixes(result.claude_md_files) == []


# --- Selection: archivable by heading ------------------------------------

def _changelog_body() -> str:
    """A realistically-sized changelog body that clears the min-size guard."""
    entries = [
        f"- 2026-{m:02d}-01: release {m}. Lots of small fixes and "
        "improvements documented in the release notes for this month."
        for m in range(1, 9)
    ]
    return "\n".join(entries)


def _examples_body() -> str:
    """Realistic examples block — several worked examples, each a
    paragraph long, well above the 5-line / 150-token min."""
    return "\n\n".join(
        f"### Example {i}\n\nThe quick brown fox jumps over the lazy dog. "
        "Sample text here describes a worked example in enough detail "
        "to make the section meaningful."
        for i in range(1, 5)
    )


def test_changelog_heading_is_archived(tmp_path: Path):
    _claude_md(tmp_path / "p", (
        "# Project\n\n"
        "## Rules\n\n- Use type hints.\n\n"
        f"## Changelog\n\n{_changelog_body()}\n"
    ))
    result = scan(tmp_path / "p")
    [proposal] = propose_claude_md_archive_fixes(result.claude_md_files)
    # Proposal has two changes: archive create + source edit.
    assert len(proposal.changes) == 2
    paths = {c.path.name for c in proposal.changes}
    assert paths == {"CLAUDE.archive.md", "CLAUDE.md"}
    # Rationale must name the actual heading that triggered selection.
    assert "Changelog" in proposal.rationale


def test_examples_heading_is_archived(tmp_path: Path):
    _claude_md(tmp_path / "p", (
        "# Project\n\n"
        "## Rules\n\n- Foo.\n\n"
        f"## Examples\n\n{_examples_body()}\n"
    ))
    result = scan(tmp_path / "p")
    [proposal] = propose_claude_md_archive_fixes(result.claude_md_files)
    archive_change = next(c for c in proposal.changes
                          if c.path.name == "CLAUDE.archive.md")
    assert "Examples" in archive_change.after


# --- Conservatism: false-positive guards from real-world testing --------

def test_reference_section_with_load_bearing_body_is_not_archived(tmp_path: Path):
    """Real-world bug: a `## Engine Reference` section whose body says
    "Always check here before using any engine API" should NOT be
    archived. The heading keyword matches but the body is operational
    ("always", "before using") — load-bearing on every session.
    """
    _claude_md(tmp_path / "p", (
        "# Project\n\n"
        "## Engine Reference\n\n"
        "Version-pinned engine API snapshots. **Always check here before "
        "using any engine API** — the LLM's training data predates the "
        "pinned engine version.\n\n"
        "## Rules\n\n- Foo.\n"
    ))
    result = scan(tmp_path / "p")
    assert propose_claude_md_archive_fixes(result.claude_md_files) == []


def test_short_reference_stub_is_not_archived(tmp_path: Path):
    """A `## Reference` section that is just one line (a pointer to
    another file) is too small to archive. Reviewing the proposal
    costs more than the saved tokens."""
    _claude_md(tmp_path / "p", (
        "# Project\n\n"
        "## Engine Version Reference\n\n"
        "@docs/engine-reference/unity/VERSION.md\n\n"
        "## Rules\n\n- Foo.\n"
    ))
    result = scan(tmp_path / "p")
    assert propose_claude_md_archive_fixes(result.claude_md_files) == []


def test_body_with_must_phrase_blocks_archive(tmp_path: Path):
    """Operational language anywhere in the body protects the section."""
    body = "Version pinning matters here. " + ("Detail. " * 80)
    _claude_md(tmp_path / "p", (
        f"# Project\n\n"
        f"## Reference\n\n{body}\n**You must run setup before using.**\n\n"
        f"## Rules\n\n- Foo.\n"
    ))
    result = scan(tmp_path / "p")
    assert propose_claude_md_archive_fixes(result.claude_md_files) == []


# --- Selection: archivable by sheer length -------------------------------

def test_very_long_section_is_archived_even_without_keyword(tmp_path: Path):
    long_body = "\n".join(f"Detail {i}." for i in range(LONG_SECTION_LINES + 5))
    _claude_md(tmp_path / "p", (
        "# Project\n\n"
        f"## Background\n\n{long_body}\n\n"
        "## Rules\n\n- Foo.\n"
    ))
    result = scan(tmp_path / "p")
    proposals = propose_claude_md_archive_fixes(result.claude_md_files)
    assert proposals
    # The Background section moved; Rules did not.
    [proposal] = proposals
    archive_change = next(c for c in proposal.changes
                          if c.path.name == "CLAUDE.archive.md")
    assert "Background" in archive_change.after
    assert "## Rules" not in archive_change.after


# --- Source-file shape after the move ------------------------------------

def test_source_keeps_a_pointer_to_the_archive(tmp_path: Path):
    _claude_md(tmp_path / "p", (
        "# Project\n\n"
        "## Rules\n\n- Foo.\n\n"
        f"## Changelog\n\n{_changelog_body()}\n"
    ))
    result = scan(tmp_path / "p")
    [proposal] = propose_claude_md_archive_fixes(result.claude_md_files)
    source_change = next(c for c in proposal.changes
                          if c.path.name == "CLAUDE.md")
    # The heading line stays at its original level so the outline survives.
    assert "## Changelog" in source_change.after
    # And a pointer to the archive replaces the body.
    assert "CLAUDE.archive.md" in source_change.after
    # The original body content is gone from the source.
    assert "2026-01-01: release 1" not in source_change.after


def test_unrelated_sections_are_untouched(tmp_path: Path):
    _claude_md(tmp_path / "p", (
        "# Project\n\n"
        "## Rules\n\n- Use type hints.\n- Run tests.\n\n"
        f"## Changelog\n\n{_changelog_body()}\n"
    ))
    result = scan(tmp_path / "p")
    [proposal] = propose_claude_md_archive_fixes(result.claude_md_files)
    source_change = next(c for c in proposal.changes
                          if c.path.name == "CLAUDE.md")
    # Rules section preserved verbatim.
    assert "- Use type hints." in source_change.after
    assert "- Run tests." in source_change.after


# --- Code-fence safety ---------------------------------------------------

def test_headings_inside_code_fences_are_not_parsed(tmp_path: Path):
    """A `# comment` inside a fenced code block must not be mistaken
    for a Markdown heading. Otherwise we might "archive" a Python
    comment by accident."""
    _claude_md(tmp_path / "p", (
        "# Project\n\n"
        "## Rules\n\n"
        "```python\n"
        "# this looks like a heading but is a Python comment\n"
        "x = 1\n"
        "```\n\n"
        "Body continues here.\n"
    ))
    result = scan(tmp_path / "p")
    # No archivable sections → no proposals.
    assert propose_claude_md_archive_fixes(result.claude_md_files) == []


# --- End-to-end through fix flow -----------------------------------------

def test_proposal_applies_and_reverts_cleanly(tmp_path: Path):
    target = tmp_path / "p"
    source = _claude_md(target, (
        "# Project\n\n"
        "## Rules\n\n- Foo.\n\n"
        f"## Changelog\n\n{_changelog_body()}\n"
    ))
    archive = target / "CLAUDE.archive.md"
    src_before = source.read_text()

    result = scan(target)
    proposals = propose_claude_md_archive_fixes(result.claude_md_files)
    assert proposals

    outcome = run_fix_flow(
        target, proposals,
        prompter=lambda p, r: "y",
        out=io.StringIO(),
        use_color=False,
    )
    assert outcome.applied
    assert archive.exists()
    # Source still has Rules but no longer carries the changelog body.
    after_source = source.read_text()
    assert "- Foo." in after_source
    assert "release 1." not in after_source

    # Revert restores both sides exactly.
    revert_session(outcome.session_dir)
    assert not archive.exists()
    assert source.read_text() == src_before


def test_archive_is_appended_when_one_already_exists(tmp_path: Path):
    """If a CLAUDE.archive.md already exists from a previous run, new
    archived sections append rather than overwrite."""
    target = tmp_path / "p"
    _claude_md(target, (
        "# Project\n\n## Rules\n\n- Foo.\n\n"
        f"## Changelog\n\n{_changelog_body()}\n"
    ))
    archive = target / "CLAUDE.archive.md"
    archive.write_text("# CLAUDE archive\n\nOld content from a previous run.\n",
                       encoding="utf-8")

    result = scan(target)
    [proposal] = propose_claude_md_archive_fixes(result.claude_md_files)
    archive_change = next(c for c in proposal.changes
                          if c.path.name == "CLAUDE.archive.md")
    # is_new_file should be False (file existed); the after-content
    # must contain both the pre-existing text AND the new addition.
    assert archive_change.is_new_file is False
    assert "Old content from a previous run." in archive_change.after
    assert "Changelog" in archive_change.after

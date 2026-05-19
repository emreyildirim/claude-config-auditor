"""Tests for the Phase 2 fix-mode approval loop and applier.

Contracts (from PROJECT_BRIEF_PHASE2.md §3 and §5):
  - No change applied without explicit per-proposal approval.
  - "a" (all) batches future approvals; "q" (quit) stops the loop.
  - --dry-run shows everything, applies nothing, opens no backup.
  - Every applied proposal goes through a BackupSession.
  - Proposals targeting paths outside the audit target are refused.
  - Proposals cannot empty a file (Phase 2 never deletes).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from claude_config_auditor.fixes import Proposal, apply_proposals, run_fix_flow
from claude_config_auditor.fixes.flow import FileChange
from claude_config_auditor.backup import (
    BACKUP_DIR_NAME,
    load_session,
    revert_session,
)


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal target tree we can mutate freely."""
    target = tmp_path / "project"
    target.mkdir()
    (target / "CLAUDE.md").write_text("original guidance\n")
    (target / ".claude" / "agents").mkdir(parents=True)
    (target / ".claude" / "agents" / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: too short\n---\n\nbody\n"
    )
    return target


# --- Proposal / FileChange model -----------------------------------------

def test_filechange_refuses_to_empty_a_file(tmp_path: Path):
    """Phase 2 never deletes content. Empty `after` is a programmer
    error in the fix module — fail loud."""
    with pytest.raises(ValueError, match="never deletes"):
        FileChange(path=tmp_path / "f.md", before="something", after="")


def test_proposal_requires_at_least_one_change():
    with pytest.raises(ValueError, match="at least one"):
        Proposal(title="t", rationale="r", changes=[])


def test_filechange_label_is_relative_to_cwd_when_possible(tmp_path: Path,
                                                            monkeypatch):
    f = tmp_path / "x.md"
    monkeypatch.chdir(tmp_path)
    ch = FileChange(path=f, before="a", after="b")
    assert ch.label == "x.md"


def test_filechange_label_falls_back_to_absolute_for_outside_cwd(tmp_path: Path,
                                                                  monkeypatch):
    monkeypatch.chdir(tmp_path)
    ch = FileChange(path=Path("/tmp/somewhere/x.md"), before="a", after="b")
    assert ch.label.startswith("/")


def test_filechange_flags_new_file(tmp_path: Path):
    ch = FileChange(path=tmp_path / "new.md", before="", after="generated\n")
    assert ch.is_new_file is True


def test_proposal_edit_convenience_constructor(tmp_path: Path):
    """Proposal.edit(...) builds a single-change Proposal."""
    p = Proposal.edit(
        path=tmp_path / "x.md", before="a", after="b",
        title="t", rationale="r",
    )
    assert len(p.changes) == 1
    assert p.changes[0].before == "a"
    assert p.changes[0].after == "b"


def test_proposal_paths_returns_every_change_path(tmp_path: Path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    p = Proposal(
        title="multi", rationale="r",
        changes=[
            FileChange(a, "1", "2"),
            FileChange(b, "", "new"),
        ],
    )
    assert p.paths == [a, b]


# --- run_fix_flow: empty / no-op cases -----------------------------------

def test_run_with_no_proposals_prints_clean_message(tmp_path: Path):
    out = io.StringIO()
    outcome = run_fix_flow(
        tmp_path, [],
        prompter=lambda p, t: "y",
        out=out,
        use_color=False,
    )
    assert outcome.applied == []
    assert outcome.session_dir is None
    assert "Nothing to fix" in out.getvalue()


# --- run_fix_flow: approval branches -------------------------------------

def _prop(path: Path, *, title="edit", before="x\n", after="X\n",
          rationale="why") -> Proposal:
    return Proposal.edit(path=path, before=before, after=after,
                         title=title, rationale=rationale)


def test_yes_applies_and_writes_backup(tmp_path: Path):
    target = _setup_project(tmp_path)
    f = target / "CLAUDE.md"
    out = io.StringIO()

    outcome = run_fix_flow(
        target,
        [_prop(f, before=f.read_text(), after="rewritten\n")],
        prompter=lambda p, rendered: "y",
        out=out,
        use_color=False,
    )

    assert len(outcome.applied) == 1
    assert f.read_text() == "rewritten\n"
    assert outcome.session_dir is not None
    assert (outcome.session_dir / "manifest.json").is_file()


def test_no_skips_without_writing(tmp_path: Path):
    target = _setup_project(tmp_path)
    f = target / "CLAUDE.md"
    original = f.read_text()

    outcome = run_fix_flow(
        target,
        [_prop(f, before=original, after="rewritten\n")],
        prompter=lambda p, r: "n",
        out=io.StringIO(),
        use_color=False,
    )

    assert outcome.applied == []
    assert outcome.skipped and outcome.skipped[0].changes[0].path == f
    assert f.read_text() == original
    # No session should be created if nothing is applied.
    assert outcome.session_dir is None


def test_all_promotes_remaining_to_auto_yes(tmp_path: Path):
    target = _setup_project(tmp_path)
    f1 = target / "CLAUDE.md"
    f2 = target / ".claude" / "agents" / "reviewer.md"

    calls = []

    def prompter(p, rendered):
        calls.append(p.changes[0].path.name)
        return "a"  # first prompt says "yes to all"

    outcome = run_fix_flow(
        target,
        [
            _prop(f1, before=f1.read_text(), after="new f1\n"),
            _prop(f2, before=f2.read_text(), after="new f2\n"),
        ],
        prompter=prompter,
        out=io.StringIO(),
        use_color=False,
    )

    # The prompter was only called once (the first proposal). The
    # second was auto-approved.
    assert len(calls) == 1
    assert len(outcome.applied) == 2
    assert f1.read_text() == "new f1\n"
    assert f2.read_text() == "new f2\n"


def test_quit_stops_the_loop(tmp_path: Path):
    target = _setup_project(tmp_path)
    f1 = target / "CLAUDE.md"
    f2 = target / ".claude" / "agents" / "reviewer.md"
    before1, before2 = f1.read_text(), f2.read_text()

    outcome = run_fix_flow(
        target,
        [
            _prop(f1, before=before1, after="new f1\n"),
            _prop(f2, before=before2, after="new f2\n"),
        ],
        prompter=lambda p, r: "q",
        out=io.StringIO(),
        use_color=False,
    )

    assert outcome.quit_early is True
    assert outcome.applied == []
    assert f1.read_text() == before1
    assert f2.read_text() == before2


# --- dry-run --------------------------------------------------------------

def test_dry_run_changes_nothing_and_opens_no_session(tmp_path: Path):
    target = _setup_project(tmp_path)
    f = target / "CLAUDE.md"
    before = f.read_text()

    # Even with auto-yes the prompt should never be called in dry-run.
    def must_not_be_called(p, r):
        raise AssertionError("prompter must not run in --dry-run")

    outcome = run_fix_flow(
        target,
        [_prop(f, before=before, after="rewritten\n")],
        prompter=must_not_be_called,
        out=io.StringIO(),
        use_color=False,
        dry_run=True,
    )

    assert outcome.dry_run is True
    assert outcome.applied == []
    assert outcome.session_dir is None
    assert f.read_text() == before
    # And no backup dir should have been created in the target.
    assert not (target / BACKUP_DIR_NAME).exists()


def test_dry_run_still_renders_diff_to_output(tmp_path: Path):
    target = _setup_project(tmp_path)
    f = target / "CLAUDE.md"
    out = io.StringIO()

    run_fix_flow(
        target,
        [_prop(f, before=f.read_text(), after="REWRITTEN\n",
               title="Rewrite guidance", rationale="too long")],
        prompter=lambda p, r: "y",
        out=out,
        use_color=False,
        dry_run=True,
    )

    text = out.getvalue()
    assert "Rewrite guidance" in text
    assert "+REWRITTEN" in text
    assert "-original guidance" in text
    assert "dry-run" in text.lower()


# --- Containment ---------------------------------------------------------

def test_proposal_outside_target_is_refused(tmp_path: Path):
    target = _setup_project(tmp_path)
    outside = tmp_path / "elsewhere.md"
    outside.write_text("x")

    with pytest.raises(ValueError, match="outside"):
        apply_proposals(
            [_prop(outside, before="x", after="y")],
            target,
        )

    # Outside file should be untouched.
    assert outside.read_text() == "x"


def test_run_fix_rejects_non_directory_target(tmp_path: Path):
    not_a_dir = tmp_path / "f.md"
    not_a_dir.write_text("x")
    with pytest.raises(ValueError, match="target"):
        run_fix_flow(not_a_dir, [], prompter=lambda p, r: "y",
                     out=io.StringIO(), use_color=False)


# --- New files + revert end-to-end ---------------------------------------

def test_new_file_creation_is_reversible(tmp_path: Path):
    target = _setup_project(tmp_path)
    new = target / "CLAUDE.archive.md"
    assert not new.exists()

    outcome = run_fix_flow(
        target,
        [_prop(new, before="", after="archived content\n",
               title="Archive section")],
        prompter=lambda p, r: "y",
        out=io.StringIO(),
        use_color=False,
    )

    assert new.exists()
    assert outcome.session_dir is not None

    # Revert: the created file must go away.
    revert_session(outcome.session_dir)
    assert not new.exists()


def test_edit_is_reversible(tmp_path: Path):
    target = _setup_project(tmp_path)
    f = target / "CLAUDE.md"
    original = f.read_text()

    outcome = run_fix_flow(
        target,
        [_prop(f, before=original, after="rewritten\n")],
        prompter=lambda p, r: "y",
        out=io.StringIO(),
        use_color=False,
    )
    assert f.read_text() == "rewritten\n"

    revert_session(outcome.session_dir)
    assert f.read_text() == original


# --- Manifest content ----------------------------------------------------

def test_session_manifest_records_each_applied_change(tmp_path: Path):
    target = _setup_project(tmp_path)
    f1 = target / "CLAUDE.md"
    new = target / ".claude" / "agents" / "new-agent.md"

    outcome = run_fix_flow(
        target,
        [
            _prop(f1, before=f1.read_text(), after="rewritten\n"),
            _prop(new, before="", after="---\nname: x\n---\n", title="create"),
        ],
        prompter=lambda p, r: "y",
        out=io.StringIO(),
        use_color=False,
    )

    payload = load_session(outcome.session_dir)
    paths = {f["relative_path"] for f in payload["files"]}
    assert paths == {"CLAUDE.md", ".claude/agents/new-agent.md"}

    # The created file's manifest entry should mark existed_before=False.
    new_entry = next(f for f in payload["files"]
                     if f["relative_path"].endswith("new-agent.md"))
    assert new_entry["existed_before"] is False


# --- Multi-change proposals (e.g. archive moves) -------------------------

def test_multi_change_proposal_applies_all_changes_atomically(tmp_path: Path):
    """A single Proposal with two FileChange entries (e.g. an archive
    operation: source edit + new archive file) must either apply both
    changes or none — a single yes covers the whole proposal."""
    target = _setup_project(tmp_path)
    source = target / "CLAUDE.md"
    archive = target / "CLAUDE.archive.md"
    source_before = source.read_text()

    p = Proposal(
        title="Archive a section",
        rationale="Moves a section out of CLAUDE.md into a sibling file.",
        changes=[
            FileChange(path=archive, before="",
                       after="# Archived\n\n" + source_before),
            FileChange(path=source, before=source_before,
                       after="# CLAUDE.md\nSee CLAUDE.archive.md.\n"),
        ],
        source_code="HLT001",
    )

    outcome = run_fix_flow(
        target, [p],
        prompter=lambda p, r: "y",
        out=io.StringIO(),
        use_color=False,
    )

    assert len(outcome.applied) == 1
    assert archive.read_text().startswith("# Archived")
    assert "See CLAUDE.archive.md" in source.read_text()

    # Revert restores BOTH: archive deleted, source back to original.
    revert_session(outcome.session_dir)
    assert not archive.exists()
    assert source.read_text() == source_before


def test_multi_change_proposal_rendered_lists_each_file(tmp_path: Path):
    """The terminal preview for a multi-change proposal should mention
    every affected file before showing the diffs."""
    target = _setup_project(tmp_path)
    source = target / "CLAUDE.md"
    archive = target / "CLAUDE.archive.md"
    src_before = source.read_text()

    p = Proposal(
        title="Archive section",
        rationale="r",
        changes=[
            FileChange(path=archive, before="", after="archived\n"),
            FileChange(path=source, before=src_before, after="trimmed\n"),
        ],
    )

    out = io.StringIO()
    run_fix_flow(target, [p],
                 prompter=lambda p, r: "n",
                 out=out, use_color=False)
    text = out.getvalue()
    assert "affects 2 file(s)" in text
    assert "CLAUDE.archive.md" in text
    assert "CLAUDE.md" in text

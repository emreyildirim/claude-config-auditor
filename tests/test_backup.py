"""Tests for the Phase 2 backup / revert safety net.

The contract (from PROJECT_BRIEF_PHASE2.md §3 and §5.4):
  - No silent change to user files.
  - Every change reversible.
  - Drift detected via SHA-256, never silently overwritten.
  - Files created by fix are deleted on revert.
  - Sessions are immutable once closed.
  - Best-effort atomic per file (temp + rename).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_config_auditor import __version__
from claude_config_auditor.backup import (
    BACKUP_DIR_NAME,
    MANIFEST_FILENAME,
    MANIFEST_VERSION,
    BackupError,
    DriftError,
    list_sessions,
    load_session,
    open_session,
    revert_session,
)


# --- Session creation -------------------------------------------------------

def test_open_session_creates_directories(tmp_path: Path):
    s = open_session(tmp_path, tool_version=__version__)
    assert s.session_dir.is_dir()
    assert s.session_id in str(s.session_dir)
    assert (tmp_path / BACKUP_DIR_NAME / "backups").is_dir()


def test_open_session_rejects_non_directory(tmp_path: Path):
    file = tmp_path / "not_a_dir.txt"
    file.write_text("x")
    with pytest.raises(BackupError):
        open_session(file, tool_version=__version__)


def test_open_session_id_is_unique_per_call(tmp_path: Path):
    a = open_session(tmp_path, tool_version=__version__)
    b = open_session(tmp_path, tool_version=__version__)
    assert a.session_id != b.session_id


def test_custom_backup_root_is_honoured(tmp_path: Path):
    custom = tmp_path / "elsewhere"
    target = tmp_path / "project"
    target.mkdir()
    s = open_session(target, tool_version=__version__, backup_root=custom)
    assert custom in s.session_dir.parents
    # Default location should not have been created.
    assert not (target / BACKUP_DIR_NAME).exists()


# --- Snapshot behaviour -----------------------------------------------------

def test_snapshot_copies_existing_file_and_records_sha(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    f = target / "CLAUDE.md"
    f.write_text("original content")

    s = open_session(target, tool_version=__version__)
    entry = s.snapshot(f)

    assert entry.relative_path == "CLAUDE.md"
    assert entry.existed_before is True
    assert len(entry.sha256_before) == 64
    backup_file = s.session_dir / entry.backup_relative_path
    assert backup_file.is_file()
    assert backup_file.read_text() == "original content"


def test_snapshot_of_missing_file_records_did_not_exist(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    f = target / "new-file.md"
    # Don't create the file — fix is going to create it.

    s = open_session(target, tool_version=__version__)
    entry = s.snapshot(f)

    assert entry.existed_before is False
    assert entry.sha256_before == ""
    # No backup file is written for non-existent originals.
    assert not (s.session_dir / entry.backup_relative_path).exists()


def test_snapshot_is_idempotent_within_session(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    f = target / "CLAUDE.md"
    f.write_text("content")

    s = open_session(target, tool_version=__version__)
    e1 = s.snapshot(f)
    e2 = s.snapshot(f)

    assert len(s.entries) == 1
    assert e1 is e2


def test_snapshot_refuses_paths_outside_target(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    outside = tmp_path / "other-place.md"
    outside.write_text("x")

    s = open_session(target, tool_version=__version__)
    with pytest.raises(BackupError, match="outside target_root"):
        s.snapshot(outside)


def test_snapshot_after_close_raises(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    f = target / "CLAUDE.md"
    f.write_text("x")

    s = open_session(target, tool_version=__version__)
    s.close()
    with pytest.raises(BackupError, match="closed"):
        s.snapshot(f)


# --- Manifest -------------------------------------------------------------

def test_close_writes_a_well_formed_manifest(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    f = target / "CLAUDE.md"
    f.write_text("c")

    s = open_session(target, tool_version=__version__)
    s.snapshot(f)
    manifest_path = s.close()

    assert manifest_path.name == MANIFEST_FILENAME
    payload = json.loads(manifest_path.read_text())
    assert payload["manifest_version"] == MANIFEST_VERSION
    assert payload["session_id"] == s.session_id
    assert payload["tool_version"] == __version__
    assert len(payload["files"]) == 1
    assert payload["files"][0]["relative_path"] == "CLAUDE.md"


def test_load_session_round_trip(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    (target / "a.md").write_text("a")
    (target / "b.md").write_text("b")
    s = open_session(target, tool_version=__version__)
    s.snapshot(target / "a.md")
    s.snapshot(target / "b.md")
    s.close()

    payload = load_session(s.session_dir)
    paths = {f["relative_path"] for f in payload["files"]}
    assert paths == {"a.md", "b.md"}


def test_load_session_rejects_unknown_version(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    s = open_session(target, tool_version=__version__)
    s.close()
    # Corrupt the manifest with a future version.
    payload = json.loads(s.manifest_path.read_text())
    payload["manifest_version"] = MANIFEST_VERSION + 1
    s.manifest_path.write_text(json.dumps(payload))
    with pytest.raises(BackupError, match="version"):
        load_session(s.session_dir)


# --- Listing --------------------------------------------------------------

def test_list_sessions_returns_oldest_first(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    a = open_session(target, tool_version=__version__)
    a.close()
    b = open_session(target, tool_version=__version__)
    b.close()
    found = list_sessions(target)
    assert len(found) == 2
    # Session IDs sort lexicographically by creation timestamp.
    assert found[0].name <= found[1].name


def test_list_sessions_is_empty_when_no_backups(tmp_path: Path):
    assert list_sessions(tmp_path) == []


# --- Abort ----------------------------------------------------------------

def test_abort_deletes_session_directory(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    s = open_session(target, tool_version=__version__)
    (target / "f.md").write_text("x")
    s.snapshot(target / "f.md")
    assert s.session_dir.is_dir()
    s.abort()
    assert not s.session_dir.exists()


def test_abort_after_close_raises(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    s = open_session(target, tool_version=__version__)
    s.close()
    with pytest.raises(BackupError, match="cannot abort"):
        s.abort()


# --- Revert: happy path ---------------------------------------------------

def test_revert_restores_pre_change_content(tmp_path: Path):
    """Models the canonical fix flow: snapshot → modify → close →
    (later) revert. Revert must restore the original content."""
    target = tmp_path / "project"
    target.mkdir()
    f = target / "CLAUDE.md"
    f.write_text("original")

    s = open_session(target, tool_version=__version__)
    s.snapshot(f)
    # Fix modifies the file before close() captures the after-hash.
    f.write_text("MODIFIED BY FIX")
    s.close()

    touched = revert_session(s.session_dir)
    assert f.read_text() == "original"
    assert f in touched


def test_revert_deletes_files_created_by_fix(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    new_file = target / "archived.md"
    # File doesn't exist yet.

    s = open_session(target, tool_version=__version__)
    s.snapshot(new_file)  # records existed_before=False
    # Fix creates the file before close() records the after-state.
    new_file.write_text("content generated by fix")
    s.close()
    assert new_file.exists()

    revert_session(s.session_dir)
    assert not new_file.exists()


def test_revert_works_on_nested_paths(tmp_path: Path):
    target = tmp_path / "project"
    nested = target / ".claude" / "agents"
    nested.mkdir(parents=True)
    f = nested / "reviewer.md"
    f.write_text("original")

    s = open_session(target, tool_version=__version__)
    s.snapshot(f)
    f.write_text("modified by fix")
    s.close()

    revert_session(s.session_dir)
    assert f.read_text() == "original"


# --- Revert: drift detection ---------------------------------------------

def test_revert_refuses_to_overwrite_drifted_file(tmp_path: Path):
    """Drift: user manually edited the fix's OUTPUT between apply and
    revert. We must not silently overwrite those edits."""
    target = tmp_path / "project"
    target.mkdir()
    f = target / "CLAUDE.md"
    f.write_text("original")

    s = open_session(target, tool_version=__version__)
    s.snapshot(f)
    f.write_text("fix-produced content")
    s.close()

    # User edits the fix's output by hand.
    f.write_text("then the user changed it again manually")

    with pytest.raises(DriftError, match="drift"):
        revert_session(s.session_dir)

    # File must be untouched.
    assert f.read_text() == "then the user changed it again manually"


def test_revert_force_overrides_drift_check(tmp_path: Path):
    """Force flag lets the user explicitly accept the destructive revert."""
    target = tmp_path / "project"
    target.mkdir()
    f = target / "CLAUDE.md"
    f.write_text("original")

    s = open_session(target, tool_version=__version__)
    s.snapshot(f)
    f.write_text("fix-produced content")
    s.close()
    f.write_text("drifted by user")

    revert_session(s.session_dir, force=True)
    assert f.read_text() == "original"


# --- Revert: error cases -------------------------------------------------

def test_revert_fails_loudly_when_backup_file_is_missing(tmp_path: Path):
    target = tmp_path / "project"
    target.mkdir()
    f = target / "CLAUDE.md"
    f.write_text("original")

    s = open_session(target, tool_version=__version__)
    s.snapshot(f)
    f.write_text("fixed")
    s.close()
    # Corrupt the session by removing the backup file. The on-disk
    # state still matches sha_after, so drift check passes; then the
    # missing-backup check trips.
    (s.session_dir / "files" / "CLAUDE.md").unlink()

    with pytest.raises(BackupError, match="backup file missing"):
        revert_session(s.session_dir)

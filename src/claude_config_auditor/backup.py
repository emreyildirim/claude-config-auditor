"""Backup / revert safety net for Phase 2 `fix` operations.

Design contract (from Phase 2 brief §3 and §5.4):

1. No file is ever modified by `fix` before the original is snapshotted
   to disk and recorded in a session manifest.
2. Backups live inside the target tree at `.claude-config-auditor/backups/<id>/`
   so they are discoverable with `ls -a`, readable by the user, and easy
   to gitignore. Path can be overridden.
3. Every snapshot records a SHA-256 of the original. Revert refuses to
   overwrite a file whose on-disk content has drifted from that hash
   between backup and revert — the user's out-of-band edits are never
   silently destroyed.
4. Revert is atomic per file: write to a temp sibling, then rename.
5. Sessions are immutable. A session is created, snapshots are added,
   then `close()` finalises it by writing the manifest. After that the
   session is read-only.

This module is intentionally `fix`-mode-only. The Phase 1 `audit` mode
never imports it and never touches `.claude-config-auditor/` itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Where session directories live, relative to the target root.
BACKUP_DIR_NAME = ".claude-config-auditor"
SESSIONS_SUBDIR = "backups"
MANIFEST_FILENAME = "manifest.json"

# Internal manifest schema version. Bump if the JSON format changes in a
# non-additive way so old sessions stay revertable with a clear error.
MANIFEST_VERSION = 1


class BackupError(Exception):
    """Anything that prevents a safe snapshot or revert."""


class DriftError(BackupError):
    """The on-disk file's hash no longer matches what we snapshotted —
    something edited it between backup time and revert time. Aborts
    rather than silently overwriting the user's work."""


@dataclass
class SnapshotEntry:
    """One file inside a session's manifest."""

    relative_path: str          # path relative to target_root
    backup_relative_path: str   # path of the backup, relative to session dir
    sha256_before: str          # hash of the file at snapshot time
    sha256_after: str           # hash recorded at close() — i.e. the
                                # fix's output. Drift detection on revert
                                # compares the current on-disk file to
                                # this, not to sha256_before.
    existed_before: bool        # False for "the fix creates this file"
    exists_after: bool          # False if the fix's net effect is to leave
                                # the file absent (currently only happens
                                # if the fix never wrote a created file)


@dataclass
class Session:
    """An in-progress backup session.

    Created by `open_session`, populated by `snapshot()`, finalised by
    `close()`. After close, treat as read-only. To revert, use
    `revert_session()` against the session_id.
    """

    session_id: str
    target_root: Path
    session_dir: Path
    created_at: str
    tool_version: str
    entries: list[SnapshotEntry] = field(default_factory=list)
    _closed: bool = False
    # Track relative paths already snapshotted so we don't double-snapshot
    # within the same session.
    _seen: set[str] = field(default_factory=set, repr=False)

    @property
    def files_dir(self) -> Path:
        return self.session_dir / "files"

    @property
    def manifest_path(self) -> Path:
        return self.session_dir / MANIFEST_FILENAME

    def snapshot(self, path: Path) -> SnapshotEntry:
        """Record the current state of `path` so the fix can safely
        modify it. `path` may or may not exist (e.g. fix is creating a
        new file — we still record "did not exist before" so revert
        can delete it).
        """
        if self._closed:
            raise BackupError("session is closed; open a new one")

        abs_path = path.resolve()
        try:
            rel = abs_path.relative_to(self.target_root.resolve())
        except ValueError as exc:
            raise BackupError(
                f"path {abs_path} is outside target_root {self.target_root}"
            ) from exc
        rel_str = str(rel)

        if rel_str in self._seen:
            # Idempotent: snapshotting the same file twice in one session
            # is a no-op, not an error.
            return next(e for e in self.entries if e.relative_path == rel_str)

        backup_rel = Path("files") / rel
        backup_abs = self.session_dir / backup_rel
        backup_abs.parent.mkdir(parents=True, exist_ok=True)

        if abs_path.exists():
            sha = _sha256_of(abs_path)
            shutil.copy2(abs_path, backup_abs)
            existed = True
        else:
            sha = ""
            existed = False

        entry = SnapshotEntry(
            relative_path=rel_str,
            backup_relative_path=str(backup_rel),
            sha256_before=sha,
            sha256_after="",       # filled in by close()
            existed_before=existed,
            exists_after=False,    # filled in by close()
        )
        self.entries.append(entry)
        self._seen.add(rel_str)
        return entry

    def close(self) -> Path:
        """Finalise the session by writing the manifest. Returns the
        manifest path. After close, the session is read-only.

        Before writing, each entry's `sha256_after` and `exists_after`
        are recorded by re-reading the file from disk. This is what
        drift detection compares against on revert — the fix's output,
        not the pre-fix state.
        """
        if self._closed:
            return self.manifest_path

        for entry in self.entries:
            current = (self.target_root / entry.relative_path).resolve()
            if current.exists():
                entry.exists_after = True
                entry.sha256_after = _sha256_of(current)
            else:
                entry.exists_after = False
                entry.sha256_after = ""

        payload = {
            "manifest_version": MANIFEST_VERSION,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "tool_version": self.tool_version,
            "target_root": str(self.target_root),
            "files": [
                {
                    "relative_path": e.relative_path,
                    "backup_relative_path": e.backup_relative_path,
                    "sha256_before": e.sha256_before,
                    "sha256_after": e.sha256_after,
                    "existed_before": e.existed_before,
                    "exists_after": e.exists_after,
                }
                for e in self.entries
            ],
        }
        # Atomic write: tmp file then rename, so a crash mid-write leaves
        # either the old manifest (none) or the complete one.
        tmp = self.manifest_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.manifest_path)
        self._closed = True
        return self.manifest_path

    def abort(self) -> None:
        """Discard this in-progress session — useful when the fix flow
        decides not to proceed. Deletes the on-disk session directory."""
        if self._closed:
            raise BackupError("cannot abort a closed session — use revert")
        if self.session_dir.exists():
            shutil.rmtree(self.session_dir)


def open_session(target_root: Path, tool_version: str,
                 backup_root: Path | None = None) -> Session:
    """Start a new backup session. Nothing is written until the first
    `snapshot()` or `close()`. The session_id is timestamp + short uuid
    so sessions sort lexicographically by creation time."""
    target = target_root.resolve()
    if not target.is_dir():
        raise BackupError(f"target is not a directory: {target}")

    sessions_root = (backup_root or (target / BACKUP_DIR_NAME)) / SESSIONS_SUBDIR
    sessions_root.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    sid = now.strftime("%Y-%m-%dT%H-%M-%SZ") + "-" + uuid.uuid4().hex[:6]
    session_dir = sessions_root / sid
    session_dir.mkdir()

    return Session(
        session_id=sid,
        target_root=target,
        session_dir=session_dir,
        created_at=now.isoformat(),
        tool_version=tool_version,
    )


def load_session(session_dir: Path) -> dict[str, Any]:
    """Read a session's manifest. Raises BackupError if missing or in
    an unknown schema version."""
    manifest_path = session_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise BackupError(f"no manifest at {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = payload.get("manifest_version")
    if version != MANIFEST_VERSION:
        raise BackupError(
            f"manifest version {version} is not supported by this tool "
            f"(expected {MANIFEST_VERSION})"
        )
    return payload


def list_sessions(target_root: Path,
                  backup_root: Path | None = None) -> list[Path]:
    """Return paths of every backup session found, oldest first."""
    sessions_root = (backup_root or (target_root / BACKUP_DIR_NAME)) / SESSIONS_SUBDIR
    if not sessions_root.is_dir():
        return []
    return sorted(p for p in sessions_root.iterdir() if p.is_dir())


def revert_session(session_dir: Path, *, force: bool = False) -> list[Path]:
    """Restore every file in the session to its pre-fix state.

    Returns the list of paths actually touched. Drift detection: each
    file's current content must match the SHA we recorded at close()
    (i.e. the fix's output). If a file has been edited after close(),
    we refuse to overwrite it unless `force=True`. Files the fix
    created (where existed_before=False) are deleted rather than
    restored.

    Per-file atomic (temp + rename), not atomic across files. Re-running
    revert is safe because each file's check is independent.
    """
    payload = load_session(session_dir)
    target_root = Path(payload["target_root"])
    touched: list[Path] = []

    for entry in payload["files"]:
        rel = entry["relative_path"]
        backup_rel = entry["backup_relative_path"]
        sha_after = entry["sha256_after"]
        existed_before = entry["existed_before"]
        exists_after = entry.get("exists_after", True)

        original = (target_root / rel).resolve()

        # Drift detection: current state must match the fix's output
        # exactly. If the user edited the fix's output between apply
        # and revert, abort — don't silently destroy their edits.
        if exists_after and original.exists():
            current_sha = _sha256_of(original)
            if current_sha != sha_after and not force:
                raise DriftError(
                    f"file has drifted since fix applied: {original} "
                    f"(expected sha {sha_after[:8] or '<none>'}…, "
                    f"found {current_sha[:8]}…). "
                    "Use force=True to overwrite anyway."
                )
        elif exists_after and not original.exists() and not force:
            # The fix left a file there; now it is gone. Recreating it
            # silently could surprise the user.
            raise DriftError(
                f"file expected to exist no longer present: {original}. "
                "Use force=True to recreate from backup."
            )

        # Files the fix created get deleted on revert.
        if not existed_before:
            if original.exists():
                original.unlink()
                touched.append(original)
            continue

        # File existed before fix; restore from backup.
        backup_path = session_dir / backup_rel
        if not backup_path.is_file():
            raise BackupError(f"backup file missing: {backup_path}")

        original.parent.mkdir(parents=True, exist_ok=True)
        tmp = original.with_suffix(original.suffix + ".cca-restore.tmp")
        shutil.copy2(backup_path, tmp)
        os.replace(tmp, original)
        touched.append(original)

    return touched


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

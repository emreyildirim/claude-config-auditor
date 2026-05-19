"""The fix-mode approval loop and applier.

Per PROJECT_BRIEF_PHASE2.md §3:
  - No change applied without explicit approval.
  - Every change reversible (this layer opens a BackupSession around
    the apply step).
  - The tool never deletes files; proposals can edit existing files
    and create new ones, but never erase.

Per §5.5 the same loop drives `--dry-run`: every proposal is rendered
exactly as for a real run, the prompt is replaced with a notice that
nothing will be applied, and the backup session is never opened.

Concrete proposals (CLAUDE.md archiving, agent-description rewrites,
etc.) are built in sibling modules and handed to `run_fix_flow` as a
sequence of `Proposal` objects. This module knows nothing about *what*
is being changed — only the shape of the change and the user-facing
flow around it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Callable, Iterable

from claude_config_auditor import __version__
from claude_config_auditor.backup import Session, open_session
from claude_config_auditor.diff import make_diff, render_diff, summarise_diff


@dataclass
class Proposal:
    """One concrete change a fix module wants to apply.

    A proposal can:
      - edit an existing file (before != "", after != "")
      - create a new file   (before == "", after != "")

    It cannot delete a file. The brief forbids deletion outright; if a
    fix wants to "move" content somewhere else, it emits two proposals
    (one create, one edit) inside the same fix run.

    Attributes:
        path:    absolute path the proposal targets. Must be inside the
                 audit target — the applier verifies this.
        before:  current content of `path` ("" if the file does not exist)
        after:   desired content of `path` ("" is forbidden — fixes do
                 not delete files)
        title:   short, human-readable name of the change ("Rewrite
                 agent description", "Archive CLAUDE.md section")
        rationale: 1–3 sentence "why" shown alongside the diff
        source_code: optional finding code that produced this proposal
                 (e.g. "AGT008") — lets the report tie a fix back to
                 the audit finding the user already saw
    """

    path: Path
    before: str
    after: str
    title: str
    rationale: str
    source_code: str | None = None

    def __post_init__(self) -> None:
        if self.after == "":
            raise ValueError(
                "proposals cannot leave a file empty — Phase 2 never "
                "deletes content. Build two proposals if you mean to "
                "archive."
            )

    @property
    def is_new_file(self) -> bool:
        return self.before == ""

    @property
    def label(self) -> str:
        """The label used in the diff header. Relative to the user's
        cwd if possible, otherwise absolute."""
        try:
            return str(self.path.relative_to(Path.cwd()))
        except ValueError:
            return str(self.path)


# A prompter takes the rendered proposal block and returns the user's
# answer as one of: "y" (yes), "n" (no), "a" (yes-to-all),
# "q" (quit). Tests can supply a deterministic prompter; the CLI wires
# in a real stdin reader.
Prompter = Callable[[Proposal, str], str]
_YES, _NO, _ALL, _QUIT = "y", "n", "a", "q"


@dataclass
class FixOutcome:
    """Summary of what a fix run did. Useful for tests and for the
    end-of-run report the CLI prints."""

    total_proposed: int = 0
    applied: list[Proposal] = field(default_factory=list)
    skipped: list[Proposal] = field(default_factory=list)
    session_dir: Path | None = None
    dry_run: bool = False
    quit_early: bool = False


def run_fix_flow(
    target: Path,
    proposals: Iterable[Proposal],
    *,
    prompter: Prompter,
    out: IO[str],
    use_color: bool = True,
    dry_run: bool = False,
    backup_root: Path | None = None,
) -> FixOutcome:
    """Drive the approval loop. Returns a FixOutcome describing what
    was applied or skipped.

    The flow:
      1. For each proposal, render its diff + rationale to `out`.
      2. If dry-run, mark as "would apply" and move on.
      3. Otherwise call `prompter(proposal, rendered_block)` and act on
         the answer. "a" upgrades all subsequent prompts to auto-yes.
         "q" stops the loop, applying nothing else.
      4. If any proposals were accepted, open a BackupSession and apply
         them under it. The session is closed even if an apply step
         fails (best-effort partial recovery).
    """
    target = target.resolve()
    if not target.is_dir():
        raise ValueError(f"target is not a directory: {target}")

    proposals = list(proposals)
    outcome = FixOutcome(total_proposed=len(proposals), dry_run=dry_run)

    if not proposals:
        out.write("No proposed changes. Nothing to fix.\n")
        return outcome

    auto_yes = False
    accepted: list[Proposal] = []

    for i, p in enumerate(proposals, 1):
        rendered = _render_proposal(p, i, len(proposals), use_color=use_color)
        out.write(rendered)

        if dry_run:
            out.write(_dim("  (dry-run — not applied)\n\n", use_color))
            continue

        if auto_yes:
            answer = _YES
            out.write(_dim("  (auto-approved)\n", use_color))
        else:
            answer = prompter(p, rendered).strip().lower()

        if answer == _QUIT:
            outcome.quit_early = True
            out.write(_dim("Quit. No further proposals considered.\n\n",
                           use_color))
            break
        if answer == _ALL:
            auto_yes = True
            answer = _YES
        if answer == _YES:
            accepted.append(p)
        else:
            outcome.skipped.append(p)

    if dry_run or not accepted:
        return outcome

    # Apply the accepted set under one backup session. If any step fails
    # the session is closed (so users can revert) before the exception
    # propagates.
    session = open_session(target, tool_version=__version__,
                           backup_root=backup_root)
    outcome.session_dir = session.session_dir
    try:
        for p in accepted:
            apply_proposal(p, session, target)
            outcome.applied.append(p)
    finally:
        session.close()

    out.write(
        f"\nApplied {len(outcome.applied)} change(s). "
        f"Backup written to {session.session_dir}\n"
    )
    return outcome


def apply_proposals(
    proposals: Iterable[Proposal],
    target: Path,
    *,
    backup_root: Path | None = None,
) -> FixOutcome:
    """Apply every proposal without any prompting. Used by tests and
    eventually by `--yes`-flavoured non-interactive modes. The user-
    facing CLI does NOT call this — every fix must go through the
    approval loop per brief §3."""
    target = target.resolve()
    proposals = list(proposals)
    outcome = FixOutcome(total_proposed=len(proposals))
    if not proposals:
        return outcome

    session = open_session(target, tool_version=__version__,
                           backup_root=backup_root)
    outcome.session_dir = session.session_dir
    try:
        for p in proposals:
            apply_proposal(p, session, target)
            outcome.applied.append(p)
    finally:
        session.close()
    return outcome


def apply_proposal(p: Proposal, session: Session, target: Path) -> None:
    """Apply a single proposal under an open backup session.

    Snapshots the target file (recording existed_before either way), then
    writes the new content via temp + rename for per-file atomicity.
    The session captures sha_after when `close()` is later called.
    """
    abs_path = p.path.resolve()
    try:
        abs_path.relative_to(target.resolve())
    except ValueError as exc:
        raise ValueError(
            f"proposal target {abs_path} is outside audit target {target}"
        ) from exc

    session.snapshot(abs_path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = abs_path.with_suffix(abs_path.suffix + ".cca-fix.tmp")
    tmp.write_text(p.after, encoding="utf-8")
    tmp.replace(abs_path)


# --- Rendering ------------------------------------------------------------

def _render_proposal(p: Proposal, idx: int, total: int,
                     *, use_color: bool) -> str:
    """One proposal block: header + rationale + diff."""
    header = f"[{idx}/{total}] {p.title}"
    if p.source_code:
        header += f"  ({p.source_code})"
    sep = "─" * max(8, min(len(header), 78))

    parts = [
        _bold(header, use_color) + "\n",
        _dim(sep, use_color) + "\n",
        f"  file:      {p.label}\n",
        f"  rationale: {p.rationale}\n",
    ]

    diff_text = make_diff(p.label, p.before, p.after)
    if diff_text:
        adds, rems = summarise_diff(diff_text)
        parts.append(
            _dim(f"  change:    +{adds} / -{rems} line(s)\n", use_color)
        )
        parts.append("\n")
        parts.append(render_diff(diff_text, use_color=use_color))
    parts.append("\n")
    return "".join(parts)


def _bold(s: str, use_color: bool) -> str:
    return f"\033[1m{s}\033[0m" if use_color else s


def _dim(s: str, use_color: bool) -> str:
    return f"\033[2m{s}\033[0m" if use_color else s

"""Render before/after diffs for fix suggestions.

Phase 2 brief §5.1: "her öneri kullanıcıya diff (önce/sonra farkı)
olarak gösterilir". Every fix proposal — whether it edits a CLAUDE.md
section, rewrites an agent description, or moves text into an archive
file — flows through this module so the user always sees the same
shape of preview before deciding.

Two API entry points:

  make_diff(label, before, after)   -> unified-diff text (uncoloured)
  render_diff(diff_text, use_color) -> the same text with ANSI colours
                                        for human terminals

Built on `difflib.unified_diff` from the stdlib — no extra dependency.

Conventions:
  - The label is a short identifier of what is being diffed, typically
    a relative path. It appears in both the header and the file labels.
  - `before == ""` and `after != ""` is rendered as a NEW FILE diff so
    the user sees the full file content as additions. Mirrors how
    `git diff /dev/null new_file.md` reads.
  - `before != ""` and `after == ""` is rendered as a removal — but
    Phase 2 never deletes files in practice; this is here for
    completeness and dry-run preview of "remove this section".
  - A no-op diff (before == after) returns "" so callers can skip
    presenting it.
"""

from __future__ import annotations

import difflib
import os


# ANSI escape codes for terminal colouring.
_RED = "\033[31m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def make_diff(label: str, before: str, after: str,
              context: int = 3) -> str:
    """Return a unified-diff string for the change from `before` to
    `after`. Empty if nothing changed.

    `label` is used for both `--- a/<label>` and `+++ b/<label>` lines
    (and `/dev/null` if a side is empty). `context` is the number of
    unchanged surrounding lines to include.
    """
    if before == after:
        return ""

    from_label = f"a/{label}" if before else "/dev/null"
    to_label = f"b/{label}" if after else "/dev/null"

    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=from_label,
        tofile=to_label,
        n=context,
    )
    return "".join(diff)


def render_diff(diff_text: str, *, use_color: bool = True) -> str:
    """Return the diff with ANSI colours suitable for a terminal.

    `use_color=False` leaves the text untouched. NO_COLOR support is
    handled at the CLI layer (see cli._should_use_color) — this function
    just trusts the boolean it receives.
    """
    if not diff_text:
        return ""
    if not use_color:
        return diff_text

    out_lines = []
    for line in diff_text.splitlines(keepends=True):
        # Strip a trailing newline so the reset escape lands on the same
        # logical line, then put the newline back. Without this, the
        # reset bleeds onto the next line and a pipe-truncation can
        # leave the terminal in a coloured state.
        content, nl = (line[:-1], line[-1]) if line.endswith("\n") else (line, "")
        if content.startswith("+++") or content.startswith("---"):
            out_lines.append(f"{_BOLD}{content}{_RESET}{nl}")
        elif content.startswith("@@"):
            out_lines.append(f"{_CYAN}{content}{_RESET}{nl}")
        elif content.startswith("+"):
            out_lines.append(f"{_GREEN}{content}{_RESET}{nl}")
        elif content.startswith("-"):
            out_lines.append(f"{_RED}{content}{_RESET}{nl}")
        else:
            out_lines.append(line)
    return "".join(out_lines)


def summarise_diff(diff_text: str) -> tuple[int, int]:
    """Return (additions, removals) line counts for a unified-diff.

    Headers (---, +++) are excluded so the counts mean "actual content
    changes" rather than diff metadata. Useful for one-line summaries
    like "agent.md: +12 / -4 lines".
    """
    adds = 0
    rems = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            adds += 1
        elif line.startswith("-"):
            rems += 1
    return adds, rems

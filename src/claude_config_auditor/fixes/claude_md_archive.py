"""Propose moving low-priority CLAUDE.md sections into a sibling archive.

Phase 2 brief §5.2: an oversized CLAUDE.md eats context-window space
on every session. This module looks at each over-budget CLAUDE.md, picks
candidate sections that "are probably not needed every session", and
emits a single Proposal whose two FileChange entries together perform
the move:

  1. Create or extend  CLAUDE.archive.md  (sibling of the source)
  2. Edit              CLAUDE.md          to remove those sections and
                                          leave a one-line pointer to
                                          the archive.

Brief §9 is explicit: candidate detection must be "açıklanabilir" —
the user should be able to see *why* a section was singled out, and
the tool should err on the side of NOT moving things. Borderline
sections stay put.

Candidate heuristics, in order:

  1. The section is unusually long (≥ LONG_SECTION_LINES OR
     ≥ LONG_SECTION_TOKENS estimated tokens).
  2. The section's heading matches a known "reference / log /
     changelog / examples" pattern that strongly suggests it does not
     need to load on every session.

Sections that look like project rules / conventions / "don't"-lists
are NEVER candidates; those are the load-bearing parts of CLAUDE.md.

This module emits at most one Proposal per CLAUDE.md file. If no
section clears the bar, nothing is emitted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Iterable
from pathlib import Path

from claude_config_auditor.fixes.flow import FileChange, Proposal
from claude_config_auditor.scanner import FileRecord


# --- Heuristic thresholds ------------------------------------------------

LONG_SECTION_LINES = 40           # heading + this many body lines → candidate
LONG_SECTION_TOKENS = 600         # OR ≈ this many tokens (chars/3.7)
ARCHIVE_FILENAME = "CLAUDE.archive.md"

# Heading words that we treat as STRONG signals the section is
# reference-only and unlikely to need every-session loading. Case-
# insensitive substring match against the heading text (after stripping
# the leading `#`).
_ARCHIVABLE_HEADING_PATTERNS = [
    r"\bchangelog\b",
    r"\brevision history\b",
    r"\bhistory\b",
    r"\barchive\b",
    r"\bexamples?\b",
    r"\breference\b",
    r"\bappendix\b",
    r"\bfaq\b",
    r"\bnotes\b",
    r"\bglossary\b",
]

# Headings we PROTECT — these are usually project rules / conventions
# the user wrote on purpose. We never propose archiving them, regardless
# of length.
_PROTECTED_HEADING_PATTERNS = [
    r"\brules?\b",
    r"\bconventions?\b",
    r"\bguidance\b",
    r"\bdo not\b",
    r"\bdon't\b",
    r"\bdonts?\b",
    r"\bnever\b",
    r"\balways\b",
    r"\bprinciples?\b",
    r"\bcontract\b",
    r"\bcommands?\b",
    r"\bworkflow\b",
]


@dataclass
class _Section:
    """One H2-or-deeper Markdown section.

    Top-level H1 headings are treated as the file's title and never
    moved. Sections nested below the first H1 are candidates.
    """

    heading: str       # full line, e.g. "## Changelog"
    body: str          # body text (lines AFTER the heading, before next ≥-level heading)
    start: int         # index of heading line in original file's split
    end: int           # index of first line AFTER this section
    level: int         # number of leading `#`

    @property
    def line_count(self) -> int:
        return max(0, self.end - self.start - 1)

    @property
    def token_estimate(self) -> int:
        # Same heuristic as the budget module's char fallback.
        return max(1, round(len(self.body) / 3.7))


@dataclass
class _Candidate:
    section: _Section
    reasons: list[str]    # human-readable explanations


def propose_claude_md_archive_fixes(
    claude_md_files: Iterable[FileRecord],
) -> list[Proposal]:
    """For each CLAUDE.md with archivable sections, build one Proposal
    that creates/extends the sibling archive and trims the source."""
    proposals: list[Proposal] = []
    for rec in claude_md_files:
        prop = _build_for_one(rec)
        if prop is not None:
            proposals.append(prop)
    return proposals


def _build_for_one(rec: FileRecord) -> Proposal | None:
    """Inspect one CLAUDE.md; return a Proposal if anything is worth
    archiving, or None otherwise."""
    sections = _split_into_sections(rec.raw)
    if not sections:
        return None

    candidates = _pick_candidates(sections)
    if not candidates:
        return None

    archive_path = rec.path.parent / ARCHIVE_FILENAME
    archive_before = archive_path.read_text(encoding="utf-8") \
        if archive_path.is_file() else ""

    archived_blocks: list[str] = []
    for c in candidates:
        block = (
            c.section.heading + "\n" + c.section.body
            if c.section.body else c.section.heading + "\n"
        )
        archived_blocks.append(block.rstrip("\n") + "\n")

    # Compose the archive's after-content: existing content + a marker
    # header + each archived block.
    moved_marker = (
        f"<!-- moved from {rec.relpath} by claude-config-auditor -->\n\n"
    )
    archive_after_tail = moved_marker + "\n".join(archived_blocks)
    archive_after = (
        archive_before.rstrip("\n") + "\n\n" + archive_after_tail
        if archive_before else archive_after_tail
    )

    # Compose the source's after-content: every section that wasn't
    # archived, plus a one-line pointer for each removed section.
    source_after = _strip_sections_with_pointers(rec.raw, candidates,
                                                  ARCHIVE_FILENAME)

    title = (
        f"Archive {len(candidates)} section(s) of "
        f"{Path(rec.relpath).name} → {ARCHIVE_FILENAME}"
    )
    reason_lines = "; ".join(
        f"`{c.section.heading.strip()}` ({', '.join(c.reasons)})"
        for c in candidates
    )
    rationale = (
        "Each section below looks unlikely to be needed in every Claude "
        f"Code session. Sections selected: {reason_lines}. They move into "
        f"{ARCHIVE_FILENAME}; pointers stay in the source so you can "
        "always find them again."
    )

    return Proposal(
        title=title,
        rationale=rationale,
        changes=[
            FileChange(path=archive_path, before=archive_before,
                       after=archive_after),
            FileChange(path=rec.path, before=rec.raw, after=source_after),
        ],
        source_code="HLT001",
    )


# --- Section parsing ------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def _split_into_sections(content: str) -> list[_Section]:
    """Walk the markdown and emit one _Section per heading at level ≥ 2.

    H1 (top-level title) is skipped because a CLAUDE.md typically has
    one H1 that serves as the file's name, and moving it would orphan
    the document.

    Sections inside fenced code blocks (``` … ```) are ignored — we do
    not want to mistake a `# comment` inside Python or shell code for
    a Markdown heading.
    """
    lines = content.splitlines()
    sections: list[_Section] = []
    in_fence = False
    fence_marker = ""

    # Pass 1: find every real heading line.
    heads: list[tuple[int, int, str]] = []   # (line index, level, heading text)
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        # Toggle fenced code-block state.
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if m:
            heads.append((i, len(m.group(1)), line))

    # Pass 2: turn heads list into sections at level ≥ 2.
    for idx, (line_i, level, heading_line) in enumerate(heads):
        if level < 2:
            continue
        # Section ends at the next heading at level ≤ this one's level,
        # OR end of file.
        end = len(lines)
        for j in range(idx + 1, len(heads)):
            _, lvl, _ = heads[j]
            if lvl <= level:
                end = heads[j][0]
                break
        body_lines = lines[line_i + 1: end]
        body = "\n".join(body_lines).rstrip("\n")
        sections.append(_Section(
            heading=heading_line,
            body=body,
            start=line_i,
            end=end,
            level=level,
        ))
    return sections


def _pick_candidates(sections: list[_Section]) -> list[_Candidate]:
    """Apply the heuristics in §5.2 and return the sections worth
    proposing to archive, each carrying its human-readable reasons."""
    candidates: list[_Candidate] = []
    for s in sections:
        heading_text = s.heading.lstrip("#").strip().lower()
        if any(re.search(p, heading_text)
               for p in _PROTECTED_HEADING_PATTERNS):
            continue  # never touch project rules / conventions

        reasons: list[str] = []
        if any(re.search(p, heading_text)
               for p in _ARCHIVABLE_HEADING_PATTERNS):
            reasons.append("heading suggests reference/log content")
        if s.line_count >= LONG_SECTION_LINES:
            reasons.append(f"{s.line_count} lines")
        if s.token_estimate >= LONG_SECTION_TOKENS:
            reasons.append(f"≈{s.token_estimate} tokens")

        if reasons:
            candidates.append(_Candidate(section=s, reasons=reasons))
    return candidates


def _strip_sections_with_pointers(content: str,
                                    candidates: list[_Candidate],
                                    archive_filename: str) -> str:
    """Return `content` with each candidate's lines (heading + body)
    replaced by a single pointer line referring to the archive."""
    lines = content.splitlines(keepends=True)
    out: list[str] = []
    skip_until: int = -1
    candidate_ranges = sorted(
        ((c.section.start, c.section.end, c.section.heading)
         for c in candidates),
        key=lambda x: x[0],
    )
    range_iter = iter(candidate_ranges)
    next_range = next(range_iter, None)

    i = 0
    while i < len(lines):
        if next_range and i == next_range[0]:
            start, end, heading = next_range
            level_prefix = heading.lstrip()[: len(heading) - len(heading.lstrip("#"))]
            # Use the section's heading level for the pointer so it stays
            # at the same place in the document outline.
            pointer = (
                f"{level_prefix} {_heading_text(heading)}\n\n"
                f"*Moved to [{archive_filename}](./{archive_filename}).*\n\n"
            )
            out.append(pointer)
            i = end
            next_range = next(range_iter, None)
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def _heading_text(heading_line: str) -> str:
    return heading_line.lstrip("#").strip()

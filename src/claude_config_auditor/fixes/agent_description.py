"""Rule-based suggestions for agent-description findings.

Phase 2 brief §5.3 is clear about tone: the auditor should *not* pretend
to be omniscient. We have no LLM at our disposal in this phase, so the
only honest move when an agent description is wrong is to flag it for
the human, not silently rewrite it.

This module turns AGT003/AGT004/AGT005/AGT006/AGT008 findings into
proposals that insert `# TODO (claude-audit, AGTxxx): ...` comment
lines above the `description:` field. YAML comments are ignored by
Claude Code at load time, so the agent's behaviour is unchanged the
instant the proposal is applied — the change is purely a hint to the
human maintainer. AGT003 is the one exception: it inserts a real
`description:` field with a TODO value, because without one Claude
will never invoke the agent.

Findings we deliberately do *not* touch:

  AGT001 — broken YAML. We refuse to edit a frontmatter we cannot
           parse; user fixes by hand.
  AGT002 — missing `name`. Structural issue; auto-editing such a file
           feels like overreach.
  AGT007 — token bloat. The check is about the whole file, not the
           description. No rule-based knowledge of what to trim.

Implementation note: all edits are *string-level*. We never reserialise
the YAML through a parser — that would strip existing comments and
canonicalise quoting, both of which the user did on purpose. Surgical
inserts only.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from claude_config_auditor.findings import Finding
from claude_config_auditor.fixes.flow import Proposal
from claude_config_auditor.scanner import FileRecord


# Codes we know how to suggest a fix for.
_HANDLED_CODES = {"AGT003", "AGT004", "AGT005", "AGT006", "AGT008"}

# Codes whose presence on a file disqualifies it from any auto-edit —
# the file's structure is in doubt and silent automated changes are
# not safe.
_SKIP_IF_PRESENT = {"AGT001", "AGT002"}

# Visible marker so users can grep `TODO (claude-audit` to find every
# hint the tool has injected across their tree.
_TODO_PREFIX = "TODO (claude-audit"


def propose_description_fixes(
    agents: Iterable[FileRecord],
    findings: Iterable[Finding],
) -> list[Proposal]:
    """For each agent file with handleable description findings, build
    one proposal that annotates the frontmatter with TODO comments.

    One proposal per file (not per finding) so the user reviews and
    approves an agent's hints as a single unit.
    """
    by_path: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        if f.file and f.code.startswith("AGT"):
            by_path[f.file].append(f)

    agent_by_path = {a.relpath: a for a in agents}

    proposals: list[Proposal] = []
    for relpath, file_findings in by_path.items():
        rec = agent_by_path.get(relpath)
        if rec is None or not rec.frontmatter_ok:
            continue
        codes_here = {f.code for f in file_findings}
        if codes_here & _SKIP_IF_PRESENT:
            continue
        if not (codes_here & _HANDLED_CODES):
            continue

        prop = _build_proposal(rec, file_findings)
        if prop is not None:
            proposals.append(prop)

    return proposals


def _build_proposal(rec: FileRecord, findings: list[Finding]) -> Proposal | None:
    after = rec.raw
    applied_codes: list[str] = []

    # AGT003 first because it inserts a brand-new field; the subsequent
    # AGT004/5/6/8 inserts can then anchor on the newly-created
    # description line.
    agt003 = next((f for f in findings if f.code == "AGT003"), None)
    if agt003 is not None:
        after = _insert_missing_description(after)
        applied_codes.append("AGT003")

    for code in ("AGT004", "AGT005", "AGT006"):
        f = next((f for f in findings if f.code == code), None)
        if f is None:
            continue
        comment = _comment_for(code, f.message)
        new = _insert_comment_above_description(after, comment)
        if new != after:
            after = new
            applied_codes.append(code)

    # AGT008 can appear multiple times on a single file when the agent
    # overlaps with several others. Emit one comment per overlap.
    overlap_findings = [f for f in findings if f.code == "AGT008"]
    for f in overlap_findings:
        comment = _comment_for("AGT008", f.message)
        new = _insert_comment_above_description(after, comment)
        if new != after:
            after = new
            if "AGT008" not in applied_codes:
                applied_codes.append("AGT008")

    if after == rec.raw or not applied_codes:
        return None

    codes_label = ", ".join(applied_codes)
    title = f"Annotate {Path(rec.relpath).name} with description hints"
    rationale = (
        f"Phase 1 flagged this agent for {codes_label}. The auditor "
        "cannot rewrite descriptions reliably without semantic context, "
        "so it inserts TODO comments pointing at what to revise. The "
        "file's frontmatter still parses; agent behaviour is unchanged "
        "until you act on the hints."
    )
    return Proposal.edit(
        path=rec.path,
        before=rec.raw,
        after=after,
        title=title,
        rationale=rationale,
        source_code=codes_label,
    )


# --- Comment builders -----------------------------------------------------

def _comment_for(code: str, finding_message: str) -> list[str]:
    """Return the lines of the YAML comment block (without the leading
    `#`; the inserter adds those). Each entry is one logical line."""
    if code == "AGT004":
        return [
            f"{_TODO_PREFIX}, {code}): {finding_message}",
            "Add 2-3 concrete trigger phrases so Claude knows when to call",
            "this agent. Without them, routing is unreliable.",
        ]
    if code == "AGT005":
        return [
            f"{_TODO_PREFIX}, {code}): {finding_message}",
            "Consider extending the description with one or two example",
            "user phrases that should fire this agent.",
        ]
    if code == "AGT006":
        return [
            f"{_TODO_PREFIX}, {code}): {finding_message}",
            "Trim the description to the routing signal. Move long-form",
            "usage docs into the agent body — that section loads only",
            "when this agent is invoked.",
        ]
    if code == "AGT008":
        return [
            f"{_TODO_PREFIX}, {code}): {finding_message}",
            "Add a disambiguator: say what this agent does that the other",
            "one does NOT. Otherwise Claude may pick the wrong agent.",
        ]
    # Unknown code — best-effort fallback.
    return [f"{_TODO_PREFIX}, {code}): {finding_message}"]


# --- String-level YAML editors -------------------------------------------

def _insert_comment_above_description(content: str, comment_lines: list[str]) -> str:
    """Insert a YAML comment block of `# <line>` rows directly above the
    `description:` line inside the frontmatter. Preserves all other
    formatting. No-op if no description line is found.
    """
    lines = content.splitlines(keepends=True)
    out: list[str] = []
    inserted = False
    in_fm = False
    seen_open = False

    for line in lines:
        # Toggle frontmatter membership on each `---` line.
        if line.rstrip() == "---":
            if not seen_open:
                seen_open = True
                in_fm = True
                out.append(line)
                continue
            in_fm = False
            out.append(line)
            continue

        if in_fm and not inserted and line.lstrip().startswith("description:"):
            indent = line[: len(line) - len(line.lstrip())]
            for c in comment_lines:
                out.append(f"{indent}# {c}\n")
            inserted = True

        out.append(line)

    return "".join(out)


def _insert_missing_description(content: str) -> str:
    """Insert a `description:` field with a TODO placeholder value
    directly after the `name:` line in frontmatter. The TODO marker
    starts with the standard prefix so it grep-matches alongside the
    comment hints. Returns the content unchanged if no `name:` line
    is found (the AGT002 case, which we skip earlier anyway).
    """
    lines = content.splitlines(keepends=True)
    out: list[str] = []
    inserted = False
    in_fm = False
    seen_open = False

    for line in lines:
        out.append(line)
        if line.rstrip() == "---":
            if not seen_open:
                seen_open = True
                in_fm = True
                continue
            in_fm = False
            continue
        if in_fm and not inserted and line.lstrip().startswith("name:"):
            indent = line[: len(line) - len(line.lstrip())]
            placeholder = (
                f"description: {_TODO_PREFIX}, AGT003): describe in one or "
                "two lines exactly when Claude should invoke this agent.\n"
            )
            out.append(f"{indent}{placeholder}")
            inserted = True

    return "".join(out)

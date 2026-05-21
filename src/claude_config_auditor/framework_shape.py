"""Detect well-known third-party framework installs.

Some Claude Code frameworks lay out `.claude/` in a way that violates
the "always have a CLAUDE.md" expectation by design. BMAD-METHOD, for
example, installs 70+ skills and intentionally writes no CLAUDE.md to
keep the eager session footprint near zero. Flagging that as a missing
configuration is correct (the file is missing) but the recommended
remedy — "add CLAUDE.md" — is wrong for those projects.

This module identifies those shapes and exposes the signal as
*context*, not as a suppression: findings continue to fire, but their
hint text gains a framework-aware sentence. The user reads both
signals and decides.

Detection is heuristic and intentionally narrow — when we don't
recognise the shape, we say so (`name=None`) rather than guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from claude_config_auditor.scanner import Scan


# Per-shape thresholds. Tuned against the 5 frameworks audited in May 2026
# (BMAD, claude-flow, wshobson, VoltAgent, SuperClaude). Adjust if real
# projects start producing false positives.
_SKILL_PACK_MIN_SKILLS = 10
_AGENT_PACK_MIN_AGENTS = 30
_COMMAND_PACK_MIN_COMMANDS = 5


@dataclass
class FrameworkShape:
    """What kind of install the target looks like.

    `name` is a human-readable label ("BMAD", "skill-pack", …) or None
    when no recognised shape matches. `intentional_no_claude_md` is True
    when the shape's convention is to *not* write a CLAUDE.md — useful
    to enrich (not suppress) HLT005's hint.

    `markers` lists the evidence that led to the classification so the
    report can explain itself.
    """

    name: str | None = None
    intentional_no_claude_md: bool = False
    markers: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.markers is None:
            self.markers = []


def detect(target: Path, scan: Scan) -> FrameworkShape:
    """Classify the install shape.

    Order matters: explicit marker directories (BMAD's `_bmad/`,
    claude-flow's `.claude-flow/`) win over heuristic shapes, because
    they are unambiguous. The heuristic shapes only fire when no
    marker is present and the layout looks distinctly like a pure
    skill / agent / command pack.
    """
    # --- Explicit marker directories ---------------------------------------
    if (target / "_bmad").is_dir():
        return FrameworkShape(
            name="BMAD",
            intentional_no_claude_md=True,
            markers=[
                "_bmad/ runtime directory present",
                f"{len(scan.skills)} skill(s) in .claude/skills/",
            ],
        )

    if (target / ".claude-flow").is_dir():
        return FrameworkShape(
            name="claude-flow",
            # claude-flow does write CLAUDE.md by default, so absence
            # there is a real signal, not intentional.
            intentional_no_claude_md=False,
            markers=[
                ".claude-flow/ runtime directory present",
                f"{len(scan.agents)} agent(s), {len(scan.skills)} skill(s)",
            ],
        )

    # --- Heuristic shapes --------------------------------------------------
    # Skill-pack: lots of skills, no agents, no CLAUDE.md.
    # Matches BMAD-style installers and Anthropic's official skills repo.
    if (
        not scan.has_claude_md
        and not scan.agents
        and len(scan.skills) >= _SKILL_PACK_MIN_SKILLS
    ):
        return FrameworkShape(
            name="skill-pack",
            intentional_no_claude_md=True,
            markers=[
                f"{len(scan.skills)} skill(s), no agents, no CLAUDE.md",
            ],
        )

    # Agent-pack: large agent collection (wshobson, VoltAgent), no
    # CLAUDE.md, no skills. The convention is to copy these in and
    # let Claude route on description text alone.
    if (
        not scan.has_claude_md
        and not scan.skills
        and len(scan.agents) >= _AGENT_PACK_MIN_AGENTS
    ):
        return FrameworkShape(
            name="agent-pack",
            intentional_no_claude_md=True,
            markers=[
                f"{len(scan.agents)} agent(s), no skills, no CLAUDE.md",
            ],
        )

    # Command-pack: slash-command-only install (SuperClaude when only
    # commands are scoped to the project).
    if (
        not scan.has_claude_md
        and not scan.agents
        and not scan.skills
        and len(scan.commands) >= _COMMAND_PACK_MIN_COMMANDS
    ):
        return FrameworkShape(
            name="command-pack",
            intentional_no_claude_md=True,
            markers=[
                f"{len(scan.commands)} slash command(s), nothing else",
            ],
        )

    return FrameworkShape()

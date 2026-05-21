"""Skill quality audit — see brief section 5.3.

Skills live under .claude/skills/<name>/SKILL.md. The SKILL.md has YAML
frontmatter with `name` and `description`. The description is what Claude
reads at session start to decide *when* to use the skill, so it must be
specific and trigger-oriented.
"""

from __future__ import annotations

from dataclasses import dataclass

from claude_config_auditor.findings import Finding
from claude_config_auditor.scanner import FileRecord

SKILL_DESCRIPTION_MIN_CHARS = 40
SKILL_DESCRIPTION_LONG_CHARS = 800
# SKL005 measures eager footprint only — see AGENT_EAGER_BLOAT_TOKENS
# in agents.py for the same reasoning. A skill body of 5 000 tokens is
# fine: skills are read at use time, not at session start. What hurts
# every session is a bloated description in the SKILL.md frontmatter.
SKILL_EAGER_BLOAT_TOKENS = 250


@dataclass
class SkillReport:
    findings: list[Finding]


def audit(
    skills: list[FileRecord],
    tokens_by_path: dict[str, int],
    eager_tokens_by_path: dict[str, int] | None = None,
) -> SkillReport:
    """Lint skill definitions; see agents.audit for the contract."""
    if eager_tokens_by_path is None:
        eager_tokens_by_path = {}
    findings: list[Finding] = []

    for rec in skills:
        if not rec.frontmatter_ok:
            findings.append(
                Finding(
                    severity="error",
                    code="SKL001",
                    message=f"SKILL.md frontmatter could not be parsed ({rec.parse_warning})",
                    file=rec.relpath,
                    hint="Fix the YAML between the '---' lines at the top of SKILL.md.",
                )
            )
            continue

        description = (rec.frontmatter.get("description") or "").strip()
        if not description:
            findings.append(
                Finding(
                    severity="error",
                    code="SKL002",
                    message="SKILL.md has no `description` — Claude cannot decide when to invoke this skill",
                    file=rec.relpath,
                    hint="Describe the user intents that should trigger this skill, in concrete terms.",
                )
            )
        else:
            dlen = len(description)
            if dlen < SKILL_DESCRIPTION_MIN_CHARS:
                findings.append(
                    Finding(
                        severity="warning",
                        code="SKL003",
                        message=f"SKILL.md `description` is very short ({dlen} chars)",
                        file=rec.relpath,
                        hint="Include example user phrases that should trigger this skill.",
                    )
                )
            elif dlen > SKILL_DESCRIPTION_LONG_CHARS:
                findings.append(
                    Finding(
                        severity="warning",
                        code="SKL004",
                        message=f"SKILL.md `description` is unusually long ({dlen} chars)",
                        file=rec.relpath,
                        hint="The description is loaded on every session. Keep it to triggers; move usage docs into the body.",
                    )
                )

        eager_cost = eager_tokens_by_path.get(rec.relpath, 0)
        if eager_cost > SKILL_EAGER_BLOAT_TOKENS:
            findings.append(
                Finding(
                    severity="info",
                    code="SKL005",
                    message=(
                        f"SKILL.md session-start cost is ~{eager_cost} tokens "
                        "(frontmatter description loaded on every session)"
                    ),
                    file=rec.relpath,
                    hint=(
                        "The body of a skill is on-demand. Only the "
                        "frontmatter — primarily `description` — is loaded "
                        "every session. A description over ~250 tokens "
                        "usually means usage instructions belong in the "
                        "body, not the frontmatter."
                    ),
                )
            )

    return SkillReport(findings=findings)

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
SKILL_TOKEN_BLOAT = 3_000


@dataclass
class SkillReport:
    findings: list[Finding]


def audit(skills: list[FileRecord], tokens_by_path: dict[str, int]) -> SkillReport:
    """Lint skill definitions; see agents.audit for the tokens_by_path contract."""
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

        token_cost = tokens_by_path.get(rec.relpath, 0)
        if token_cost > SKILL_TOKEN_BLOAT:
            findings.append(
                Finding(
                    severity="info",
                    code="SKL005",
                    message=f"SKILL.md is large (~{token_cost} tokens)",
                    file=rec.relpath,
                    hint="Skills are loaded by description at session start, but the body is read on use. Still — trim aggressively.",
                )
            )

    return SkillReport(findings=findings)

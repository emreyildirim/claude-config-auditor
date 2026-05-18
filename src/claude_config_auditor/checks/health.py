"""Overall health checks — see brief section 5.4.

These are cross-cutting checks that don't fit cleanly into one config
category. They run after the budget pass so they can use the totals.
"""

from __future__ import annotations

from claude_config_auditor.checks.budget import BudgetReport
from claude_config_auditor.findings import Finding
from claude_config_auditor.scanner import Scan


DEFAULT_CLAUDE_MD_BUDGET_TOKENS = 5_000


def audit(scan: Scan, budget: BudgetReport, claude_md_budget: int) -> list[Finding]:
    findings: list[Finding] = []

    # CLAUDE.md per-file budget.
    for rec in scan.claude_md_files:
        tokens = next(
            (f.tokens for f in budget.files if f.relpath == rec.relpath),
            0,
        )
        if tokens > claude_md_budget:
            findings.append(
                Finding(
                    severity="warning",
                    code="HLT001",
                    message=(
                        f"`{rec.relpath}` is ~{tokens} tokens, over the configured "
                        f"budget of {claude_md_budget}"
                    ),
                    file=rec.relpath,
                    hint="Move stable reference material out of CLAUDE.md into a skill or external doc; keep CLAUDE.md to project-specific rules.",
                )
            )

    # Session-start total budget vs reference window.
    pct = budget.percent_of_window
    if pct >= 10:
        findings.append(
            Finding(
                severity="warning",
                code="HLT002",
                message=(
                    f"session-start config is ~{budget.session_start_total} tokens "
                    f"({pct:.1f}% of the {budget.reference_window_label} reference window) "
                    "— that is paid on every session"
                ),
                hint="Trim CLAUDE.md and prune unused agents/skills.",
            )
        )
    elif pct >= 5:
        findings.append(
            Finding(
                severity="info",
                code="HLT003",
                message=(
                    f"session-start config is ~{budget.session_start_total} tokens "
                    f"({pct:.1f}% of the reference window)"
                ),
            )
        )

    # Imbalance: big CLAUDE.md with no agents/skills, or many agents with no CLAUDE.md.
    claude_md_tokens = sum(
        f.tokens for f in budget.files if f.category == "claude.md"
    )
    if claude_md_tokens > 4_000 and not scan.agents and not scan.skills:
        findings.append(
            Finding(
                severity="info",
                code="HLT004",
                message=(
                    "large CLAUDE.md but no agents/skills — some of this content "
                    "may belong in a skill so it only loads when relevant"
                ),
            )
        )
    if (len(scan.agents) + len(scan.skills)) >= 5 and not scan.has_claude_md:
        findings.append(
            Finding(
                severity="info",
                code="HLT005",
                message="agents/skills present but no CLAUDE.md — consider adding project-level guidance",
            )
        )

    if not scan.has_claude_dir and not scan.has_claude_md:
        findings.append(
            Finding(
                severity="info",
                code="HLT006",
                message="no .claude/ directory and no CLAUDE.md found in this directory",
                hint="claude-config-auditor only has something to look at when one of these exists.",
            )
        )

    return findings

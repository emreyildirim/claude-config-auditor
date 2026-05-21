"""Overall health checks — see brief section 5.4.

These are cross-cutting checks that don't fit cleanly into one config
category. They run after the budget pass so they can use the totals.
"""

from __future__ import annotations

from claude_config_auditor.checks.budget import BudgetReport
from claude_config_auditor.findings import Finding
from claude_config_auditor.framework_shape import FrameworkShape
from claude_config_auditor.scanner import Scan


DEFAULT_CLAUDE_MD_BUDGET_TOKENS = 5_000

# Thresholds for session-start total vs context window.
WINDOW_WARN_PERCENT = 10      # session-start ≥ this percent → warning
WINDOW_INFO_PERCENT = 5       # session-start ≥ this percent → info

# Imbalance heuristics.
LARGE_CLAUDE_MD_TOKENS = 4_000      # "big CLAUDE.md without agents/skills"
AGENT_OR_SKILL_FLOOR = 5            # ≥ this many agents/skills without CLAUDE.md
                                    # → suggest project-level guidance


def audit(
    scan: Scan,
    budget: BudgetReport,
    claude_md_budget: int,
    tokens_by_path: dict[str, int],
    shape: FrameworkShape | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if shape is None:
        shape = FrameworkShape()

    # CLAUDE.md per-file budget.
    for rec in scan.claude_md_files:
        tokens = tokens_by_path.get(rec.relpath, 0)
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
    if pct >= WINDOW_WARN_PERCENT:
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
    elif pct >= WINDOW_INFO_PERCENT:
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
    if claude_md_tokens > LARGE_CLAUDE_MD_TOKENS and not scan.agents and not scan.skills:
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
    if (len(scan.agents) + len(scan.skills)) >= AGENT_OR_SKILL_FLOOR and not scan.has_claude_md:
        # The fact is unchanged — no CLAUDE.md is present — and we still
        # emit it, because even a project that runs a third-party framework
        # may benefit from a thin project-specific CLAUDE.md alongside it.
        # When a known framework shape is detected, we enrich the hint so
        # the user has the framework convention in front of them and can
        # decide for themselves whether to act.
        if shape.intentional_no_claude_md and shape.name:
            hint = (
                f"This looks like a {shape.name}-style install where no "
                "project CLAUDE.md is by design. You can ignore this if "
                "the framework's defaults match your project, or add a "
                "thin CLAUDE.md for project-specific rules — both are "
                "valid."
            )
        else:
            hint = (
                "A short CLAUDE.md at the project root gives Claude the "
                "context it needs to apply your rules consistently across "
                "agents and skills."
            )
        findings.append(
            Finding(
                severity="info",
                code="HLT005",
                message="agents/skills present but no CLAUDE.md",
                hint=hint,
            )
        )

    # Positive context: when we recognise the shape, surface it so the
    # rest of the report is easier to read. Not a problem, not a
    # suggestion — just orientation.
    if shape.name:
        markers = "; ".join(shape.markers) if shape.markers else "shape match"
        findings.append(
            Finding(
                severity="info",
                code="HLT007",
                message=f"detected {shape.name}-style install at this target",
                hint=f"Evidence: {markers}.",
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

"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from claude_config_auditor import __version__
from claude_config_auditor.checks import agents as agents_check
from claude_config_auditor.checks import budget as budget_check
from claude_config_auditor.checks import health as health_check
from claude_config_auditor.checks import skills as skills_check
from claude_config_auditor.findings import Finding
from claude_config_auditor.render_html import render_html
from claude_config_auditor.report import render_json, render_terminal
from claude_config_auditor.scanner import scan
from claude_config_auditor.tokens import get_estimator


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="claude-audit",
        description=(
            "Read-only linter for .claude/ and CLAUDE.md. Measures the token "
            "cost of your Claude Code config and flags quality issues. "
            "Does not modify any files."
        ),
    )
    p.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Directory to audit (default: current working directory).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report instead of the terminal view.",
    )
    p.add_argument(
        "--html",
        metavar="PATH",
        help=(
            "Write a self-contained HTML report (with charts) to PATH. "
            "Can be combined with terminal or --json output."
        ),
    )
    p.add_argument(
        "--budget",
        type=int,
        default=health_check.DEFAULT_CLAUDE_MD_BUDGET_TOKENS,
        metavar="TOKENS",
        help=(
            "Token budget for a single CLAUDE.md file. Files larger than "
            f"this are flagged. Default: {health_check.DEFAULT_CLAUDE_MD_BUDGET_TOKENS}."
        ),
    )
    p.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color in terminal output.",
    )
    p.add_argument(
        "--fail-on",
        choices=["never", "error", "warning"],
        default="never",
        help=(
            "Exit with a non-zero status when findings of this severity or "
            "worse are present. Useful in CI. Default: never."
        ),
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"claude-config-auditor {__version__}",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"error: target does not exist: {target}", file=sys.stderr)
        return 2
    if not target.is_dir():
        print(f"error: target is not a directory: {target}", file=sys.stderr)
        return 2

    estimator = get_estimator()
    scan_result = scan(target)

    budget = budget_check.compute(scan_result, estimator)
    tokens_by_path = budget.tokens_by_path

    findings: list[Finding] = []
    findings.extend(agents_check.audit(scan_result.agents, tokens_by_path).findings)
    findings.extend(skills_check.audit(scan_result.skills, tokens_by_path).findings)
    findings.extend(health_check.audit(scan_result, budget, args.budget, tokens_by_path))

    if args.html:
        html_path = Path(args.html).resolve()
        # Sanity: never write inside the target dir — keeps the read-only
        # guarantee easy to reason about even if the user passes a path
        # that happens to be under the project.
        try:
            html_path.relative_to(target)
            print(
                f"error: --html path must not be inside the target directory ({target})",
                file=sys.stderr,
            )
            return 2
        except ValueError:
            pass
        html_path.parent.mkdir(parents=True, exist_ok=True)
        with html_path.open("w", encoding="utf-8") as f:
            render_html(target=str(target), budget=budget, findings=findings, out=f)
        print(f"wrote HTML report: {html_path}", file=sys.stderr)

    if args.json:
        render_json(target=str(target), budget=budget, findings=findings)
    elif not args.html:
        render_terminal(
            target=str(target),
            budget=budget,
            findings=findings,
            use_color=not args.no_color,
        )

    if args.fail_on == "error" and any(f.severity == "error" for f in findings):
        return 1
    if args.fail_on == "warning" and any(
        f.severity in ("error", "warning") for f in findings
    ):
        return 1
    return 0

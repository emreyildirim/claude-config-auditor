"""Command-line entry point.

Three subcommands:

  audit  — Phase 1, read-only report. Default when no subcommand is given,
           so `claude-audit .` and every existing `--json` / `--html`
           script keeps working unchanged.

  fix    — Phase 2, opt-in. Runs the audit, gathers fix proposals, walks
           the user through each one interactively, and applies the
           accepted ones under a backup session. Never invoked unless the
           user types `fix` explicitly.

  revert — Phase 2, undo. Lists or restores backup sessions made by `fix`.

The fix mode is strictly opt-in: typing just `claude-audit .` (or the
equivalent `claude-audit audit .`) never modifies any file in the
target directory. Read-only stays the default forever.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import IO

from claude_config_auditor import __version__
from claude_config_auditor.backup import (
    DriftError,
    list_sessions,
    revert_session,
)
from claude_config_auditor.checks import agents as agents_check
from claude_config_auditor.checks import budget as budget_check
from claude_config_auditor.checks import health as health_check
from claude_config_auditor.checks import skills as skills_check
from claude_config_auditor.findings import Finding
from claude_config_auditor.fixes import Proposal, run_fix_flow
from claude_config_auditor.fixes.agent_description import (
    propose_description_fixes,
)
from claude_config_auditor.fixes.claude_md_archive import (
    propose_claude_md_archive_fixes,
)
from claude_config_auditor.framework_shape import detect as detect_shape
from claude_config_auditor.render_html import render_html
from claude_config_auditor.report import render_json, render_terminal
from claude_config_auditor.scanner import scan
from claude_config_auditor.tokens import get_estimator


_SUBCOMMANDS = {"audit", "fix", "revert"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="claude-audit",
        description=(
            "Read-only linter for .claude/ and CLAUDE.md. The default "
            "`audit` mode never modifies files. Phase 2 `fix` mode is "
            "opt-in and prompts before every change."
        ),
    )
    p.add_argument(
        "--version", action="version",
        version=f"claude-config-auditor {__version__}",
    )

    sub = p.add_subparsers(dest="command", metavar="{audit,fix,revert}")

    # --- audit (Phase 1, read-only) -------------------------------------
    audit_p = sub.add_parser(
        "audit",
        help="Analyse a project's .claude/ config (default, read-only).",
        description=(
            "Run the static analysis on the target and produce a report. "
            "Never modifies any file in the target directory."
        ),
    )
    _add_audit_args(audit_p)

    # --- fix (Phase 2, opt-in, modifies files) --------------------------
    fix_p = sub.add_parser(
        "fix",
        help="Propose and (with your approval) apply fixes for findings.",
        description=(
            "Run the audit, build fix proposals from the findings, and "
            "walk you through each one. Every change is previewed as a "
            "diff and applied only after explicit approval. All changes "
            "are backed up before being written so they can be reverted."
        ),
    )
    fix_p.add_argument("target", nargs="?", default=".",
                       help="Directory to fix (default: current directory).")
    fix_p.add_argument(
        "--dry-run", action="store_true",
        help="Show every proposal as a diff but do not prompt or apply.",
    )
    fix_p.add_argument(
        "--apply-all", action="store_true",
        help=(
            "Skip the per-change prompt and apply every proposal after "
            "showing its diff. Diffs are still printed; this is batch "
            "approval, not silent application. Required when stdin is "
            "not a terminal."
        ),
    )
    fix_p.add_argument(
        "--no-color", action="store_true",
        help="Disable ANSI color in diff output.",
    )
    fix_p.add_argument(
        "--backup-dir", metavar="PATH",
        help=(
            "Override the location backup sessions are written to "
            "(default: <target>/.claude-config-auditor/backups/)."
        ),
    )
    fix_p.add_argument(
        "--accurate", action="store_true",
        help=(
            "Route token counts through Anthropic's count_tokens endpoint "
            "(uses ANTHROPIC_API_KEY). Opt-in; default tokenizer unchanged."
        ),
    )
    fix_p.add_argument(
        "--accurate-model", metavar="MODEL", default=None,
        help="Model name for count_tokens (default: claude-sonnet-4-5).",
    )

    # --- revert ---------------------------------------------------------
    rev_p = sub.add_parser(
        "revert",
        help="List or restore backup sessions written by `fix`.",
        description=(
            "Restore a project to the state captured before `fix` ran. "
            "Without arguments, reverts the most recent session; pass a "
            "session id to revert a specific one, or --list to enumerate."
        ),
    )
    rev_p.add_argument("target", nargs="?", default=".",
                       help="Directory whose backups to operate on.")
    rev_p.add_argument("session", nargs="?", default=None,
                       help="Session id (directory name) to revert. "
                            "Defaults to the most recent session.")
    rev_p.add_argument(
        "--list", action="store_true", dest="list_only",
        help="List available backup sessions and exit.",
    )
    rev_p.add_argument(
        "--force", action="store_true",
        help=(
            "Overwrite files that have drifted from the state recorded "
            "at fix time. Without this, drifted files are refused with "
            "an explanation."
        ),
    )
    rev_p.add_argument(
        "--backup-dir", metavar="PATH",
        help="Override the backup-session location.",
    )

    return p


def _add_audit_args(parser: argparse.ArgumentParser) -> None:
    """Audit's argument surface, factored out so the default-no-subcommand
    path can mount it on the top-level parser as well."""
    parser.add_argument(
        "target", nargs="?", default=".",
        help="Directory to audit (default: current working directory).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit a machine-readable JSON report instead of the terminal view.",
    )
    parser.add_argument(
        "--html", metavar="PATH",
        help=(
            "Write a self-contained HTML report (with charts) to PATH. "
            "Can be combined with terminal or --json output."
        ),
    )
    parser.add_argument(
        "--budget", type=int,
        default=health_check.DEFAULT_CLAUDE_MD_BUDGET_TOKENS,
        metavar="TOKENS",
        help=(
            "Token budget for a single CLAUDE.md file. Files larger than "
            f"this are flagged. Default: {health_check.DEFAULT_CLAUDE_MD_BUDGET_TOKENS}."
        ),
    )
    parser.add_argument(
        "--no-color", action="store_true",
        help=(
            "Disable ANSI color in terminal output. The NO_COLOR "
            "environment variable (no-color.org) has the same effect."
        ),
    )
    parser.add_argument(
        "--fail-on", choices=["never", "error", "warning"], default="never",
        help=(
            "Exit with a non-zero status when findings of this severity "
            "or worse are present. Useful in CI. Default: never."
        ),
    )
    parser.add_argument(
        "--accurate", action="store_true",
        help=(
            "Route token counts through Anthropic's count_tokens endpoint "
            "for ground-truth numbers (uses ANTHROPIC_API_KEY from the "
            "environment). Default behaviour is unchanged; this is an "
            "opt-in opt-out from the offline contract."
        ),
    )
    parser.add_argument(
        "--accurate-model", metavar="MODEL", default=None,
        help=(
            "Model name to pass to count_tokens (default: "
            "claude-sonnet-4-5). Only meaningful with --accurate."
        ),
    )


def _estimator_from_args(args: argparse.Namespace):
    """Build the estimator honouring --accurate / --accurate-model, with a
    clean exit on the explicit-opt-in error (missing ANTHROPIC_API_KEY)."""
    try:
        return get_estimator(
            accurate=getattr(args, "accurate", False),
            accurate_model=getattr(args, "accurate_model", None),
        )
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)


def _should_use_color(args: argparse.Namespace, env: Mapping[str, str]) -> bool:
    """Honour the --no-color flag and the NO_COLOR environment variable
    (no-color.org). Empty NO_COLOR is treated as unset."""
    if getattr(args, "no_color", False):
        return False
    if env.get("NO_COLOR"):
        return False
    return True


# --- Argv normalisation: default subcommand is "audit" --------------------

def _normalise_argv(argv: list[str]) -> list[str]:
    """Inject `audit` as the implicit subcommand when none is given.

    This keeps `claude-audit .`, `claude-audit . --json`, and every
    existing CI script working unchanged. Only does the prepend when
    the first arg is not already a known subcommand and not a top-level
    help/version flag.
    """
    if not argv:
        return ["audit"]
    first = argv[0]
    if first in _SUBCOMMANDS:
        return argv
    if first in {"-h", "--help", "--version"}:
        return argv
    return ["audit", *argv]


# --- main dispatch --------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    args = build_parser().parse_args(_normalise_argv(list(argv)))

    try:
        if args.command == "audit":
            return _run_audit(args)
        if args.command == "fix":
            return _run_fix(args)
        if args.command == "revert":
            return _run_revert(args)
    except RuntimeError as e:
        # Operational errors (e.g. --accurate hitting a 401 mid-audit)
        # surface as a single-line message, never a stack trace.
        print(f"error: {e}", file=sys.stderr)
        return 2
    # build_parser sets command to None only when no subparser matched;
    # _normalise_argv prevents that. Treat as a programming error.
    print("error: no command", file=sys.stderr)
    return 2


# --- audit ----------------------------------------------------------------

def _run_audit(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"error: target does not exist: {target}", file=sys.stderr)
        return 2
    if not target.is_dir():
        print(f"error: target is not a directory: {target}", file=sys.stderr)
        return 2

    estimator = _estimator_from_args(args)
    scan_result = scan(target)
    budget = budget_check.compute(scan_result, estimator)
    tokens_by_path = budget.tokens_by_path
    eager_by_path = budget.eager_tokens_by_path
    shape = detect_shape(target, scan_result)

    findings: list[Finding] = []
    findings.extend(
        agents_check.audit(scan_result.agents, tokens_by_path, eager_by_path).findings
    )
    findings.extend(
        skills_check.audit(scan_result.skills, tokens_by_path, eager_by_path).findings
    )
    findings.extend(
        health_check.audit(scan_result, budget, args.budget, tokens_by_path, shape)
    )

    if args.html:
        html_path = Path(args.html).resolve()
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
            use_color=_should_use_color(args, os.environ),
        )

    if args.fail_on == "error" and any(f.severity == "error" for f in findings):
        return 1
    if args.fail_on == "warning" and any(
        f.severity in ("error", "warning") for f in findings
    ):
        return 1
    return 0


# --- fix ------------------------------------------------------------------

def _interactive_prompter(stdin: IO[str], stdout: IO[str]):
    """Build a Prompter that reads y/n/a/q from a real terminal.

    EOF (e.g. user hits Ctrl-D) is treated as `q` so an interrupted
    session stops cleanly instead of looping forever on empty reads.
    Empty input re-prompts; unrecognised input also re-prompts with a
    one-line reminder of the choices.
    """
    def prompter(proposal: Proposal, rendered: str) -> str:
        while True:
            stdout.write("  Apply this change? [y]es / [n]o / [a]ll / [q]uit > ")
            stdout.flush()
            try:
                line = stdin.readline()
            except KeyboardInterrupt:
                return "q"
            if line == "":              # EOF
                stdout.write("\n")
                return "q"
            choice = line.strip().lower()
            if choice in {"y", "yes", "n", "no", "a", "all", "q", "quit"}:
                return choice[0]
            stdout.write("  (please type one of: y, n, a, q)\n")
    return prompter


def _gather_proposals(target: Path, args: argparse.Namespace) -> list[Proposal]:
    estimator = _estimator_from_args(args)
    scan_result = scan(target)
    budget = budget_check.compute(scan_result, estimator)
    tokens_by_path = budget.tokens_by_path
    eager_by_path = budget.eager_tokens_by_path
    shape = detect_shape(target, scan_result)

    findings: list[Finding] = []
    findings.extend(
        agents_check.audit(scan_result.agents, tokens_by_path, eager_by_path).findings
    )
    findings.extend(
        skills_check.audit(scan_result.skills, tokens_by_path, eager_by_path).findings
    )
    findings.extend(health_check.audit(
        scan_result, budget,
        health_check.DEFAULT_CLAUDE_MD_BUDGET_TOKENS,
        tokens_by_path, shape,
    ))

    proposals: list[Proposal] = []
    proposals.extend(propose_description_fixes(scan_result.agents, findings))
    proposals.extend(propose_claude_md_archive_fixes(scan_result.claude_md_files))
    return proposals


def _run_fix(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"error: target does not exist: {target}", file=sys.stderr)
        return 2
    if not target.is_dir():
        print(f"error: target is not a directory: {target}", file=sys.stderr)
        return 2

    use_color = _should_use_color(args, os.environ)
    proposals = _gather_proposals(target, args)

    if not proposals:
        print("No fix proposals to review. Run `claude-audit` to see the report.")
        return 0

    if args.dry_run:
        # Dry-run draws every proposal but never prompts or writes.
        def must_not_prompt(*_a, **_kw):
            raise RuntimeError("dry-run should not prompt")
        run_fix_flow(
            target, proposals,
            prompter=must_not_prompt,
            out=sys.stdout,
            use_color=use_color,
            dry_run=True,
            backup_root=Path(args.backup_dir) if args.backup_dir else None,
        )
        return 0

    # Decide prompter: interactive on a TTY, batch under --apply-all,
    # error otherwise (non-interactive without explicit consent flag).
    is_tty = getattr(sys.stdin, "isatty", lambda: False)()
    if args.apply_all:
        prompter = lambda p, r: "a"   # noqa: E731 — small lambda
    elif is_tty:
        prompter = _interactive_prompter(sys.stdin, sys.stdout)
    else:
        print(
            "error: `fix` requires an interactive terminal. Either run "
            "from a real shell, or use --dry-run to preview without "
            "applying, or --apply-all to accept every proposal.",
            file=sys.stderr,
        )
        return 2

    outcome = run_fix_flow(
        target, proposals,
        prompter=prompter,
        out=sys.stdout,
        use_color=use_color,
        backup_root=Path(args.backup_dir) if args.backup_dir else None,
    )
    if outcome.quit_early:
        return 1
    return 0


# --- revert ---------------------------------------------------------------

def _run_revert(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if not target.is_dir():
        print(f"error: target is not a directory: {target}", file=sys.stderr)
        return 2

    backup_root = Path(args.backup_dir) if args.backup_dir else None
    sessions = list_sessions(target, backup_root=backup_root)

    if args.list_only:
        if not sessions:
            print("No backup sessions found.")
            return 0
        print(f"{len(sessions)} backup session(s):")
        for s in sessions:
            print(f"  {s.name}")
        return 0

    if not sessions:
        print("No backup sessions to revert.", file=sys.stderr)
        return 1

    if args.session:
        wanted = next(
            (s for s in sessions if s.name == args.session),
            None,
        )
        if wanted is None:
            print(
                f"error: session {args.session!r} not found. "
                "Use --list to see available sessions.",
                file=sys.stderr,
            )
            return 2
        session_dir = wanted
    else:
        session_dir = sessions[-1]   # most recent

    try:
        touched = revert_session(session_dir, force=args.force)
    except DriftError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "Re-run with --force to overwrite the drifted file(s) anyway.",
            file=sys.stderr,
        )
        return 1

    print(f"Reverted {len(touched)} file(s) from session {session_dir.name}.")
    return 0

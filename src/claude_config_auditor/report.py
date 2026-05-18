"""Report rendering — terminal (human) and JSON (machine).

The order is fixed by the brief (section 5.5):
  1. Headline: session-start token total + % of reference window.
  2. Per-file breakdown, most expensive first.
  3. Quality findings, error -> warning -> info.
  4. Closing note: estimator method + reminder that everything is read-only.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import IO

from claude_config_auditor.checks.budget import BudgetReport
from claude_config_auditor.findings import Finding


# ANSI escape codes. Disabled when output isn't a TTY or when --no-color is set.
class _Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    GREEN = "\033[32m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"


class _NoStyle:
    RESET = BOLD = DIM = RED = YELLOW = GREEN = CYAN = MAGENTA = ""


SEVERITY_COLOR = {
    "error": "RED",
    "warning": "YELLOW",
    "info": "CYAN",
}


def render_terminal(
    *,
    target: str,
    budget: BudgetReport,
    findings: list[Finding],
    out: IO[str] | None = None,
    use_color: bool = True,
) -> None:
    out = out or sys.stdout
    s = _Style if (use_color and out.isatty()) else _NoStyle

    write = out.write

    # --- Header ---------------------------------------------------------
    write(f"{s.BOLD}claude-config-auditor{s.RESET}  ")
    write(f"{s.DIM}target: {target}{s.RESET}\n")
    write(f"{s.DIM}tokenizer: {budget.estimator_method}{s.RESET}\n\n")

    # --- Headline -------------------------------------------------------
    pct = budget.percent_of_window
    pct_color = s.GREEN if pct < 5 else (s.YELLOW if pct < 15 else s.RED)
    write(f"{s.BOLD}Session-start fixed cost{s.RESET}\n")
    write(
        f"  ~{s.BOLD}{budget.session_start_total:,}{s.RESET} tokens  "
        f"({pct_color}{pct:.1f}%{s.RESET} of {budget.reference_window_label})\n"
    )
    write(f"  {s.DIM}This is paid on every Claude Code session in this project.{s.RESET}\n\n")

    # --- Per-category --------------------------------------------------
    write(f"{s.BOLD}By category{s.RESET}\n")
    for cat in budget.categories:
        if cat.file_count == 0 and cat.total_tokens == 0:
            continue
        write(
            f"  {cat.name:<10} {cat.file_count:>3} file(s)   "
            f"~{cat.total_tokens:,} tokens\n"
        )
    write("\n")

    # --- Per-file (top N) -----------------------------------------------
    if budget.files:
        write(f"{s.BOLD}Largest files (top 15){s.RESET}\n")
        for ft in budget.files[:15]:
            write(
                f"  ~{ft.tokens:>6,} tok  {s.DIM}{ft.category:<10}{s.RESET}  {ft.relpath}\n"
            )
        if len(budget.files) > 15:
            write(f"  {s.DIM}... and {len(budget.files) - 15} more{s.RESET}\n")
        write("\n")

    # --- Findings -------------------------------------------------------
    findings_sorted = sorted(findings, key=Finding.sort_key)
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings_sorted:
        counts[f.severity] += 1

    write(
        f"{s.BOLD}Findings{s.RESET}  "
        f"{s.RED}{counts['error']} error{s.RESET}  "
        f"{s.YELLOW}{counts['warning']} warning{s.RESET}  "
        f"{s.CYAN}{counts['info']} info{s.RESET}\n"
    )
    if not findings_sorted:
        write(f"  {s.GREEN}No issues found.{s.RESET}\n")
    for f in findings_sorted:
        color_name = SEVERITY_COLOR[f.severity]
        color = getattr(s, color_name)
        location = f" {s.DIM}{f.file}{s.RESET}" if f.file else ""
        write(f"  {color}{f.severity:<7}{s.RESET} {s.DIM}[{f.code}]{s.RESET}{location}\n")
        write(f"          {f.message}\n")
        if f.hint:
            write(f"          {s.DIM}hint: {f.hint}{s.RESET}\n")
    write("\n")

    # --- Footer ---------------------------------------------------------
    write(f"{s.DIM}{budget.estimator_note}{s.RESET}\n")
    write(
        f"{s.DIM}This tool is read-only. Nothing was modified.{s.RESET}\n"
    )


def render_json(
    *,
    target: str,
    budget: BudgetReport,
    findings: list[Finding],
    out: IO[str] | None = None,
) -> None:
    out = out or sys.stdout
    payload = {
        "target": target,
        "tokenizer": {
            "method": budget.estimator_method,
            "note": budget.estimator_note,
            "estimate": True,
        },
        "reference_window": {
            "tokens": budget.reference_window_tokens,
            "label": budget.reference_window_label,
        },
        "session_start_total_tokens": budget.session_start_total,
        "session_start_percent_of_window": round(budget.percent_of_window, 3),
        "categories": [asdict(c) for c in budget.categories],
        "files": [asdict(f) for f in budget.files],
        "findings": [asdict(f) for f in sorted(findings, key=Finding.sort_key)],
        "summary": {
            "errors": sum(1 for f in findings if f.severity == "error"),
            "warnings": sum(1 for f in findings if f.severity == "warning"),
            "info": sum(1 for f in findings if f.severity == "info"),
        },
    }
    json.dump(payload, out, indent=2, ensure_ascii=False)
    out.write("\n")

"""Context budget: count tokens for everything Claude loads at session start.

The headline metric is the sum of tokens for CLAUDE.md + every agent +
every skill + every rule — that is the fixed cost paid on every single
Claude Code session in the project.
"""

from __future__ import annotations

from dataclasses import dataclass

from claude_config_auditor.scanner import FileRecord, Scan
from claude_config_auditor.tokens import Estimator


# Reference context window we compare against. Claude 4.x models advertise
# 200k as the standard context window for Claude Code (1M is opt-in and not
# default for most users). We use 200k as the baseline and label it in the
# report. The brief (section 10) explicitly requires labeling.
REFERENCE_WINDOW_TOKENS = 200_000
REFERENCE_WINDOW_LABEL = "200k (typical Claude Code default)"

# How many "largest files" to surface in the terminal and HTML reports.
# HTML provides an expand-to-see-rest control for everything beyond this.
TOP_FILES = 20


@dataclass
class FileTokens:
    relpath: str
    tokens: int
    bytes: int
    category: str  # "claude.md" | "agent" | "skill" | "rule"


@dataclass
class CategoryTotal:
    name: str
    file_count: int
    total_tokens: int


@dataclass
class BudgetReport:
    estimator_method: str
    estimator_note: str
    reference_window_tokens: int
    reference_window_label: str
    files: list[FileTokens]
    categories: list[CategoryTotal]
    session_start_total: int

    @property
    def percent_of_window(self) -> float:
        if self.reference_window_tokens <= 0:
            return 0.0
        return 100.0 * self.session_start_total / self.reference_window_tokens

    @property
    def tokens_by_path(self) -> dict[str, int]:
        """Lookup table so downstream checks don't reinvoke the tokenizer."""
        return {f.relpath: f.tokens for f in self.files}


def compute(scan: Scan, estimator: Estimator) -> BudgetReport:
    files: list[FileTokens] = []

    def add(records: list[FileRecord], category: str) -> CategoryTotal:
        cat_total = 0
        for rec in records:
            tokens = estimator.count(rec.raw)
            files.append(
                FileTokens(
                    relpath=rec.relpath,
                    tokens=tokens,
                    bytes=rec.size_bytes,
                    category=category,
                )
            )
            cat_total += tokens
        return CategoryTotal(name=category, file_count=len(records), total_tokens=cat_total)

    categories = [
        add(scan.claude_md_files, "claude.md"),
        add(scan.agents, "agent"),
        add(scan.skills, "skill"),
        add(scan.rules, "rule"),
    ]
    session_start = sum(c.total_tokens for c in categories)

    # Sort files by tokens desc — most expensive first, matches brief 5.5.2.
    files.sort(key=lambda f: f.tokens, reverse=True)

    return BudgetReport(
        estimator_method=estimator.method,
        estimator_note=estimator.note,
        reference_window_tokens=REFERENCE_WINDOW_TOKENS,
        reference_window_label=REFERENCE_WINDOW_LABEL,
        files=files,
        categories=categories,
        session_start_total=session_start,
    )

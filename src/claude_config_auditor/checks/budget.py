"""Context budget: count tokens and distinguish what Claude actually loads
at session start from what waits to be invoked.

For each file we now track two numbers:

  eager_tokens   ─ pulled into the main session at startup.
                   CLAUDE.md and rule files contribute their full body;
                   agent and skill files contribute only their YAML
                   frontmatter (the name + description that Claude uses
                   to route).
  lazy_tokens    ─ loaded on demand: agent and skill *bodies*. These
                   never enter the main session — when invoked, an
                   agent runs in its own sub-session, and a skill is
                   read at use time.

This split matters because the previous "session-start cost" metric
summed all four categories naively, which dramatically overstated the
real per-session load (often by 8×). The headline metric is now the
eager-load total; the lazy total is reported alongside as
"on-demand weight" so it is not lost.

Confidence note: this split is the auditor's best estimate based on
the publicly documented Claude Code loading model
(skills register their description; subagents are isolated). If
Anthropic changes the runtime, the split will need updating.
"""

from __future__ import annotations

from dataclasses import dataclass

from claude_config_auditor.scanner import FileRecord, Scan
from claude_config_auditor.tokens import Estimator


# Reference context window we compare against. Claude 4.x models advertise
# 200k as the standard context window for Claude Code (1M is opt-in and not
# default for most users). We use 200k as the baseline and label it in the
# report.
REFERENCE_WINDOW_TOKENS = 200_000
REFERENCE_WINDOW_LABEL = "200k (typical Claude Code default)"

# How many "largest files" to surface in the terminal and HTML reports.
# HTML provides an expand-to-see-rest control for everything beyond this.
TOP_FILES = 20

# Categories whose entire file content is loaded into the main session at
# startup. For the other categories (agent, skill) only the frontmatter
# is loaded eagerly; the body is on-demand.
_FULLY_EAGER_CATEGORIES = {"claude.md", "rule"}

# Categories whose content never appears in the main session: it is only
# pulled in when the user explicitly invokes it. Slash commands behave
# this way — they exist on disk but nothing is loaded until the user
# types `/<name>`. Tracked separately so totals stay honest.
_FULLY_LAZY_CATEGORIES = {"command"}


@dataclass
class FileTokens:
    relpath: str
    tokens: int          # total file weight (eager + lazy)
    eager_tokens: int    # paid on every session start
    lazy_tokens: int     # paid only when this agent/skill is invoked
    bytes: int
    category: str        # "claude.md" | "agent" | "skill" | "rule"


@dataclass
class CategoryTotal:
    name: str
    file_count: int
    total_tokens: int        # backward-compatible alias for eager + lazy
    eager_tokens: int
    lazy_tokens: int


@dataclass
class BudgetReport:
    estimator_method: str
    estimator_note: str
    reference_window_tokens: int
    reference_window_label: str
    files: list[FileTokens]
    categories: list[CategoryTotal]
    eager_load_total: int       # what Claude actually loads at session start
    on_demand_total: int        # agent/skill bodies, loaded when invoked
    total_config_tokens: int    # eager + on-demand — useful as a "package weight"

    # Kept for backward compatibility with older callers and JSON consumers.
    # New code should prefer eager_load_total / on_demand_total.
    @property
    def session_start_total(self) -> int:
        return self.eager_load_total

    @property
    def percent_of_window(self) -> float:
        """Window occupation is driven by *eager* load — the bytes
        that actually compete for context-window space at startup."""
        if self.reference_window_tokens <= 0:
            return 0.0
        return 100.0 * self.eager_load_total / self.reference_window_tokens

    @property
    def tokens_by_path(self) -> dict[str, int]:
        """Lookup table keyed by relpath. Returns *total* file tokens
        (eager + lazy) — the size relevant to per-file bloat checks."""
        return {f.relpath: f.tokens for f in self.files}

    @property
    def eager_tokens_by_path(self) -> dict[str, int]:
        """Per-file eager footprint — the slice that competes for context
        window space at session start. For agents and skills this is just
        the YAML frontmatter; for CLAUDE.md and rules it equals the total."""
        return {f.relpath: f.eager_tokens for f in self.files}


def _split_eager_lazy(rec: FileRecord, category: str, estimator: Estimator) -> tuple[int, int, int]:
    """Return (total_tokens, eager_tokens, lazy_tokens) for one file.

    Rules:
      - claude.md / rule  → fully eager.
      - agent / skill     → frontmatter eager, body lazy.
      - file with broken frontmatter → Claude cannot register it, so
        nothing eager-loads; the whole file sits as dead weight.
    """
    total = estimator.count(rec.raw)

    if category in _FULLY_EAGER_CATEGORIES:
        return total, total, 0

    if category in _FULLY_LAZY_CATEGORIES:
        return total, 0, total

    if not rec.frontmatter_ok:
        return total, 0, total

    # For agents/skills: rec.body holds the post-frontmatter content,
    # so frontmatter tokens = total minus body tokens. Clamped to 0
    # in case the tokenizer is mildly non-monotonic on edge cases.
    body_tokens = estimator.count(rec.body)
    eager = max(0, total - body_tokens)
    lazy = total - eager
    return total, eager, lazy


def compute(scan: Scan, estimator: Estimator) -> BudgetReport:
    files: list[FileTokens] = []

    def add(records: list[FileRecord], category: str) -> CategoryTotal:
        cat_total = 0
        cat_eager = 0
        cat_lazy = 0
        for rec in records:
            total, eager, lazy = _split_eager_lazy(rec, category, estimator)
            files.append(
                FileTokens(
                    relpath=rec.relpath,
                    tokens=total,
                    eager_tokens=eager,
                    lazy_tokens=lazy,
                    bytes=rec.size_bytes,
                    category=category,
                )
            )
            cat_total += total
            cat_eager += eager
            cat_lazy += lazy
        return CategoryTotal(
            name=category,
            file_count=len(records),
            total_tokens=cat_total,
            eager_tokens=cat_eager,
            lazy_tokens=cat_lazy,
        )

    categories = [
        add(scan.claude_md_files, "claude.md"),
        add(scan.agents, "agent"),
        add(scan.skills, "skill"),
        add(scan.rules, "rule"),
        add(scan.commands, "command"),
    ]
    eager_total = sum(c.eager_tokens for c in categories)
    lazy_total = sum(c.lazy_tokens for c in categories)

    # Sort files by total tokens desc — same as before: the largest files
    # are still the prime targets for trimming, regardless of when they load.
    files.sort(key=lambda f: f.tokens, reverse=True)

    return BudgetReport(
        estimator_method=estimator.method,
        estimator_note=estimator.note,
        reference_window_tokens=REFERENCE_WINDOW_TOKENS,
        reference_window_label=REFERENCE_WINDOW_LABEL,
        files=files,
        categories=categories,
        eager_load_total=eager_total,
        on_demand_total=lazy_total,
        total_config_tokens=eager_total + lazy_total,
    )

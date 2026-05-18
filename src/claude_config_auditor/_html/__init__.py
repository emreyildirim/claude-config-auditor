"""Self-contained HTML dashboard renderer.

Design intent: a real analysis tool report — pragmatic, data-dense,
scannable. Closer in spirit to Lighthouse / Datadog / Vercel Analytics
than to a magazine layout. Color is reserved for severity signal;
typography is monospace where it carries data, sans-serif everywhere
else; no decoration.

No network, no external fonts, no JS library. The file opens offline.

Internals split across this package to keep each piece editable:

    _style.py     ─ the CSS string
    _template.py  ─ the HTML page template + theme-toggle script
    _sections.py  ─ the renderers for each section of the report
"""

from __future__ import annotations

import hashlib
import html
from datetime import datetime
from typing import IO

from claude_config_auditor import __version__
from claude_config_auditor.checks.budget import BudgetReport
from claude_config_auditor.findings import Finding

from ._sections import (
    _categories_table,
    _consumers_table,
    _findings_section,
    _kpis,
    _overall_severity,
    _utilization,
)
from ._style import _CSS
from ._template import _PAGE

__all__ = ["render_html"]


def render_html(
    *,
    target: str,
    budget: BudgetReport,
    findings: list[Finding],
    out: IO[str],
) -> None:
    """Write a complete self-contained HTML report to `out`.

    `target` is shown verbatim in the page header; it is not used to
    read anything from disk. All audit data has already been gathered
    by the caller into `budget` and `findings`.
    """
    findings_sorted = sorted(findings, key=Finding.sort_key)
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings_sorted:
        counts[f.severity] += 1

    pct = budget.percent_of_window
    severity_key = _overall_severity(pct, counts)
    # Deterministic per-target id so re-runs from the same path share a code.
    report_id = hashlib.sha1(target.encode("utf-8")).hexdigest()[:8].upper()

    parts = {
        "title": html.escape(f"Audit · {target}"),
        "css": _CSS,
        "report_id": report_id,
        "version": __version__,
        "generated_at": datetime.now().strftime("%Y-%m-%d · %H:%M"),
        "subject": html.escape(target),
        "tokenizer": html.escape(budget.estimator_method),
        "tokenizer_note": html.escape(budget.estimator_note),
        "kpis": _kpis(budget, counts),
        "utilization": _utilization(budget),
        "categories": _categories_table(budget),
        "consumers": _consumers_table(budget.files),
        "findings": _findings_section(findings_sorted, counts),
        "doc_severity_class": f"doc--{severity_key}",
    }
    out.write(_PAGE.format(**parts))

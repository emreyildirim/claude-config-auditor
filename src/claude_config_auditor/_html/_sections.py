"""HTML section renderers.

Each `_*` function in this module returns the HTML for one section of
the report. The main entry (_html.__init__.render_html) stitches them
into the template. Keeping them here means scrolling past 750 lines of
CSS or 90 lines of template chrome isn't a prerequisite to editing the
data-rendering logic.
"""

from __future__ import annotations

import html

from claude_config_auditor.checks.budget import (
    TOP_FILES,
    BudgetReport,
    FileTokens,
)
from claude_config_auditor.findings import Finding


# Plain-language explanations attached as hover tooltips. Kept here so
# the words live next to the section they describe — easier to keep
# them honest as the implementation changes.
_TIPS = {
    "session_start_cost": (
        "Tokens Claude Code loads into memory the instant a session opens "
        "in this project — CLAUDE.md plus every agent, skill, and rule. "
        "You pay this on every single session before you type a word."
    ),
    "window_occupation": (
        "How much of Claude's 200,000-token context window your config "
        "consumes just to start. Below 25% is healthy; above 100% means "
        "there is no room left for the conversation, code, or files you "
        "actually want to work with."
    ),
    "files_tracked": (
        "Total configuration files the auditor read, broken down by type. "
        "Skills, agents, and rules live under .claude/; CLAUDE.md files "
        "can sit at the project root or nested inside subprojects."
    ),
    "issues": (
        "Quality findings the auditor surfaced. Errors are blocking — "
        "Claude cannot use these correctly. Warnings cause routing or "
        "budget problems. Advisories are worth considering but not urgent."
    ),
    "window_utilization": (
        "Shows how each configuration category contributes to your "
        "context-window load. The dashed line at 100% is the window "
        "limit; any segment past that line is config that will not fit "
        "alongside your actual work."
    ),
    "categories": (
        "Token breakdown by configuration source. 'Share' is the "
        "percentage each type contributes to your total session-start "
        "cost — useful for spotting where to trim first."
    ),
    "top_consumers": (
        "The single files costing you the most tokens, sorted largest "
        "to smallest. These are usually the best places to start when "
        "you need to claw context-window space back."
    ),
    "findings": (
        "Quality issues the auditor detected, grouped by severity. Each "
        "finding has a stable code (AGT001, SKL002, HLT003, etc.) so "
        "you can grep for it or look it up later."
    ),
}


def _info(tip_key: str) -> str:
    """Render a small ⓘ button that reveals a tooltip on hover/focus/tap.

    Implemented as a `<button>` so it is reachable by keyboard. The
    actual show/hide is driven by CSS for hover and `:focus-visible`;
    the inline `<script>` near the page footer toggles a `data-open`
    attribute on tap (for touch devices that have no hover state).
    """
    text = _TIPS[tip_key]
    return (
        f'<button class="info" type="button" '
        f'aria-label="{html.escape(text)}" data-info="{html.escape(tip_key)}">'
        f'<span class="info-mark" aria-hidden="true">?</span>'
        f'<span class="info-tip" role="tooltip">{html.escape(text)}</span>'
        f'</button>'
    )


def _kpis(budget: BudgetReport, counts: dict) -> str:
    pct = budget.percent_of_window
    over = budget.session_start_total - budget.reference_window_tokens
    total_findings = sum(counts.values())
    file_count = len(budget.files)
    inventory = ", ".join(
        f"{c.file_count} {c.name}"
        for c in budget.categories
        if c.file_count > 0
    )

    # KPI 1 — session-start cost. Severity neutral; it's just the number.
    kpi_cost = _kpi(
        label="Session-start cost",
        value=f"{budget.session_start_total:,}",
        unit="tok",
        sub="paid on every Claude Code session",
        sev="neutral",
        tip="session_start_cost",
    )

    # KPI 2 — window occupation, severity-coloured.
    if pct >= 100:
        sev = "critical"
        sub = f"+{over:,} tokens over the {budget.reference_window_tokens:,} window"
    elif pct >= 25:
        sev = "warning"
        sub = f"{budget.reference_window_tokens - budget.session_start_total:,} tokens of headroom"
    elif pct >= 10:
        sev = "info"
        sub = f"{budget.reference_window_tokens - budget.session_start_total:,} tokens of headroom"
    else:
        sev = "ok"
        sub = f"{budget.reference_window_tokens - budget.session_start_total:,} tokens of headroom"

    kpi_window = _kpi(
        label="Window occupation",
        value=f"{pct:.1f}",
        unit="%",
        sub=sub,
        sev=sev,
        tip="window_occupation",
    )

    # KPI 3 — inventory. Always neutral.
    kpi_files = _kpi(
        label="Files tracked",
        value=f"{file_count}",
        unit="",
        sub=inventory or "no configuration files found",
        sev="neutral",
        tip="files_tracked",
    )

    # KPI 4 — findings. Severity from highest present.
    if counts["error"]:
        fsev = "critical"
    elif counts["warning"]:
        fsev = "warning"
    elif counts["info"]:
        fsev = "info"
    else:
        fsev = "ok"

    issues_breakdown = (
        f'<span class="sev sev-error">{counts["error"]}</span> error · '
        f'<span class="sev sev-warning">{counts["warning"]}</span> warning · '
        f'<span class="sev sev-info">{counts["info"]}</span> advisory'
    )
    kpi_issues = _kpi(
        label="Issues",
        value=f"{total_findings}",
        unit="",
        sub=issues_breakdown,
        sev=fsev,
        sub_is_html=True,
        tip="issues",
    )

    return f'<section class="kpis">{kpi_cost}{kpi_window}{kpi_files}{kpi_issues}</section>'


def _kpi(*, label: str, value: str, unit: str, sub: str, sev: str,
         sub_is_html: bool = False, tip: str | None = None) -> str:
    unit_html = (
        f'<span class="kpi-unit">{html.escape(unit)}</span>' if unit else ""
    )
    sub_html = sub if sub_is_html else html.escape(sub)
    info_button = _info(tip) if tip else ""
    return f'''
      <article class="kpi kpi--{sev}">
        <header class="kpi-label">
          <span>{html.escape(label)}</span>
          {info_button}
        </header>
        <div class="kpi-value">{html.escape(value)}{unit_html}</div>
        <div class="kpi-sub">{sub_html}</div>
        <div class="kpi-strip"></div>
      </article>
    '''


# --- Utilization chart ------------------------------------------------------

def _utilization(budget: BudgetReport) -> str:
    """Stacked horizontal bar showing how each category fills the window.

    The 100% mark is a real visual wall; bars continue past it into a red
    overflow zone when the configuration is over budget. The point is that
    overrun is unmissable, while still showing the contribution of each
    category.
    """
    window_tok = budget.reference_window_tokens
    total = budget.session_start_total
    pct_total = budget.percent_of_window

    # Geometry: viewBox 1000 wide. x=40 is bar start, x=740 is 100%, max bar
    # end at x=940 (representing ~128% past window — beyond that we'll just
    # clip the bar but still report the number).
    bar_x = 40
    pct_to_x = 7.0  # 1% = 7 SVG units
    limit_x = bar_x + 100 * pct_to_x  # 740
    max_x = 940

    segments_svg = []
    legend_rows = []
    cum_pct = 0.0  # cumulative percent of window consumed so far
    categories = [c for c in budget.categories if c.file_count > 0]

    for cat in categories:
        if cat.total_tokens == 0:
            continue
        seg_pct_of_window = 100.0 * cat.total_tokens / window_tok
        seg_pct_of_total = 100.0 * cat.total_tokens / max(total, 1)

        # Compute pixel span; split into in-window and over-window portions.
        start_pct = cum_pct
        end_pct = cum_pct + seg_pct_of_window
        start_x = bar_x + start_pct * pct_to_x
        end_x = min(bar_x + end_pct * pct_to_x, max_x)

        slug = cat.name.replace(".", "-")
        # Split if the segment straddles the 100% wall.
        if start_x < limit_x and end_x > limit_x:
            segments_svg.append(
                f'<rect x="{start_x:.1f}" y="60" width="{limit_x - start_x:.1f}" '
                f'height="40" class="util-seg util-seg--{slug}"/>'
            )
            segments_svg.append(
                f'<rect x="{limit_x:.1f}" y="60" width="{end_x - limit_x:.1f}" '
                f'height="40" class="util-seg util-seg--{slug} util-seg--over"/>'
            )
        elif start_x >= limit_x:
            segments_svg.append(
                f'<rect x="{start_x:.1f}" y="60" width="{end_x - start_x:.1f}" '
                f'height="40" class="util-seg util-seg--{slug} util-seg--over"/>'
            )
        else:
            segments_svg.append(
                f'<rect x="{start_x:.1f}" y="60" width="{end_x - start_x:.1f}" '
                f'height="40" class="util-seg util-seg--{slug}"/>'
            )
        cum_pct = end_pct

        legend_rows.append(f'''
          <div class="leg-row">
            <span class="leg-swatch leg-swatch--{slug}"></span>
            <span class="leg-name">{html.escape(cat.name)}</span>
            <span class="leg-files">{cat.file_count} files</span>
            <span class="leg-pct">{seg_pct_of_total:.1f}%</span>
            <span class="leg-tok">{cat.total_tokens:,}</span>
          </div>
        ''')

    # Ticks every 25%.
    ticks_svg = []
    for tp in (0, 25, 50, 75, 100):
        x = bar_x + tp * pct_to_x
        ticks_svg.append(f'<line x1="{x}" y1="100" x2="{x}" y2="108" class="util-tick"/>')
        ticks_svg.append(
            f'<text x="{x}" y="122" class="util-tick-label" text-anchor="middle">'
            f'{tp}%</text>'
        )

    # 100% wall. Label sits to the LEFT of the wall so it never collides
    # with the overflow label when the bar runs past 100%.
    wall = f'''
      <line x1="{limit_x}" y1="44" x2="{limit_x}" y2="108" class="util-wall"/>
      <text x="{limit_x - 6}" y="34" class="util-wall-label" text-anchor="end">
        {window_tok // 1000}K · LIMIT
      </text>
    '''

    # Overflow label sits to the RIGHT of the wall, only when over budget.
    over_label = ""
    if pct_total > 100:
        over_label = f'''
          <text x="{limit_x + 6}" y="34" class="util-over-label" text-anchor="start">
            +{pct_total - 100:.1f} pp OVER
          </text>
        '''

    return f'''
    <section class="panel">
      <header class="panel-h">
        <h2>Window utilization{_info("window_utilization")}</h2>
        <span class="panel-sub">
          stacked contribution to the {window_tok:,}-token reference window
        </span>
      </header>
      <div class="util-chart">
        <svg viewBox="0 0 1000 140" preserveAspectRatio="xMidYMid meet"
             role="img" aria-label="Context window utilization">
          {''.join(ticks_svg)}
          {wall}
          {over_label}
          {''.join(segments_svg)}
          <line x1="{bar_x}" y1="100" x2="{max_x}" y2="100" class="util-baseline"/>
        </svg>
      </div>
      <div class="util-legend">{''.join(legend_rows)}</div>
    </section>
    '''


# --- Categories table ------------------------------------------------------

def _categories_table(budget: BudgetReport) -> str:
    cats = [c for c in budget.categories if c.file_count > 0]
    if not cats:
        return ""
    total = sum(c.total_tokens for c in cats) or 1
    max_tok = max(c.total_tokens for c in cats)
    rows = []
    for c in cats:
        slug = c.name.replace(".", "-")
        share = 100 * c.total_tokens / total
        bar = 100 * c.total_tokens / max_tok
        rows.append(f'''
          <tr>
            <td class="t-cat">
              <span class="leg-swatch leg-swatch--{slug}"></span>
              {html.escape(c.name)}
            </td>
            <td class="t-num">{c.file_count}</td>
            <td class="t-bar">
              <span class="row-bar row-bar--{slug}" style="width:{bar:.1f}%"></span>
            </td>
            <td class="t-num t-num-pct">{share:.1f}%</td>
            <td class="t-num t-num-tok">{c.total_tokens:,}</td>
          </tr>''')
    return f'''
    <section class="panel">
      <header class="panel-h">
        <h2>Categories{_info("categories")}</h2>
        <span class="panel-sub">token share by configuration source</span>
      </header>
      <table class="dt">
        <thead>
          <tr>
            <th class="t-cat">Source</th>
            <th class="t-num">Files</th>
            <th class="t-bar">Share</th>
            <th class="t-num t-num-pct">%</th>
            <th class="t-num t-num-tok">Tokens</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    '''


# --- Top consumers ---------------------------------------------------------

def _consumers_table(files: list[FileTokens]) -> str:
    if not files:
        return ""
    max_tok = max(f.tokens for f in files) or 1

    def _row(i: int, f: FileTokens) -> str:
        slug = f.category.replace(".", "-")
        bar = 100 * f.tokens / max_tok
        return f'''
          <tr>
            <td class="t-rank">{i:03d}</td>
            <td class="t-path"><code>{html.escape(f.relpath)}</code></td>
            <td class="t-cat-small">
              <span class="cat-tag cat-tag--{slug}">{html.escape(f.category)}</span>
            </td>
            <td class="t-bar">
              <span class="row-bar row-bar--{slug}" style="width:{bar:.1f}%"></span>
            </td>
            <td class="t-num t-num-tok">{f.tokens:,}</td>
          </tr>'''

    head = '''
        <thead>
          <tr>
            <th class="t-rank">№</th>
            <th class="t-path">Path</th>
            <th class="t-cat-small">Type</th>
            <th class="t-bar">Size</th>
            <th class="t-num t-num-tok">Tokens</th>
          </tr>
        </thead>
    '''

    top = files[:TOP_FILES]
    rest = files[TOP_FILES:]
    top_rows = "".join(_row(i, f) for i, f in enumerate(top, 1))

    rest_block = ""
    if rest:
        rest_rows = "".join(_row(i, f) for i, f in enumerate(rest, TOP_FILES + 1))
        rest_block = f'''
          <details class="expand">
            <summary class="expand-summary">
              <span class="expand-toggle" aria-hidden="true"></span>
              <span class="expand-label">Show remaining {len(rest)} file(s)</span>
              <span class="expand-hint">{len(files)} total</span>
            </summary>
            <table class="dt dt--files dt--continuation">
              {head}
              <tbody>{rest_rows}</tbody>
            </table>
          </details>
        '''

    return f'''
    <section class="panel">
      <header class="panel-h">
        <h2>Top consumers{_info("top_consumers")}</h2>
        <span class="panel-sub">
          largest files by estimated token cost · {len(files)} file(s) total
        </span>
      </header>
      <table class="dt dt--files">
        {head}
        <tbody>{top_rows}</tbody>
      </table>
      {rest_block}
    </section>
    '''


# --- Findings --------------------------------------------------------------

def _findings_section(findings: list[Finding], counts: dict) -> str:
    if not findings:
        return f'''
        <section class="panel">
          <header class="panel-h">
            <h2>Findings{_info("findings")}</h2>
            <span class="panel-sub">no issues detected</span>
          </header>
          <div class="all-clear">
            <span class="all-clear-mark">✓</span>
            <div>
              <strong>All checks passed.</strong>
              <span>No errors, warnings, or advisories.</span>
            </div>
          </div>
        </section>
        '''

    by_sev = {"error": [], "warning": [], "info": []}
    for f in findings:
        by_sev[f.severity].append(f)

    groups = []
    sev_titles = {
        "error": ("Errors", "blocking issues that must be fixed"),
        "warning": ("Warnings", "likely to cause routing or budget problems"),
        "info": ("Advisories", "things to consider but not urgent"),
    }
    for sev in ("error", "warning", "info"):
        items = by_sev[sev]
        if not items:
            continue
        title, blurb = sev_titles[sev]
        rendered = []
        for f in items:
            file_part = (
                f'<code class="f-path">{html.escape(f.file)}</code>'
                if f.file
                else '<span class="f-path f-path--none">project-wide</span>'
            )
            hint = (
                f'<div class="f-hint">{html.escape(f.hint)}</div>'
                if f.hint else ""
            )
            rendered.append(f'''
              <li class="f f--{sev}">
                <div class="f-bullet" aria-hidden="true"></div>
                <div class="f-code"><code>{html.escape(f.code)}</code></div>
                <div class="f-body">
                  <div class="f-msg">{html.escape(f.message)}</div>
                  {file_part}
                  {hint}
                </div>
              </li>''')
        groups.append(f'''
          <div class="f-group f-group--{sev}">
            <div class="f-group-h">
              <span class="f-group-sev sev sev-{sev}">{sev}</span>
              <span class="f-group-title">{title}</span>
              <span class="f-group-blurb">{blurb}</span>
              <span class="f-group-count">{len(items)}</span>
            </div>
            <ul class="f-list">{''.join(rendered)}</ul>
          </div>
        ''')

    return f'''
    <section class="panel">
      <header class="panel-h">
        <h2>Findings{_info("findings")}</h2>
        <span class="panel-sub">
          {counts['error']} error · {counts['warning']} warning · {counts['info']} advisory
        </span>
      </header>
      {''.join(groups)}
    </section>
    '''


# --- Helpers ----------------------------------------------------------------

def _overall_severity(pct: float, counts: dict) -> str:
    if pct >= 100 or counts["error"] > 0:
        return "critical"
    if pct >= 25 or counts["warning"] > 0:
        return "warning"
    if pct >= 10 or counts["info"] > 0:
        return "info"
    return "ok"

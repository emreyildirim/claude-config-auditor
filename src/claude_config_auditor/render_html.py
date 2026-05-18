"""Self-contained HTML dashboard.

Design intent: a real analysis tool report — pragmatic, data-dense,
scannable. Closer in spirit to Lighthouse / Datadog / Vercel Analytics
than to a magazine layout. Color is reserved for severity signal;
typography is monospace where it carries data, sans-serif everywhere
else; no decoration.

No network, no external fonts, no JS. The file opens offline.
"""

from __future__ import annotations

import hashlib
import html
from datetime import datetime
from typing import IO

from claude_config_auditor import __version__
from claude_config_auditor.checks.budget import (
    TOP_FILES,
    BudgetReport,
    CategoryTotal,
    FileTokens,
)
from claude_config_auditor.findings import Finding


def render_html(
    *,
    target: str,
    budget: BudgetReport,
    findings: list[Finding],
    out: IO[str],
) -> None:
    findings_sorted = sorted(findings, key=Finding.sort_key)
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings_sorted:
        counts[f.severity] += 1

    pct = budget.percent_of_window
    severity_key = _overall_severity(pct, counts)
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


# --- KPI cards --------------------------------------------------------------

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
    )

    # KPI 3 — inventory. Always neutral.
    kpi_files = _kpi(
        label="Files tracked",
        value=f"{file_count}",
        unit="",
        sub=inventory or "no configuration files found",
        sev="neutral",
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
    )

    return f'<section class="kpis">{kpi_cost}{kpi_window}{kpi_files}{kpi_issues}</section>'


def _kpi(*, label: str, value: str, unit: str, sub: str, sev: str,
         sub_is_html: bool = False) -> str:
    unit_html = (
        f'<span class="kpi-unit">{html.escape(unit)}</span>' if unit else ""
    )
    sub_html = sub if sub_is_html else html.escape(sub)
    return f'''
      <article class="kpi kpi--{sev}">
        <header class="kpi-label">{html.escape(label)}</header>
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
        <h2>Window utilization</h2>
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
        <h2>Categories</h2>
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
        <h2>Top consumers</h2>
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
        return '''
        <section class="panel">
          <header class="panel-h">
            <h2>Findings</h2>
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
        <h2>Findings</h2>
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


# --- CSS --------------------------------------------------------------------

_CSS = r"""
/* ============ Theme tokens ============
   :root holds the light theme. Dark theme overrides via either
   [data-theme="dark"] (manual override) or @media prefers-color-scheme.
   ===================================== */
:root {
  --bg: #f7f6f3;
  --surface: #ffffff;
  --surface-alt: #fbfaf7;
  --border: #e6e3dc;
  --border-strong: #cfccc3;
  --border-faint: #efece5;

  --ink-1: #0c0c0b;
  --ink-2: #4d4b46;
  --ink-3: #8a8780;
  --ink-4: #b4b1a8;

  --critical: #cc2c1f;
  --critical-bg: #fdedea;
  --critical-line: #f0c0b9;
  --warning: #b87618;
  --warning-bg: #fbf3e3;
  --warning-line: #e9d4a4;
  --info: #1f5ec0;
  --info-bg: #ebf1fb;
  --info-line: #c2d2ee;
  --ok: #1d7a45;
  --ok-bg: #e8f3ec;
  --ok-line: #b8d8c2;

  --cat-claude-md: #2b6358;
  --cat-claude-md-bg: rgba(43, 99, 88, 0.12);
  --cat-agent: #6b3a18;
  --cat-agent-bg: rgba(107, 58, 24, 0.12);
  --cat-skill: #2e4b86;
  --cat-skill-bg: rgba(46, 75, 134, 0.12);
  --cat-rule: #6a2e54;
  --cat-rule-bg: rgba(106, 46, 84, 0.12);

  --sans: "SF Pro Text", -apple-system, BlinkMacSystemFont, system-ui,
          "Segoe UI", "Helvetica Neue", sans-serif;
  --mono: "JetBrains Mono", "SF Mono", "Cascadia Mono", Menlo, Consolas,
          ui-monospace, monospace;

  color-scheme: light;
}

/* Dark — applied when user OS prefers dark AND no manual override,
   OR when manual override sets dark explicitly. */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0d1014;
    --surface: #161a21;
    --surface-alt: #1a1f28;
    --border: #262c37;
    --border-strong: #353c4a;
    --border-faint: #1f242d;

    --ink-1: #e9ecf1;
    --ink-2: #a3a9b6;
    --ink-3: #6c7484;
    --ink-4: #4d5462;

    --critical: #ff5b62;
    --critical-bg: rgba(255, 91, 98, 0.12);
    --critical-line: rgba(255, 91, 98, 0.3);
    --warning: #f3b04a;
    --warning-bg: rgba(243, 176, 74, 0.12);
    --warning-line: rgba(243, 176, 74, 0.3);
    --info: #5fa3ff;
    --info-bg: rgba(95, 163, 255, 0.12);
    --info-line: rgba(95, 163, 255, 0.3);
    --ok: #5ad095;
    --ok-bg: rgba(90, 208, 149, 0.12);
    --ok-line: rgba(90, 208, 149, 0.3);

    --cat-claude-md: #6dc9b3;
    --cat-claude-md-bg: rgba(109, 201, 179, 0.15);
    --cat-agent: #e09368;
    --cat-agent-bg: rgba(224, 147, 104, 0.15);
    --cat-skill: #7fa9e8;
    --cat-skill-bg: rgba(127, 169, 232, 0.15);
    --cat-rule: #d68caf;
    --cat-rule-bg: rgba(214, 140, 175, 0.15);

    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0d1014;
  --surface: #161a21;
  --surface-alt: #1a1f28;
  --border: #262c37;
  --border-strong: #353c4a;
  --border-faint: #1f242d;

  --ink-1: #e9ecf1;
  --ink-2: #a3a9b6;
  --ink-3: #6c7484;
  --ink-4: #4d5462;

  --critical: #ff5b62;
  --critical-bg: rgba(255, 91, 98, 0.12);
  --critical-line: rgba(255, 91, 98, 0.3);
  --warning: #f3b04a;
  --warning-bg: rgba(243, 176, 74, 0.12);
  --warning-line: rgba(243, 176, 74, 0.3);
  --info: #5fa3ff;
  --info-bg: rgba(95, 163, 255, 0.12);
  --info-line: rgba(95, 163, 255, 0.3);
  --ok: #5ad095;
  --ok-bg: rgba(90, 208, 149, 0.12);
  --ok-line: rgba(90, 208, 149, 0.3);

  --cat-claude-md: #6dc9b3;
  --cat-claude-md-bg: rgba(109, 201, 179, 0.15);
  --cat-agent: #e09368;
  --cat-agent-bg: rgba(224, 147, 104, 0.15);
  --cat-skill: #7fa9e8;
  --cat-skill-bg: rgba(127, 169, 232, 0.15);
  --cat-rule: #d68caf;
  --cat-rule-bg: rgba(214, 140, 175, 0.15);

  color-scheme: dark;
}

* { box-sizing: border-box; }
html { font-size: 16px; -webkit-font-smoothing: antialiased; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink-1);
  font-family: var(--sans);
  font-size: 13.5px;
  line-height: 1.55;
  font-feature-settings: "kern", "liga", "ss01";
  font-variant-numeric: tabular-nums;
}

.doc {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px 32px 64px;
}

/* ============ Top bar ============ */
.topbar {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 24px;
  align-items: center;
  padding: 16px 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  margin-bottom: 20px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--mono);
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: var(--ink-1);
}
.brand-mark {
  width: 18px; height: 18px;
  display: inline-grid; place-items: center;
  background: var(--ink-1);
  color: var(--bg);
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  border-radius: 2px;
  line-height: 1;
}
.topbar-path {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-2);
  word-break: break-all;
  padding: 4px 10px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  border-radius: 3px;
  justify-self: start;
}
.topbar-meta {
  display: flex;
  gap: 18px;
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.04em;
  color: var(--ink-3);
}
.topbar-meta span strong {
  color: var(--ink-2);
  font-weight: 600;
}
.theme-toggle {
  background: var(--surface-alt);
  border: 1px solid var(--border);
  color: var(--ink-2);
  width: 30px; height: 30px;
  display: inline-grid; place-items: center;
  cursor: pointer;
  border-radius: 3px;
  font-family: var(--mono);
  font-size: 14px;
  line-height: 1;
  padding: 0;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.theme-toggle:hover {
  border-color: var(--border-strong);
  color: var(--ink-1);
}
.theme-toggle::before { content: attr(data-icon); }
.theme-toggle[data-theme="auto"] { color: var(--ink-3); }
.theme-toggle[data-theme="light"] { color: var(--warning); }
.theme-toggle[data-theme="dark"] { color: var(--info); }

/* ============ KPIs ============ */
.kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.kpi {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 16px 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 124px;
}
.kpi-label {
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--ink-3);
}
.kpi-value {
  font-family: var(--mono);
  font-size: 34px;
  font-weight: 500;
  letter-spacing: -0.02em;
  color: var(--ink-1);
  line-height: 1;
  margin-top: 2px;
  font-variant-numeric: tabular-nums lining-nums;
}
.kpi-unit {
  font-family: var(--mono);
  font-size: 14px;
  color: var(--ink-3);
  font-weight: 400;
  margin-left: 6px;
  letter-spacing: 0;
}
.kpi-sub {
  font-size: 12px;
  color: var(--ink-2);
  line-height: 1.45;
  margin-top: auto;
}
.kpi-strip {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  height: 3px;
  background: var(--border-strong);
}
.kpi--ok .kpi-strip { background: var(--ok); }
.kpi--info .kpi-strip { background: var(--info); }
.kpi--warning .kpi-strip { background: var(--warning); }
.kpi--critical .kpi-strip { background: var(--critical); }
.kpi--critical .kpi-value { color: var(--critical); }

/* ============ Panels ============ */
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  margin-bottom: 16px;
}
.panel-h {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-alt);
}
.panel-h h2 {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--ink-1);
}
.panel-sub {
  font-size: 11.5px;
  color: var(--ink-3);
}
.panel-foot {
  padding: 10px 20px;
  border-top: 1px solid var(--border);
  font-size: 11.5px;
  color: var(--ink-3);
  background: var(--surface-alt);
}

/* Expand block (top-consumers overflow) */
.expand {
  border-top: 1px solid var(--border);
  background: var(--surface);
}
.expand-summary {
  cursor: pointer;
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  font-size: 11.5px;
  letter-spacing: 0.04em;
  background: var(--surface-alt);
  border-bottom: 1px solid transparent;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.expand-summary::-webkit-details-marker { display: none; }
.expand-summary:hover {
  background: var(--surface);
  color: var(--ink-1);
}
.expand-summary:focus-visible {
  outline: 2px solid var(--info);
  outline-offset: -2px;
}
.expand-toggle {
  display: inline-block;
  width: 0; height: 0;
  border-style: solid;
  border-width: 5px 0 5px 8px;
  border-color: transparent transparent transparent var(--ink-3);
  transition: transform 0.18s ease;
  flex-shrink: 0;
}
.expand[open] .expand-toggle { transform: rotate(90deg); }
.expand[open] .expand-summary {
  border-bottom-color: var(--border);
  color: var(--ink-1);
  background: var(--surface);
}
.expand-label {
  font-family: var(--mono);
  color: var(--ink-2);
  font-size: 12px;
}
.expand[open] .expand-label { color: var(--ink-1); }
.expand-hint {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}
.dt--continuation thead {
  /* Continuation table — keep header subtle since it's a repeat */
}
.dt--continuation thead th {
  background: var(--surface);
  color: var(--ink-4);
  font-size: 9.5px;
}

/* ============ Utilization chart ============ */
.util-chart {
  padding: 20px 20px 8px;
}
.util-chart svg {
  width: 100%;
  height: auto;
  overflow: visible;
}
.util-baseline { stroke: var(--ink-1); stroke-width: 1; }
.util-tick { stroke: var(--ink-2); stroke-width: 1; }
.util-tick-label {
  font-family: var(--mono);
  font-size: 10px;
  fill: var(--ink-3);
}
.util-wall {
  stroke: var(--ink-1);
  stroke-width: 1.5;
  stroke-dasharray: 3 2;
}
.util-wall-label {
  font-family: var(--mono);
  font-size: 10.5px;
  fill: var(--ink-2);
  letter-spacing: 0.08em;
  font-weight: 600;
}
.util-over-label {
  font-family: var(--mono);
  font-size: 10.5px;
  fill: var(--critical);
  font-weight: 700;
  letter-spacing: 0.08em;
}
.util-seg { transition: opacity 0.15s; }
.util-seg:hover { opacity: 0.85; }
.util-seg--claude-md { fill: var(--cat-claude-md); }
.util-seg--agent { fill: var(--cat-agent); }
.util-seg--skill { fill: var(--cat-skill); }
.util-seg--rule { fill: var(--cat-rule); }
.util-seg--over { fill: var(--critical); }

.util-legend {
  padding: 12px 20px 18px;
  display: grid;
  gap: 4px;
}
.leg-row {
  display: grid;
  grid-template-columns: 14px 1fr 90px 60px 90px;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  font-size: 12.5px;
  border-bottom: 1px solid var(--border-faint);
}
.leg-row:last-child { border-bottom: none; }
.leg-swatch {
  display: inline-block;
  width: 10px; height: 10px;
  border-radius: 2px;
  vertical-align: middle;
  background: var(--ink-2);
}
.leg-swatch--claude-md { background: var(--cat-claude-md); }
.leg-swatch--agent { background: var(--cat-agent); }
.leg-swatch--skill { background: var(--cat-skill); }
.leg-swatch--rule { background: var(--cat-rule); }
.leg-name {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-1);
}
.leg-files {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
  text-align: right;
}
.leg-pct {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-2);
  text-align: right;
}
.leg-tok {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink-1);
  text-align: right;
  font-weight: 500;
}

/* ============ Data tables ============ */
.dt {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.dt thead th {
  text-align: left;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--ink-3);
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-alt);
}
.dt tbody td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-faint);
  vertical-align: middle;
}
.dt tbody tr:hover td { background: var(--surface-alt); }
.dt tbody tr:last-child td { border-bottom: none; }

.t-rank {
  width: 40px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.04em;
}
.t-cat {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink-1);
  width: 140px;
}
.t-cat-small { width: 80px; }
.t-path code {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink-1);
  background: transparent;
  word-break: break-all;
}
.t-num {
  text-align: right;
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink-1);
  white-space: nowrap;
}
.t-num-pct {
  width: 70px;
  color: var(--ink-2);
}
.t-num-tok {
  width: 100px;
  font-weight: 500;
}
.t-bar {
  width: 35%;
  padding-right: 18px;
}
th.t-num, th.t-num-pct, th.t-num-tok { text-align: right; }

.row-bar {
  display: block;
  height: 8px;
  background: var(--ink-1);
  border-radius: 1px;
}
.row-bar--claude-md { background: var(--cat-claude-md); }
.row-bar--agent { background: var(--cat-agent); }
.row-bar--skill { background: var(--cat-skill); }
.row-bar--rule { background: var(--cat-rule); }

.cat-tag {
  display: inline-block;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border: 1px solid currentColor;
  border-radius: 2px;
  text-transform: lowercase;
  background: transparent;
}
.cat-tag--claude-md { color: var(--cat-claude-md); background: var(--cat-claude-md-bg); border-color: transparent; }
.cat-tag--agent { color: var(--cat-agent); background: var(--cat-agent-bg); border-color: transparent; }
.cat-tag--skill { color: var(--cat-skill); background: var(--cat-skill-bg); border-color: transparent; }
.cat-tag--rule { color: var(--cat-rule); background: var(--cat-rule-bg); border-color: transparent; }

/* ============ Findings ============ */
.f-group { padding: 14px 20px 18px; border-bottom: 1px solid var(--border); }
.f-group:last-child { border-bottom: none; }
.f-group-h {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
}
.f-group-sev {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 2px;
}
.f-group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-1);
}
.f-group-blurb {
  font-size: 12px;
  color: var(--ink-3);
}
.f-group-count {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}

.f-list { list-style: none; padding: 0; margin: 0; }
.f {
  display: grid;
  grid-template-columns: 12px 88px 1fr;
  gap: 14px;
  padding: 12px 0;
  border-bottom: 1px dotted var(--border);
  align-items: start;
}
.f:last-child { border-bottom: none; }
.f-bullet {
  width: 5px; height: 5px;
  border-radius: 50%;
  margin-top: 8px;
  margin-left: 4px;
  background: var(--ink-3);
}
.f--error .f-bullet { background: var(--critical); }
.f--warning .f-bullet { background: var(--warning); }
.f--info .f-bullet { background: var(--info); }
.f-code code {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  border-radius: 2px;
  color: var(--ink-2);
  white-space: nowrap;
}
.f-body { min-width: 0; }
.f-msg {
  font-size: 13px;
  color: var(--ink-1);
  line-height: 1.5;
}
.f-path {
  display: inline-block;
  margin-top: 4px;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
  background: transparent;
  word-break: break-all;
}
.f-path--none { font-style: italic; }
.f-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--ink-2);
  padding-left: 14px;
  border-left: 2px solid var(--border-strong);
}

.sev {
  display: inline-block;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.sev-error { color: var(--critical); background: var(--critical-bg); }
.sev-warning { color: var(--warning); background: var(--warning-bg); }
.sev-info { color: var(--info); background: var(--info-bg); }

.all-clear {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 20px;
  margin: 14px 20px;
  background: var(--ok-bg);
  border: 1px solid var(--ok-line);
  border-left: 3px solid var(--ok);
}
.all-clear-mark {
  font-size: 22px;
  color: var(--ok);
  font-weight: 700;
}
.all-clear strong { color: var(--ok); font-size: 14px; font-weight: 600; display: block; }
.all-clear span { color: var(--ink-2); font-size: 12px; }

/* ============ Footer ============ */
.colophon {
  margin-top: 24px;
  padding: 16px 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  align-items: start;
}
.colophon-block { display: grid; gap: 4px; }
.colophon-row {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 12px;
  font-size: 11.5px;
}
.colophon-row dt {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--ink-3);
  padding-top: 2px;
}
.colophon-row dd {
  margin: 0;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-1);
}
.colophon-note {
  grid-column: 1 / -1;
  font-size: 11.5px;
  color: var(--ink-3);
  border-top: 1px solid var(--border-faint);
  padding-top: 12px;
  line-height: 1.55;
}
.colophon-note .ro {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 600;
  padding: 1px 6px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  color: var(--ink-2);
  margin-right: 8px;
}

@media (max-width: 920px) {
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .topbar { grid-template-columns: 1fr; }
  .topbar-path { justify-self: stretch; }
}
@media (max-width: 560px) {
  .kpis { grid-template-columns: 1fr; }
  .leg-row { grid-template-columns: 14px 1fr auto; }
  .leg-files, .leg-pct { display: none; }
  .f { grid-template-columns: 12px 1fr; }
  .f-code { grid-column: 2; }
  .colophon { grid-template-columns: 1fr; }
}
"""


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<main class="doc {doc_severity_class}">

  <header class="topbar">
    <div class="brand">
      <span class="brand-mark">▣</span>
      claude-config-auditor
    </div>
    <code class="topbar-path">{subject}</code>
    <div class="topbar-meta">
      <span><strong>v{version}</strong></span>
      <span>{generated_at}</span>
      <span>id <strong>{report_id}</strong></span>
      <button class="theme-toggle" id="theme-toggle"
              type="button" aria-label="Cycle color theme"
              title="Cycle theme (auto / light / dark)"></button>
    </div>
  </header>

  {kpis}
  {utilization}
  {categories}
  {consumers}
  {findings}

  <footer class="colophon">
    <div class="colophon-block">
      <div class="colophon-row"><dt>Tool</dt><dd>claude-config-auditor v{version}</dd></div>
      <div class="colophon-row"><dt>Report ID</dt><dd>{report_id}</dd></div>
    </div>
    <div class="colophon-block">
      <div class="colophon-row"><dt>Generated</dt><dd>{generated_at}</dd></div>
      <div class="colophon-row"><dt>Tokenizer</dt><dd>{tokenizer}</dd></div>
    </div>
    <p class="colophon-note">
      <span class="ro">Read-only</span>
      {tokenizer_note} No files in the audited target were modified.
    </p>
  </footer>

</main>

<script>
/* Theme toggle: cycles auto -> light -> dark -> auto, persisted in
   localStorage. "auto" defers to prefers-color-scheme. Inline because the
   report file must remain self-contained (no external network). */
(function () {{
  var KEY = "cca-theme";
  var ICONS = {{ auto: "◑", light: "☀", dark: "☾" }};
  var ORDER = ["auto", "light", "dark"];
  var root = document.documentElement;
  var btn = document.getElementById("theme-toggle");
  function apply(theme) {{
    if (theme === "auto") {{
      root.removeAttribute("data-theme");
    }} else {{
      root.setAttribute("data-theme", theme);
    }}
    btn.dataset.theme = theme;
    btn.dataset.icon = ICONS[theme];
    btn.setAttribute(
      "aria-label",
      "Cycle color theme (current: " + theme + ")"
    );
  }}
  var stored;
  try {{ stored = localStorage.getItem(KEY); }} catch (e) {{ stored = null; }}
  apply(stored && ORDER.indexOf(stored) >= 0 ? stored : "auto");
  btn.addEventListener("click", function () {{
    var i = ORDER.indexOf(btn.dataset.theme);
    var next = ORDER[(i + 1) % ORDER.length];
    try {{ localStorage.setItem(KEY, next); }} catch (e) {{}}
    apply(next);
  }});
}})();
</script>
</body>
</html>
"""
